"""The teardown as one self-contained .html file.

No external fonts, images or scripts: it opens straight from a Telegram chat,
works offline, and prints to PDF from the same file.
"""
import html
import re
from datetime import datetime

from . import db
from .config import EXPORT_DIR
from .steps import BY_KEY, PROFILE_TITLE

VERDICT_STYLE = {
    "GO": ("#1a7f37", "Делать", "Смертельные допущения проверяемы, ресурсы сходятся."),
    "PIVOT": ("#9a6700", "Менять форму", "Боль настоящая, но решение не то."),
    "KILL": ("#b42318", "Не делать", "Спрос, место или экономика не выдержали проверки."),
}
MARK_TITLE = {"🔴": "смертельное", "🟡": "тяжёлое", "⚪": "терпимое"}

CSS = """
:root { --ink:#1a1a1a; --dim:#5c5c5c; --line:#e3e3e3; --bg:#fff; --accent:#1a1a1a; }
* { box-sizing:border-box; }
body { margin:0; background:#f4f4f2; color:var(--ink);
  font:17px/1.62 Georgia,"Times New Roman",serif; }
.sheet { max-width:820px; margin:0 auto; background:var(--bg); padding:56px 60px 72px; }
h1,h2,h3,.ui { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
h1 { font-size:34px; line-height:1.2; margin:0 0 14px; letter-spacing:-.02em; }
h2 { font-size:22px; margin:44px 0 6px; letter-spacing:-.01em; break-after:avoid; }
h2 .num { color:var(--dim); font-weight:400; }
p { margin:0 0 14px; }
a { color:#0b57a4; }
.lede { color:var(--dim); font-size:15px; margin:0 0 28px; }
.rule { height:1px; background:var(--line); margin:34px 0; border:0; }
.verdict { border:2px solid var(--accent); border-radius:10px; padding:20px 24px; margin:26px 0; }
.verdict .word { font-size:13px; letter-spacing:.14em; text-transform:uppercase; color:var(--dim); }
.verdict .val { font-size:30px; font-weight:700; color:var(--accent); margin:2px 0 6px;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
.verdict .why { color:var(--dim); font-size:15px; }
.scores { display:flex; flex-wrap:wrap; gap:18px 30px; margin:22px 0 6px; }
.score { min-width:132px; }
.score .name { font-size:12px; letter-spacing:.08em; text-transform:uppercase; color:var(--dim); }
.bar { display:flex; gap:4px; margin-top:6px; }
.bar i { width:22px; height:9px; border-radius:2px; background:var(--line); }
.bar i.on { background:var(--accent); }
.toc { background:#fafaf8; border:1px solid var(--line); border-radius:10px; padding:18px 24px; }
.toc ol { margin:0; padding-left:22px; }
.toc li { margin:4px 0; }
.toc a { color:var(--ink); text-decoration:none; }
table { border-collapse:collapse; width:100%; margin:14px 0 18px; font-size:15px; }
th,td { text-align:left; padding:9px 10px; border-bottom:1px solid var(--line);
  vertical-align:top; }
th { font-size:12px; letter-spacing:.07em; text-transform:uppercase; color:var(--dim);
  font-weight:600; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
td.m { width:34px; font-size:16px; }
td.k { width:118px; color:var(--dim); font-size:13px; }
.src { font-size:14px; color:var(--dim); margin-top:10px; }
.src ol { padding-left:20px; margin:6px 0 0; }
.answers { background:#fafaf8; border-left:3px solid var(--line); padding:12px 18px;
  margin:16px 0; font-size:15px; }
.answers div { margin:5px 0; }
.answers b { font-weight:600; }
.gaps { border:1px solid var(--line); border-radius:10px; padding:22px 26px; margin-top:12px; }
.gaps ul { margin:10px 0 0; padding-left:20px; }
.gaps li { margin:7px 0; }
.foot { margin-top:46px; padding-top:18px; border-top:1px solid var(--line);
  color:var(--dim); font-size:13px; }
@media (max-width:640px) {
  .sheet { padding:30px 20px 44px; } h1 { font-size:27px; } body { font-size:16px; }
}
@media print {
  body { background:#fff; } .sheet { max-width:none; padding:0; }
  @page { margin:18mm 16mm; }
  h2 { break-after:avoid; } tr,li,.verdict,.gaps { break-inside:avoid; }
  a { color:var(--ink); }
}
"""

_BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)
_CODE = re.compile(r"`([^`\n]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_BARE = re.compile(r"(?<![\"'>=])(https?://[^\s<>()\[\]]+)")
_HEAD = re.compile(r"^#{1,6}\s*", re.M)
_SCORE = re.compile(r"([А-Яа-яЁё ]{3,20})\s+([▮▯]{3,7})")
_ASSUM = re.compile(r"^\s*([🔴🟡⚪])\s*(\d+)[.)]?\s*(.+)$")


def _inline(text):
    t = html.escape(text)
    t = _LINK.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', t)
    t = _BARE.sub(lambda m: f'<a href="{m.group(1)}">{m.group(1)}</a>', t)
    t = _BOLD.sub(lambda m: f"<b>{m.group(1)}</b>", t)
    t = _CODE.sub(lambda m: f"<code>{m.group(1)}</code>", t)
    return t


def _body(text, drop=()):
    """Markdown-lite -> paragraphs. `drop` filters out lines already shown elsewhere."""
    out = []
    for block in _HEAD.sub("", text.strip()).split("\n\n"):
        lines = [ln for ln in block.split("\n")
                 if ln.strip() and not any(d(ln) for d in drop)]
        if lines:
            out.append("<p>" + "<br>".join(_inline(ln) for ln in lines) + "</p>")
    return "\n".join(out)


def _scores(text):
    out = []
    for name, bar in _SCORE.findall(text):
        out.append((name.strip(), bar.count("▮"), len(bar)))
    return out


def _assumptions(text):
    out = []
    for line in text.split("\n"):
        m = _ASSUM.match(line)
        if m:
            out.append((m.group(1), m.group(2), m.group(3).strip()))
    return out


def _sources(rows):
    if not rows:
        return ""
    items = "".join(f'<li><a href="{html.escape(u)}">{html.escape(t)[:110]}</a></li>'
                    for t, u in rows)
    return f'<div class="src">Источники:<ol>{items}</ol></div>'


async def _answers_html(idea_id):
    rows = [q for q in await db.get_questions(idea_id) if (q["answer"] or "").strip()]
    if not rows:
        return ""
    body = "".join(f"<div><b>{html.escape(q['text'])}</b> — {html.escape(q['answer'])}</div>"
                   for q in rows)
    return f'<div class="answers">{body}</div>'


GAPS = """<div class="gaps"><h3 style="margin:0">На что этот отчёт не отвечает</h3>
<p style="margin:8px 0 0;color:#5c5c5c;font-size:15px">Разбор говорит, стоит ли браться.
Он не говорит, как именно это открыть:</p>
<ul>
<li>сколько денег нужно точно — по статьям, с точкой безубыточности и сроком окупаемости;</li>
<li>что оформить и в какой последовательности — режим, разрешения, проверки, касса;</li>
<li>где брать оборудование и почём, что взять б/у, а что арендовать;</li>
<li>что делать в первые два месяца — по неделям, с точками остановки.</li>
</ul></div>"""


async def build(idea):
    rows = await db.get_steps(idea["id"])
    by_key = {r["step_key"]: r for r in rows}
    verdict = (idea["verdict"] or "").upper()
    color, word, blurb = VERDICT_STYLE.get(verdict, ("#5c5c5c", "Не закончен",
                                                     "Разбор остановлен на середине."))
    title = html.escape(idea["title"] or "Разбор идеи")
    mode = "полный разбор" if idea["mode"] != "fast" else "быстрый разбор"

    shape = PROFILE_TITLE.get(idea.get("profile") or "online", "")
    parts = [f'<div class="sheet"><h1>{title}</h1>',
             f'<p class="lede">{shape} · {mode} · {len(rows)} из '
             f'{8 if idea["mode"] != "fast" else 5} шагов · '
             f'{datetime.now().strftime("%d.%m.%Y")}</p>']

    parts.append(f'<div class="verdict"><div class="word">Вердикт</div>'
                 f'<div class="val">{verdict or "—"} · {word}</div>'
                 f'<div class="why">{blurb}</div></div>')

    final = by_key.get("verdict")
    scores = _scores(final["content"]) if final else []
    if scores:
        cells = "".join(
            f'<div class="score"><div class="name">{html.escape(n)}</div><div class="bar">'
            + "".join(f'<i class="{"on" if i < f else ""}"></i>' for i in range(t))
            + "</div></div>" for n, f, t in scores)
        parts.append(f'<div class="scores">{cells}</div>')

    parts.append('<hr class="rule"><h3 style="margin:0 0 10px">Идея, как она была описана</h3>')
    parts.append(f"<p>{_inline(idea['raw'])}</p>")
    parts.append(await _answers_html(idea["id"]))

    toc = "".join(f'<li><a href="#s{r["num"]}">'
                  f'{html.escape(BY_KEY[r["step_key"]].title if r["step_key"] in BY_KEY else r["step_key"])}'
                  f"</a></li>" for r in rows)
    parts.append(f'<div class="toc ui"><ol>{toc}</ol></div>')

    for r in rows:
        step = BY_KEY.get(r["step_key"])
        name = html.escape(step.title if step else r["step_key"])
        parts.append(f'<h2 id="s{r["num"]}"><span class="num">{r["num"]} · </span>{name}</h2>')

        drop = []
        if r["step_key"] == "assumptions":
            items = _assumptions(r["content"])
            if len(items) >= 3:
                trs = "".join(
                    f'<tr><td class="m" title="{MARK_TITLE.get(m, "")}">{m}</td>'
                    f'<td class="k">{MARK_TITLE.get(m, "")}</td>'
                    f"<td>{_inline(t)}</td></tr>" for m, _n, t in items)
                parts.append("<table><tr><th></th><th>вес</th><th>допущение</th></tr>"
                             f"{trs}</table>")
                drop.append(lambda ln: bool(_ASSUM.match(ln)))
        if r["step_key"] == "verdict" and scores:
            drop.append(lambda ln: "▮" in ln or "▯" in ln)

        parts.append(_body(r["content"], drop))
        parts.append(_sources(r["sources"]))

    parts.append('<hr class="rule">')
    parts.append(GAPS)
    parts.append('<div class="foot">Собрано ботом-разборщиком идей. '
                 'Разбор — не инвестиционная и не юридическая консультация: '
                 'цифры и требования проверяй по первоисточникам.</div>')
    parts.append("</div>")

    doc = ("<!doctype html><html lang=\"ru\"><head><meta charset=\"utf-8\">"
           "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
           "<meta name=\"robots\" content=\"noindex\">"
           f"<title>{title}</title><style>{CSS}</style></head><body>"
           + "\n".join(p for p in parts if p) + "</body></html>")

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / f"razbor-{idea['id']}.html"
    path.write_text(doc, encoding="utf-8")
    return path
