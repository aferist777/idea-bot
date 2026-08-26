"""Rebuild the HTML report from the demo teardown markdown, for eyeballing the template.

    python tools/demo_report.py
"""
import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot import db, report, steps   # noqa: E402

SRC = ROOT / "exports" / "demo-razbor-idea-bot.md"
BY_NUM = {s.num: s for s in steps.STEPS}


async def main():
    text = SRC.read_text(encoding="utf-8")
    raw = re.search(r"## Идея, как она была описана\n\n(.+?)\n\n## ", text, re.S).group(1)
    await db.init()
    idea_id = await db.create_idea(0, "Бот, который разбирает идею по 8 шагам", raw, "full")

    chunks = re.split(r"\n## Шаг (\d+) · ([^\n_]+?)(?: _\(.*?\)_)?\n", text)[1:]
    for i in range(0, len(chunks), 3):
        num, _title, body = int(chunks[i]), chunks[i + 1], chunks[i + 2]
        body = body.split("\n## ")[0].strip()
        srcs = []
        if "**Источники:**" in body:
            body, tail = body.split("**Источники:**", 1)
            srcs = re.findall(r"\[(.+?)\]\((https?://[^\s)]+)\)", tail)
        await db.save_step(idea_id, BY_NUM[num].key, num, body.strip(), srcs)

    await db.update_idea(idea_id, status="done", verdict="KILL", idx=8)
    await db.save_questions(idea_id, "formula", [
        {"q": "Сколько людей ты лично знаешь, кому это нужно?", "options": []}])
    qs = await db.get_questions(idea_id, "formula")
    await db.set_answer(qs[0]["id"], "Пару человек, и те не платили бы")

    idea = await db.get_idea(idea_id)
    path = await report.build(idea)
    print("steps:", len(await db.get_steps(idea_id)))
    print("size :", path.stat().st_size // 1024, "KB")
    print("file :", path)
    await db.delete_idea(idea_id)


asyncio.run(main())
