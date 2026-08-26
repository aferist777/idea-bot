"""Run the step engine straight from the shell, no Telegram involved.

    python tools/dry_run.py 2 fast      # first two steps of the fast route
    python tools/dry_run.py 8 full      # the whole thing
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import db, engine, steps   # noqa: E402

RAW = ("Телеграм-бот, который собирает боли айтишников из реддита и твиттера, "
       "я их аппрувлю, он делает разбор боли в мой канал и коротким рилсом "
       "с картинками и озвучкой. Монетизация — реклама в канале и потом свой продукт.")


async def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    mode = sys.argv[2] if len(sys.argv) > 2 else "fast"
    await db.init()
    idea_id = await db.create_idea(0, "dry run", RAW, mode)
    for i in range(n):
        idea = await db.get_idea(idea_id)
        step = steps.step_at(mode, i)
        if not step:
            break
        print(f"\n{'=' * 70}\nШАГ {step.num} · {step.title}{' [web]' if step.web else ''}\n{'=' * 70}")
        text, src = await engine.run_step(idea, step, online=step.web)
        print(text)
        if src:
            print("\nИСТОЧНИКИ:")
            for t, u in src:
                print(f" - {t} :: {u}")
        await db.update_idea(idea_id, idx=i + 1)
    print(f"\n[idea_id={idea_id}]")


asyncio.run(main())
