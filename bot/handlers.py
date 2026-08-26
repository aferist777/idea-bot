import html
import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (CallbackQuery, FSInputFile, LabeledPrice, Message,
                           PreCheckoutQuery)

from . import billing, db, engine, export, llm, orders, render, report, steps
from .config import (FAST_COST, FULL_COST, NEW_USER_FREE_RUNS, REGEN_LIMIT)
from .keyboards import (confirm_del_kb, describe_kb, final_kb, gate_kb, idea_kb, ideas_kb,
                        launch_kb, main_menu, mode_kb, profile_kb, question_kb, retry_kb,
                        topup_kb, web_kb)
from .states import Ask, Fix, New

router = Router()
log = logging.getLogger(__name__)

BUSY = set()   # idea ids with a step in flight - stops double taps from paying twice

HELLO = (
    "🧨 <b>Разбор идеи</b>\n\n"
    "Я не хвалю идеи. Я ищу, где они ломаются — по шагам, а не одной простынёй.\n\n"
    "Разбираю и офлайн, и онлайн: точку с помещением, выездную услугу или "
    "интернет-продукт. Считаю в рублях, чеках и часах.\n\n"
    "Восемь шагов: формулировка → допущения → спрос → конкуренты → премортем → "
    "ресурсы → дешёвый тест → вердикт GO/PIVOT/KILL.\n\n"
    "Между шагами ты решаешь, идти дальше или переделать. Разбор можно бросить "
    "на середине и вернуться завтра — всё сохранится."
)

HOW = (
    "<b>Как устроен разбор</b>\n\n"
    "🎯 <b>1 · Формулировка</b> — что это, кому и какую боль снимает. Своими словами, без украшений.\n"
    "🧨 <b>2 · Допущения</b> — 8-15 скрытых предположений, из них 2-4 смертельных.\n"
    "🔍 <b>3 · Спрос</b> — поиск по твоему городу и нише: есть ли люди и платят ли они.\n"
    "⚔️ <b>4 · Конкуренты</b> — кто рядом, по каким ценам и что пишут в отзывах.\n"
    "☠️ <b>5 · Премортем</b> — год прошёл, проект мёртв, пять сценариев вскрытия.\n"
    "⏳ <b>6 · Ресурсы</b> — вложения, постоянка, точка безубыточности, окупаемость.\n"
    "🧪 <b>7 · Дешёвый тест</b> — проверка на 7 дней, которая убивает главное допущение.\n"
    "⚖️ <b>8 · Вердикт</b> — GO, PIVOT или KILL. Без «зависит».\n\n"
    f"Полный разбор — {FULL_COST}⭐. Быстрый (шаги 1, 2, 5, 7, 8) — {FAST_COST}⭐.\n"
    "Первый разбор бесплатно. «Поправить» на шаге — бесплатно, "
    f"до {REGEN_LIMIT} раз."
)


def _esc(t):
    return html.escape(t or "")


async def _menu(target, text=HELLO):
    if isinstance(target, CallbackQuery):
        await target.message.answer(text, reply_markup=main_menu(), disable_web_page_preview=True)
        await target.answer()
    else:
        await target.answer(text, reply_markup=main_menu(), disable_web_page_preview=True)


# ---------------- entry ----------------
@router.message(CommandStart())
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    ref = None
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip().isdigit():
        ref = int(parts[1].strip())
    await db.ensure_user(m.from_user.id, m.from_user.username, ref, NEW_USER_FREE_RUNS)
    await _menu(m)


@router.message(Command("menu", "cancel"))
async def cmd_menu(m: Message, state: FSMContext):
    await state.clear()
    await _menu(m)


@router.callback_query(F.data == "menu")
async def cb_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await _menu(cb)


@router.callback_query(F.data == "how")
async def cb_how(cb: CallbackQuery):
    await cb.message.answer(HOW, reply_markup=main_menu())
    await cb.answer()


