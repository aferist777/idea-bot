"""Model output -> safe Telegram HTML, and long text -> sendable chunks.

The model writes markdown-lite (**bold**, `code`); anything else it emits is escaped,
so a stray "<" can never blow up a send.
"""
import html
import re

from .config import TG_LIMIT

_BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)
_CODE = re.compile(r"`([^`\n]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_HEAD = re.compile(r"^#{1,6}\s*", re.M)


def to_html(text: str) -> str:
    t = _HEAD.sub("", text.strip())
    t = html.escape(t)
    t = _LINK.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', t)
    t = _BOLD.sub(lambda m: f"<b>{m.group(1)}</b>", t)
    t = _CODE.sub(lambda m: f"<code>{m.group(1)}</code>", t)
    return t


def chunks(text: str, limit: int = TG_LIMIT):
    """Split on blank lines first, then lines, so a paragraph is never cut mid-word."""
    if len(text) <= limit:
        return [text]
    out, buf = [], ""
    for block in text.split("\n\n"):
        piece = block if not buf else buf + "\n\n" + block
        if len(piece) <= limit:
            buf = piece
            continue
        if buf:
            out.append(buf)
            buf = ""
        while len(block) > limit:
            cut = block.rfind("\n", 0, limit)
            if cut < limit // 2:
                cut = limit
            out.append(block[:cut])
            block = block[cut:].lstrip("\n")
        buf = block
    if buf:
        out.append(buf)
    return out


def sources_block(sources):
    if not sources:
        return ""
    lines = ["", "<b>Источники:</b>"]
    for i, (title, url) in enumerate(sources[:8], 1):
        safe = html.escape(title)[:70]
        lines.append(f'{i}. <a href="{url}">{safe}</a>')
    return "\n".join(lines)


def verdict_of(text: str) -> str:
    """Pull GO / PIVOT / KILL out of the final step for the idea list."""
    m = re.search(r"ВЕРДИКТ:?\s*\**\s*(GO|PIVOT|KILL)", text, re.I)
    return m.group(1).upper() if m else ""
