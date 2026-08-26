"""Assembles the context for one step and runs it.

Each step sees the raw idea plus every earlier step's output - and nothing about
the steps ahead, so it cannot collapse the whole teardown into one answer.
"""
import json
import logging
import re

from . import db, llm
from .steps import prompt_for, questions_system_for, system_for

log = logging.getLogger(__name__)


async def _answers_block(idea_id):
    """Everything the user told us in the micro-surveys, skips excluded."""
    lines = [f"- {q['text']} — {q['answer']}"
             for q in await db.get_questions(idea_id) if (q["answer"] or "").strip()]
    if not lines:
        return None
    return "=== ЧТО ПОЛЬЗОВАТЕЛЬ РАССКАЗАЛ О СЕБЕ И ИДЕЕ ===\n" + "\n".join(lines)


async def build_context(idea, step, note=None):
    parts = [f"=== ИДЕЯ, КАК ЕЁ ОПИСАЛ ПОЛЬЗОВАТЕЛЬ ===\n{idea['raw']}"]
    answers = await _answers_block(idea["id"])
    if answers:
        parts.append(answers)
    for s in await db.get_steps(idea["id"]):
        if s["num"] < step.num:
            parts.append(f"=== ШАГ {s['num']} · РЕЗУЛЬТАТ ===\n{s['content']}")
    parts.append(prompt_for(step, idea.get("profile")))
    if note:
        parts.append(
            "=== ЗАМЕЧАНИЕ ПОЛЬЗОВАТЕЛЯ К ЭТОМУ ШАГУ ===\n"
            f"{note}\n"
            "Переделай шаг с учётом замечания. Не спорь с фактами, которые он сообщил о себе "
            "и о своём положении, — но и не смягчай выводы только потому, что ему не понравилось.")
    return "\n\n".join(parts)


async def run_step(idea, step, note=None, online=False):
    """Returns (text, sources). Raises llm.LLMError."""
    user = await build_context(idea, step, note)
    text, sources = await llm.chat(system_for(idea.get("profile")), user,
                                   max_tokens=step.tokens, online=online)
    await db.save_step(idea["id"], step.key, step.num, text, sources)
    if step.key == "formula":
        await db.update_idea(idea["id"], title=_title_from(text, idea["raw"]))
    return text, sources


_JSON = re.compile(r"\[.*\]", re.S)


async def gen_questions(idea, step):
    """1-2 tailored questions before a step. Never raises - no questions is a fine outcome."""
    parts = [f"=== ИДЕЯ ===\n{idea['raw']}"]
    answers = await _answers_block(idea["id"])
    if answers:
        parts.append(answers)
    for s in await db.get_steps(idea["id"]):
        if s["num"] < step.num:
            parts.append(f"=== ШАГ {s['num']} · РЕЗУЛЬТАТ ===\n{s['content'][:1200]}")
    parts.append(f"Следующий шаг разбора: «{step.title}». "
                 "Задай два вопроса, ответы на которые сделают этот шаг точнее.")
    try:
        text, _ = await llm.chat(questions_system_for(idea.get("profile")),
                                 "\n\n".join(parts), max_tokens=500)
        m = _JSON.search(text)
        items = json.loads(m.group(0)) if m else []
    except Exception as e:
        log.warning("question generation failed: %s", e)
        return []

    out = []
    for it in items[:2]:
        q = str(it.get("q") or "").strip()
        opts = [str(o).strip()[:40] for o in (it.get("options") or []) if str(o).strip()][:4]
        if q and len(opts) >= 2:
            out.append({"q": q[:300], "options": opts})
    return out


_SUT = re.compile(r"\*\*Суть:?\*\*\s*(.+)")


def _title_from(text, fallback):
    m = _SUT.search(text)
    src = (m.group(1) if m else fallback).strip().replace("\n", " ")
    return src[:70] + ("…" if len(src) > 70 else "")
