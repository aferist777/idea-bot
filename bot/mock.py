"""Canned answers for driving the bot without an API key.

Switched on by MOCK_LLM=1 in .env. Steps replay the demo teardown, so the texts are
about idea-bot itself, not about whatever the user typed - the point is to exercise
the Telegram flow (gates, survey, pause, report), not the analysis.
"""
import asyncio
import re

from .config import EXPORT_DIR

_DEMO = EXPORT_DIR / "demo-razbor-idea-bot.md"
_STEP_IN_PROMPT = re.compile(r"ШАГ (\d+) ·")

QUESTIONS = """[{"q": "Сколько людей ты лично знаешь, кому это нужно?",
  "options": ["Ни одного", "Пару человек", "Больше десяти", "Не считал"]},
 {"q": "Сколько часов в неделю готов на это тратить?",
  "options": ["До 5", "5-15", "Больше 15", "Пока не думал"]}]"""

_cache = {}


def _load():
    if _cache or not _DEMO.exists():
        return _cache
    text = _DEMO.read_text(encoding="utf-8")
    chunks = re.split(r"\n## Шаг (\d+) · [^\n]+\n", text)[1:]
    for i in range(0, len(chunks), 3):
        _cache[int(chunks[i])] = chunks[i + 1].split("\n## ")[0].strip()
    return _cache


async def chat(system, user, max_tokens=1600, online=False, temperature=None):
    await asyncio.sleep(3 if online else 1.5)     # so the "думаю…" state is visible
    if system.startswith("Ты готовишь короткие уточняющие"):
        return QUESTIONS, []
    steps = _load()
    nums = [int(n) for n in _STEP_IN_PROMPT.findall(user)]
    body = steps.get(nums[-1] if nums else 1) or "Заглушка: демо-текст не найден."
    srcs = [("Обзор валидаторов идей, август 2026", "https://preuve.ai/blog/best-tools"),
            ("Telegram Stars: комиссии и холд", "https://grambase.ai/blog/stars")]
    return body, (srcs if online else [])
