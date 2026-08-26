"""The whole teardown as one markdown file, ready to drop into Obsidian."""
import re

from . import db
from .config import EXPORT_DIR
from .steps import BY_KEY

_SLUG = re.compile(r"[^a-z0-9а-яё]+", re.I)


def _slug(text):
    s = _SLUG.sub("-", (text or "idea").lower()).strip("-")
    return s[:40] or "idea"


async def build(idea):
    steps = await db.get_steps(idea["id"])
    mode = "полный" if idea["mode"] != "fast" else "быстрый"
    head = [
        f"# {idea['title'] or 'Разбор идеи'}",
        "",
        f"Режим: {mode} · создан {idea['created_at']}"
        + (f" · **ВЕРДИКТ: {idea['verdict']}**" if idea["verdict"] else " · не закончен"),
        "",
        "## Идея, как она была описана",
        "",
        idea["raw"],
        "",
    ]
    for s in steps:
        st = BY_KEY.get(s["step_key"])
        title = st.title if st else s["step_key"]
        head += [f"## Шаг {s['num']} · {title}", "", s["content"], ""]
        if s["sources"]:
            head.append("**Источники:**")
            head += [f"- [{t}]({u})" for t, u in s["sources"]]
            head.append("")

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / f"razbor-{idea['id']}-{_slug(idea['title'])}.md"
    path.write_text("\n".join(head), encoding="utf-8")
    return path
