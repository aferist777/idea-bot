"""Offline check of the micro-survey: DB round-trip, JSON parsing, context assembly.

Mocks the model, so it needs no API key.  python tools/test_flow.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import db, engine, llm, render, report, steps   # noqa: E402

FAKE = """Вот вопросы:
[{"q": "Сколько людей ты лично знаешь, кому это нужно?",
  "options": ["Ни одного", "1-3", "Больше десяти", "Не считал"]},
 {"q": "Сколько часов в неделю готов на это тратить?",
  "options": ["До 5", "5-15", "Больше 15"]},
 {"q": "Третий вопрос сверх лимита", "options": ["а", "б"]}]"""


async def fake_chat(system, user, **kw):
    return FAKE, []


async def main():
    llm.chat = fake_chat
    await db.init()
    idea_id = await db.create_idea(0, "тест", "Бот, который делает X для Y.", "fast")
    idea = await db.get_idea(idea_id)
    step = steps.BY_KEY["formula"]

    items = await engine.gen_questions(idea, step)
    assert len(items) == 2, f"лимит в 2 вопроса не сработал: {len(items)}"
    assert len(items[0]["options"]) == 4, items[0]
    print("1. генерация и парсинг JSON:", [i["q"][:30] for i in items])

    await db.save_questions(idea_id, step.key, items)
    qs = await db.get_questions(idea_id, step.key)
    assert len(qs) == 2 and all(q["answer"] is None for q in qs)
    print("2. сохранено вопросов:", len(qs))

    await db.set_answer(qs[0]["id"], qs[0]["options"][1])          # кнопкой
    await db.set_answer(qs[1]["id"], "часа три, по вечерам")       # своими словами
    ctx = await engine.build_context(idea, steps.BY_KEY["assumptions"])
    assert "ЧТО ПОЛЬЗОВАТЕЛЬ РАССКАЗАЛ" in ctx and "часа три" in ctx
    print("3. ответы попали в контекст следующего шага")

    await db.save_questions(idea_id, "demand", [{"q": "Пропущу", "options": ["а", "б"]}])
    await db.skip_rest(idea_id, "demand")
    skipped = await db.get_questions(idea_id, "demand")
    assert skipped[0]["answer"] == ""
    ctx2 = await engine.build_context(idea, steps.BY_KEY["rivals"])
    assert "Пропущу" not in ctx2, "пропущенный вопрос протёк в контекст"
    print("4. «пропустить всё» не засоряет контекст")

    html = render.to_html("**Жирный** и `код` и <script>alert(1)</script>")
    assert "<b>Жирный</b>" in html and "&lt;script&gt;" in html
    long = render.chunks("абзац\n\n" * 3000)
    assert all(len(c) <= 3900 for c in long) and len(long) > 1
    print(f"5. рендер и разбивка: {len(long)} сообщения(й), макс {max(map(len, long))} симв.")

    await db.save_step(idea_id, "assumptions", 2,
                       "🔴 1. Первое допущение\n🟡 2. Второе\n⚪ 3. Третье\n\n**Самое смертельное:** 1",
                       [("Источник раз", "https://example.com/a")])
    await db.save_step(idea_id, "verdict", 8,
                       "**ВЕРДИКТ: KILL**\n\nПотому что <b>опасный</b> ввод и **жирный**.\n\n"
                       "боль ▮▮▮▯▯ · рынок ▮▮▯▯▯ · выполнимость ▮▮▮▮▯ · защищённость ▮▯▯▯▯")
    await db.update_idea(idea_id, verdict="KILL", status="done")
    idea = await db.get_idea(idea_id)
    doc = (await report.build(idea)).read_text(encoding="utf-8")
    assert doc.count('<td class="m"') == 3, "таблица допущений не собралась"
    assert doc.count('class="score"') == 4, "полоски оценок не собрались"
    assert "▮" not in doc, "строка оценок продублировалась в тексте"
    assert "<p>🔴" not in doc, "допущения продублировались под таблицей"
    assert "&lt;b&gt;опасный&lt;/b&gt;" in doc, "html из модели не экранирован"
    assert doc.count("<div") == doc.count("</div>"), "теги не сбалансированы"
    assert 'href="https://example.com/a"' in doc, "источники не попали в отчёт"
    print(f"6. отчёт: {len(doc) // 1024} КБ, таблица, полоски и экранирование на месте")

    place = steps.system_for("place")
    online = steps.system_for("online")
    assert "поток" in place and "соло-разработчик" not in place
    assert "сабреддит" not in place.lower() or "Никогда не предлагай" in place
    assert "в одиночку" in online
    test_step = steps.BY_KEY["test"]
    p_place = steps.prompt_for(test_step, "place")
    p_online = steps.prompt_for(test_step, "online")
    assert "замер потока" in p_place, "офлайн-подсказка не приклеилась к шагу"
    assert p_online == test_step.prompt, "онлайн-профиль не должен ничего добавлять"
    res_place = steps.prompt_for(steps.BY_KEY["resources"], "place")
    assert "аренд" in res_place and "чеках за день" in res_place
    loc = steps.prompt_for(steps.BY_KEY["rivals"], "local")
    assert "картах" in loc or "объявлени" in loc
    print("7. профили: system и шаги меняются под тип дела")

    o1 = await db.create_order(0, "tester", idea_id, "launch", 3900)
    o2 = await db.create_order(0, "tester", idea_id, "launch", 3900)
    assert o1["id"] == o2["id"], "двойное нажатие наплодило счета"
    assert not await db.has_paid(0, idea_id, "launch")
    await db.set_order_status(o1["id"], "claimed")
    await db.set_order_status(o1["id"], "paid")
    assert await db.has_paid(0, idea_id, "launch"), "оплата не засчиталась"
    paid = await db.get_order(o1["id"])
    assert paid["paid_at"], "не проставилось время оплаты"
    o3 = await db.create_order(0, "tester", idea_id, "launch", 3900)
    assert o3["id"] != o1["id"], "после оплаты должен создаваться новый счёт"
    await db.set_order_status(o3["id"], "canceled")
    print(f"8. счета: идемпотентность, статусы, has_paid — счёт №{o1['id']}")

    await db.delete_idea(idea_id)
    assert not await db.get_questions(idea_id)
    print("9. удаление разбора чистит вопросы")
    print("\nВСЁ ЗЕЛЁНОЕ")


asyncio.run(main())