# ---------------- money ----------------
@router.callback_query(F.data == "balance")
async def cb_balance(cb: CallbackQuery):
    u = await db.ensure_user(cb.from_user.id, cb.from_user.username, None, NEW_USER_FREE_RUNS)
    me = await cb.bot.me()
    free = u.get("free_runs") or 0
    txt = (f"💳 Баланс: <b>{u.get('balance') or 0}⭐</b>\n"
           f"🎁 Бесплатных разборов: <b>{free}</b>\n\n"
           f"Полный — {FULL_COST}⭐ · быстрый — {FAST_COST}⭐\n\n"
           f"Зови друзей: за каждого, кто дойдёт до вердикта, тебе +1 бесплатный разбор.\n"
           f"<code>https://t.me/{me.username}?start={cb.from_user.id}</code>")
    await cb.message.answer(txt, reply_markup=topup_kb(), disable_web_page_preview=True)
    await cb.answer()


@router.callback_query(F.data.startswith("buy:"))
async def cb_buy(cb: CallbackQuery):
    n = int(cb.data.split(":")[1])
    await cb.message.answer_invoice(
        title=f"Пополнение {n}⭐",
        description=f"{n} звёзд на баланс разборов.",
        payload=f"topup:{n}",
        currency="XTR",
        prices=[LabeledPrice(label=f"{n} звёзд", amount=n)],
        provider_token="",
    )
    await cb.answer()


@router.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)


@router.message(F.successful_payment)
async def on_paid(m: Message):
    sp = m.successful_payment
    try:
        n = int(sp.invoice_payload.split(":")[1])
    except Exception:
        n = sp.total_amount
    await billing.apply_topup(m.from_user.id, n)
    u = await db.get_user(m.from_user.id)
    await m.answer(f"✅ Зачислено {n}⭐. Баланс: {u.get('balance')}⭐.", reply_markup=main_menu())


# ---------------- new idea ----------------
BRIEF = (
    "Расскажи об идее по пунктам — чем подробнее, тем точнее вердикт. "
    "Пиши одним сообщением или несколькими, как удобно.\n\n"
    "1⃣ <b>Идея</b> — что делаешь и в чём суть\n"
    "2⃣ <b>Клиент</b> — кто это конкретно, а не «все подряд»\n"
    "3⃣ <b>Сейчас</b> — что он делает вместо этого сегодня\n"
    "4⃣ <b>Деньги</b> — на чём зарабатываешь и сколько берёшь\n"
    "5⃣ <b>Что уже есть</b> — опыт, деньги, помещение, аудитория, наработки\n"
    "6⃣ <b>Сколько вложишь</b> — денег и часов в неделю\n"
    "7⃣ <b>Город и район</b> — если дело офлайн\n\n"
    "Не знаешь пункт — так и пиши «не знаю». Это честный ответ, он тоже пойдёт в дело: "
    "разберу, чем именно такое незнание грозит.\n\n"
    "Шаблон ниже можно нажать — скопируется целиком."
)

FORM = ("1. Идея: \n"
        "2. Клиент: \n"
        "3. Сейчас он: \n"
        "4. Деньги: \n"
        "5. Уже есть: \n"
        "6. Вложу: \n"
        "7. Город: ")

THIN = 320   # ниже этого описание слишком тощее для приличного разбора


@router.callback_query(F.data == "new")
async def cb_new(cb: CallbackQuery, state: FSMContext):
    await state.set_state(New.describing)
    await state.update_data(parts=[])
    await cb.message.answer(BRIEF)
    await cb.message.answer(f"<pre>{FORM}</pre>")
    await cb.answer()


@router.callback_query(F.data == "redescribe")
async def cb_redescribe(cb: CallbackQuery, state: FSMContext):
    await state.set_state(New.describing)
    await state.update_data(parts=[])
    await cb.message.answer("Стёр. Пиши заново.")
    await cb.answer()


@router.message(New.describing)
async def got_idea(m: Message, state: FSMContext):
    data = await state.get_data()
    parts = list(data.get("parts") or [])
    chunk = (m.text or "").strip()
    if not chunk:
        return
    parts.append(chunk)
    await state.update_data(parts=parts)
    total = len("\n".join(parts))

    tail = ("Пока коротко — на таком описании разбор выйдет общим. Допиши, кто клиент, "
            "что он делает сейчас и на чём деньги."
            if total < THIN else
            "Есть что копать. Можешь дописать ещё или начинать.")
    await m.answer(tail, reply_markup=describe_kb(total, thin=total < THIN))


@router.callback_query(New.describing, F.data == "described")
async def cb_described(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    parts = data.get("parts") or []
    if not parts:
        await cb.answer("Сначала опиши идею", show_alert=True)
        return
    await state.update_data(raw="\n".join(parts)[:6000])
    await state.set_state(New.profile)
    await cb.message.answer(
        "Что это за дело? От этого зависит, чем мерить: потоком мимо двери, "
        "заявками с карт или установками.",
        reply_markup=profile_kb())
    await cb.answer()


@router.callback_query(New.profile, F.data.startswith("prof:"))
async def cb_profile(cb: CallbackQuery, state: FSMContext):
    profile = cb.data.split(":")[1]
    await state.update_data(profile=profile)
    await state.set_state(New.mode)
    await cb.message.answer(
        f"Разбираю как {steps.PROFILE_TITLE.get(profile, profile)}. "
        "Насколько глубоко копаем?", reply_markup=mode_kb())
    await cb.answer()


@router.callback_query(New.mode, F.data.startswith("mode:"))
async def cb_mode(cb: CallbackQuery, state: FSMContext):
    mode = cb.data.split(":")[1]
    data = await state.get_data()
    raw = data.get("raw")
    profile = data.get("profile") or "online"
    await state.clear()
    if not raw:
        await _menu(cb, "Идея потерялась. Начни заново.")
        return

    user = await db.ensure_user(cb.from_user.id, cb.from_user.username, None, NEW_USER_FREE_RUNS)
    ok, how = await billing.charge_run(user, cb.from_user.id, mode)
    if not ok:
        await cb.message.answer(
            f"Не хватает звёзд: разбор стоит {billing.cost(mode)}⭐, "
            f"на балансе {user.get('balance') or 0}⭐.", reply_markup=topup_kb())
        await cb.answer()
        return

    idea_id = await db.create_idea(cb.from_user.id, raw[:70], raw, mode, profile)
    note = " (бесплатный)" if how in ("free_run", "admin") else f" · списано {billing.cost(mode)}⭐"
    await cb.message.answer(f"Погнали{note}.")
    await cb.answer()
    await _start_step(cb.message, idea_id)


# ---------------- the step machine ----------------
async def _start_step(msg: Message, idea_id):
    """Micro-survey (if the step wants one) -> web-search choice -> the step itself."""
    idea = await db.get_idea(idea_id)
    if not idea:
        return
    step = steps.step_at(idea["mode"], idea["idx"])
    if step is None:
        await _finish(msg, idea)
        return
    if step.ask and not await db.get_questions(idea_id, step.key):
        wait = await msg.answer("Пара вопросов перед шагом — отвечать необязательно.")
        items = await engine.gen_questions(idea, step)
        if items:
            await db.save_questions(idea_id, step.key, items)
        else:
            try:
                await wait.delete()
            except Exception:
                pass
    if await _ask_next(msg, idea, step):
        return
    await _proceed_step(msg, idea, step)


async def _ask_next(msg: Message, idea, step):
    """Sends the first unanswered question. True means we're now waiting on the user."""
    for q in await db.get_questions(idea["id"], step.key):
        if q["answer"] is None:
            await msg.answer(f"❓ {_esc(q['text'])}", reply_markup=question_kb(q, idea["id"]))
            return True
    return False


async def _proceed_step(msg: Message, idea, step):
    if step.web:
        await msg.answer(
            f"{step.head}\n\nЭтому шагу нужны реальные данные. Поискать в интернете? "
            "Это дольше на минуту, зато со ссылками.",
            reply_markup=web_kb(idea["id"]))
        return
    await _execute(msg, idea, step, online=False)


async def _after_answer(msg: Message, idea_id, step_key):
    idea = await db.get_idea(idea_id)
    step = steps.BY_KEY.get(step_key)
    if not idea or not step:
        return
    if await _ask_next(msg, idea, step):
        return
    await _proceed_step(msg, idea, step)


async def _execute(msg: Message, idea, step, online=False, note=None):
    idea_id = idea["id"]
    if idea_id in BUSY:
        return
    BUSY.add(idea_id)
    total = steps.total(idea["mode"])
    pos = f"{idea['idx'] + 1}/{total}"
    wait = await msg.answer(
        f"{step.head}  <i>{pos}</i>\n\n"
        + ("🔍 ищу в интернете, это до минуты…" if online else "⏳ думаю…"))
    try:
        text, sources = await engine.run_step(idea, step, note=note, online=online)
    except llm.LLMError as e:
        await wait.edit_text(f"⚠️ Модель не ответила.\n<code>{_esc(str(e))[:300]}</code>",
                             reply_markup=retry_kb(idea_id))
        return
    except Exception as e:
        log.exception("step failed")
        await wait.edit_text(f"⚠️ Сбой на шаге: <code>{_esc(str(e))[:200]}</code>",
                             reply_markup=retry_kb(idea_id))
        return
    finally:
        BUSY.discard(idea_id)

    body = render.to_html(text) + render.sources_block(sources)
    last_i = step.key == "verdict"
    parts = render.chunks(body)
    await wait.edit_text(f"{step.head}  <i>{pos}</i>")
    for i, part in enumerate(parts):
        is_last = i == len(parts) - 1
        kb = None
        if is_last and not last_i:
            nxt = steps.step_at(idea["mode"], idea["idx"] + 1)
            kb = gate_kb(idea_id, last=(nxt is not None and nxt.key == "verdict"))
        await msg.answer(part, reply_markup=kb, disable_web_page_preview=True)

    if last_i:
        verdict = render.verdict_of(text)
        await db.update_idea(idea_id, status="done", verdict=verdict or "")
        ref = await billing.maybe_qualify_referral(idea["tg_id"])
        if ref:
            try:
                await msg.bot.send_message(ref, "🎁 Твой друг дошёл до вердикта — тебе +1 разбор.")
            except Exception:
                pass
        await msg.answer("Разбор закончен.", reply_markup=final_kb(idea_id))
        await _maybe_offer_launch(msg, idea, verdict)


async def _maybe_offer_launch(msg: Message, idea, verdict):
    """After GO or PIVOT, point at the paid track - KILL gets no upsell, that would be crass."""
    if verdict == "KILL" or not orders.offer_visible(idea["tg_id"]):
        return
    if await db.has_paid(idea["tg_id"], idea["id"], orders.PRODUCT):
        return
    await msg.answer(
        "Дальше начинается то, чего разбор не считает: сколько денег нужно точно, "
        "что оформить и в каком порядке, где брать оборудование и что делать "
        "первые два месяца.",
        reply_markup=launch_kb(idea["id"]))


async def _finish(msg: Message, idea):
    await db.update_idea(idea["id"], status="done")
    await msg.answer("Разбор закончен.", reply_markup=final_kb(idea["id"]))


# ---------------- micro-survey ----------------
async def _own_question(cb: CallbackQuery, qid):
    q = await db.get_question(qid)
    if not q:
        await cb.answer("Вопрос потерялся", show_alert=True)
        return None
    idea = await db.get_idea(q["idea_id"])
    if not idea or idea["tg_id"] != cb.from_user.id:
        await cb.answer("Не найдено", show_alert=True)
        return None
    return q


async def _close_question(cb: CallbackQuery, q, answer):
    mark = f"✅ {_esc(answer)}" if answer else "— пропущено"
    try:
        await cb.message.edit_text(f"❓ {_esc(q['text'])}\n{mark}")
    except Exception:
        pass


@router.callback_query(F.data.startswith("ans:"))
async def cb_answer(cb: CallbackQuery):
    _, qid, i = cb.data.split(":")
    q = await _own_question(cb, int(qid))
    if not q:
        return
    try:
        opt = q["options"][int(i)]
    except (IndexError, ValueError):
        await cb.answer("Вариант потерялся", show_alert=True)
        return
    await db.set_answer(q["id"], opt)
    await _close_question(cb, q, opt)
    await cb.answer()
    await _after_answer(cb.message, q["idea_id"], q["step_key"])


@router.callback_query(F.data.startswith("askskip:"))
async def cb_ask_skip(cb: CallbackQuery):
    q = await _own_question(cb, int(cb.data.split(":")[1]))
    if not q:
        return
    await db.set_answer(q["id"], "")
    await _close_question(cb, q, "")
    await cb.answer()
    await _after_answer(cb.message, q["idea_id"], q["step_key"])


@router.callback_query(F.data.startswith("askall:"))
async def cb_ask_all(cb: CallbackQuery):
    idea_id = int(cb.data.split(":")[1])
    idea = await db.get_idea(idea_id)
    if not idea or idea["tg_id"] != cb.from_user.id:
        await cb.answer("Не найдено", show_alert=True)
        return
    step = steps.step_at(idea["mode"], idea["idx"])
    await db.skip_rest(idea_id, step.key)
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cb.answer()
    await _proceed_step(cb.message, idea, step)


@router.callback_query(F.data.startswith("askfree:"))
async def cb_ask_free(cb: CallbackQuery, state: FSMContext):
    q = await _own_question(cb, int(cb.data.split(":")[1]))
    if not q:
        return
    await state.set_state(Ask.typing)
    await state.update_data(qid=q["id"])
    await cb.message.answer(f"❓ {_esc(q['text'])}\n\nНапиши ответ своими словами.")
    await cb.answer()


@router.message(Ask.typing)
async def got_free_answer(m: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    q = await db.get_question(data.get("qid"))
    if not q:
        await _menu(m, "Вопрос потерялся.")
        return
    await db.set_answer(q["id"], (m.text or "")[:500])
    await _after_answer(m, q["idea_id"], q["step_key"])


@router.callback_query(F.data.startswith("go:"))
async def cb_go(cb: CallbackQuery):
    _, idea_id, online = cb.data.split(":")
    idea = await db.get_idea(int(idea_id))
    if not idea or idea["tg_id"] != cb.from_user.id:
        await cb.answer("Не найдено", show_alert=True)
        return
    step = steps.step_at(idea["mode"], idea["idx"])
    await cb.answer()
    if step is None:
        await _finish(cb.message, idea)
        return
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _execute(cb.message, idea, step, online=(online == "1"))


@router.callback_query(F.data.startswith("next:"))
async def cb_next(cb: CallbackQuery):
    idea_id = int(cb.data.split(":")[1])
    idea = await db.get_idea(idea_id)
    if not idea or idea["tg_id"] != cb.from_user.id:
        await cb.answer("Не найдено", show_alert=True)
        return
    if idea_id in BUSY:
        await cb.answer("Шаг ещё считается", show_alert=True)
        return
    await cb.answer()
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    if steps.step_at(idea["mode"], idea["idx"] + 1) is None:
        await _finish(cb.message, idea)
        return
    await db.update_idea(idea_id, idx=idea["idx"] + 1, status="active")
    await _start_step(cb.message, idea_id)


@router.callback_query(F.data.startswith("resume:"))
async def cb_resume(cb: CallbackQuery):
    idea_id = int(cb.data.split(":")[1])
    idea = await db.get_idea(idea_id)
    if not idea or idea["tg_id"] != cb.from_user.id:
        await cb.answer("Не найдено", show_alert=True)
        return
    await cb.answer()
    step = steps.step_at(idea["mode"], idea["idx"])
    if step is None:
        await _finish(cb.message, idea)
        return
    done = await db.get_step(idea_id, step.key)
    if not done:
        await db.update_idea(idea_id, status="active")
        await _start_step(cb.message, idea_id)
        return
    # step already generated - show it again and re-offer the gate
    body = render.to_html(done["content"]) + render.sources_block(done["sources"])
    total = steps.total(idea["mode"])
    await cb.message.answer(f"{step.head}  <i>{idea['idx'] + 1}/{total}</i>")
    parts = render.chunks(body)
    for i, part in enumerate(parts):
        kb = gate_kb(idea_id) if i == len(parts) - 1 else None
        await cb.message.answer(part, reply_markup=kb, disable_web_page_preview=True)
    await db.update_idea(idea_id, status="active")


@router.callback_query(F.data.startswith("pause:"))
async def cb_pause(cb: CallbackQuery):
    idea_id = int(cb.data.split(":")[1])
    await db.update_idea(idea_id, status="paused")
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cb.message.answer("⏸ Отложил. Разбор ждёт в «Мои разборы» — доплачивать не придётся.",
                            reply_markup=main_menu())
    await cb.answer()


# ---------------- fix a step ----------------
@router.callback_query(F.data.startswith("fix:"))
async def cb_fix(cb: CallbackQuery, state: FSMContext):
    idea_id = int(cb.data.split(":")[1])
    idea = await db.get_idea(idea_id)
    if not idea or idea["tg_id"] != cb.from_user.id:
        await cb.answer("Не найдено", show_alert=True)
        return
    step = steps.step_at(idea["mode"], idea["idx"])
    done = await db.get_step(idea_id, step.key)
    if done and (done["regens"] or 0) >= REGEN_LIMIT and not billing.is_admin(cb.from_user.id):
        await cb.answer(f"Этот шаг уже переделан {REGEN_LIMIT} раза. Идём дальше.", show_alert=True)
        return
    await state.set_state(Fix.typing)
    await state.update_data(idea_id=idea_id, step_key=step.key)
    await cb.message.answer(
        "Что не так? Напиши замечание — что я упустил, где ошибся, что уточнить.\n\n"
        "<i>Например: «аудитория не та, это для дизайнеров, а не для маркетологов» "
        "или «у меня уже есть 300 подписчиков в этой нише».</i>")
    await cb.answer()


@router.message(Fix.typing)
async def got_fix(m: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    idea = await db.get_idea(data.get("idea_id"))
    if not idea:
        await _menu(m, "Разбор потерялся.")
        return
    step = steps.BY_KEY.get(data.get("step_key"))
    await _execute(m, idea, step, online=False, note=(m.text or "")[:1500])


# ---------------- my teardowns ----------------
@router.callback_query(F.data == "list")
async def cb_list(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    ideas = await db.list_ideas(cb.from_user.id)
    if not ideas:
        await cb.message.answer("Пока пусто.", reply_markup=main_menu())
        await cb.answer()
        return
    await cb.message.answer("📂 Твои разборы:", reply_markup=ideas_kb(ideas, steps.total))
    await cb.answer()


@router.callback_query(F.data.startswith("open:"))
async def cb_open(cb: CallbackQuery):
    idea = await db.get_idea(int(cb.data.split(":")[1]))
    if not idea or idea["tg_id"] != cb.from_user.id:
        await cb.answer("Не найдено", show_alert=True)
        return
    done = idea["status"] == "done"
    total = steps.total(idea["mode"])
    mode = "полный" if idea["mode"] != "fast" else "быстрый"
    head = (f"<b>{_esc(idea['title'])}</b>\n\n"
            f"Режим: {mode} · шаг {min(idea['idx'] + 1, total)}/{total}\n"
            + (f"Вердикт: <b>{idea['verdict']}</b>" if idea["verdict"] else "Не закончен"))
    await cb.message.answer(head, reply_markup=idea_kb(
        idea, done, admin=billing.is_admin(cb.from_user.id)))
    await cb.answer()


@router.callback_query(F.data.startswith("file:"))
async def cb_file(cb: CallbackQuery):
    idea = await db.get_idea(int(cb.data.split(":")[1]))
    if not idea or idea["tg_id"] != cb.from_user.id:
        await cb.answer("Не найдено", show_alert=True)
        return
    await cb.answer("Собираю отчёт…")
    path = await report.build(idea)
    await cb.message.answer_document(
        FSInputFile(path),
        caption="Весь разбор одной страницей. Открывается в браузере прямо из чата, "
                "работает без интернета, печатается в PDF (Ctrl+P).")


@router.callback_query(F.data.startswith("md:"))
async def cb_md(cb: CallbackQuery):
    idea = await db.get_idea(int(cb.data.split(":")[1]))
    if not idea or not billing.is_admin(cb.from_user.id):
        await cb.answer("Не найдено", show_alert=True)
        return
    path = await export.build(idea)
    await cb.message.answer_document(FSInputFile(path), caption="Markdown для Obsidian.")
    await cb.answer()


@router.callback_query(F.data.startswith("del:"))
async def cb_del(cb: CallbackQuery):
    idea_id = int(cb.data.split(":")[1])
    await cb.message.answer("Удалить разбор целиком?", reply_markup=confirm_del_kb(idea_id))
    await cb.answer()


@router.callback_query(F.data.startswith("delyes:"))
async def cb_delyes(cb: CallbackQuery):
    idea_id = int(cb.data.split(":")[1])
    idea = await db.get_idea(idea_id)
    if not idea or idea["tg_id"] != cb.from_user.id:
        await cb.answer("Не найдено", show_alert=True)
        return
    await db.delete_idea(idea_id)
    await cb.message.answer("Удалено.", reply_markup=main_menu())
    await cb.answer()


# ---------------- fallback ----------------
@router.message(F.text)
async def fallback(m: Message):
    await _menu(m, "Жми кнопку — или /menu, если потерялся.")
