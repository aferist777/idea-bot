from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .config import FAST_COST, FULL_COST, LAUNCH_PRICE, TOPUP_PACKAGES

VERDICT_MARK = {"GO": "🟢", "PIVOT": "🟡", "KILL": "🔴"}


def _kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu():
    return _kb([
        [InlineKeyboardButton(text="🧨 Разобрать идею", callback_data="new")],
        [InlineKeyboardButton(text="📂 Мои разборы", callback_data="list")],
        [InlineKeyboardButton(text="💳 Баланс", callback_data="balance"),
         InlineKeyboardButton(text="❓ Как это работает", callback_data="how")],
    ])


def describe_kb(chars, thin=False):
    """Shown while the user is still writing the idea; they decide when it's enough."""
    head = "✅ Готово, разбирай" if not thin else "✅ Всё равно начать"
    return _kb([
        [InlineKeyboardButton(text=f"{head} · {chars} симв.", callback_data="described")],
        [InlineKeyboardButton(text="🗑 Написать заново", callback_data="redescribe")],
        [InlineKeyboardButton(text="← Отмена", callback_data="menu")],
    ])


def profile_kb():
    """What shape of business this is - it changes the tone and every step's angle."""
    return _kb([
        [InlineKeyboardButton(text="🏪 Точка с помещением", callback_data="prof:place")],
        [InlineKeyboardButton(text="🚗 Услуга без помещения", callback_data="prof:local")],
        [InlineKeyboardButton(text="💻 Онлайн-продукт", callback_data="prof:online")],
    ])


def mode_kb():
    return _kb([
        [InlineKeyboardButton(text=f"🔬 Полный · 8 шагов · {FULL_COST}⭐", callback_data="mode:full")],
        [InlineKeyboardButton(text=f"⚡ Быстрый · 5 шагов · {FAST_COST}⭐", callback_data="mode:fast")],
        [InlineKeyboardButton(text="← Отмена", callback_data="menu")],
    ])


def web_kb(idea_id):
    return _kb([
        [InlineKeyboardButton(text="🔍 С поиском в интернете", callback_data=f"go:{idea_id}:1")],
        [InlineKeyboardButton(text="Без поиска, по памяти", callback_data=f"go:{idea_id}:0")],
    ])


def gate_kb(idea_id, last=False):
    rows = [[
        InlineKeyboardButton(text="✅ Вердикт" if last else "✅ Дальше", callback_data=f"next:{idea_id}"),
        InlineKeyboardButton(text="✎ Поправить", callback_data=f"fix:{idea_id}"),
    ], [InlineKeyboardButton(text="⏸ Пауза", callback_data=f"pause:{idea_id}")]]
    return _kb(rows)


def final_kb(idea_id):
    return _kb([
        [InlineKeyboardButton(text="📄 Забрать разбор страницей", callback_data=f"file:{idea_id}")],
        [InlineKeyboardButton(text="🧨 Разобрать ещё одну", callback_data="new")],
        [InlineKeyboardButton(text="← Меню", callback_data="menu")],
    ])


def ideas_kb(ideas, total_of):
    rows = []
    for i in ideas:
        if i["verdict"]:
            mark = VERDICT_MARK.get(i["verdict"], "✅")
            tail = i["verdict"]
        else:
            mark = "⏸"
            tail = f"{i['idx']}/{total_of(i['mode'])}"
        title = (i["title"] or i["raw"])[:38]
        rows.append([InlineKeyboardButton(text=f"{mark} {title} · {tail}",
                                          callback_data=f"open:{i['id']}")])
    rows.append([InlineKeyboardButton(text="← Меню", callback_data="menu")])
    return _kb(rows)


def question_kb(q, idea_id):
    """Model-generated options, plus a free-text escape and two ways out."""
    rows = [[InlineKeyboardButton(text=opt, callback_data=f"ans:{q['id']}:{i}")]
            for i, opt in enumerate(q["options"])]
    rows.append([InlineKeyboardButton(text="✍️ Своими словами",
                                      callback_data=f"askfree:{q['id']}")])
    rows.append([InlineKeyboardButton(text="→ Пропустить", callback_data=f"askskip:{q['id']}"),
                 InlineKeyboardButton(text="→ Пропустить всё", callback_data=f"askall:{idea_id}")])
    return _kb(rows)


def retry_kb(idea_id):
    return _kb([
        [InlineKeyboardButton(text="🔄 Повторить шаг", callback_data=f"resume:{idea_id}")],
        [InlineKeyboardButton(text="⏸ Отложить", callback_data=f"pause:{idea_id}")],
    ])


def idea_kb(idea, done, admin=False):
    rows = []
    if not done:
        rows.append([InlineKeyboardButton(text="▶ Продолжить разбор",
                                          callback_data=f"resume:{idea['id']}")])
    rows.append([InlineKeyboardButton(text="📄 Отчёт", callback_data=f"file:{idea['id']}"),
                 InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del:{idea['id']}")])
    if admin:
        rows.append([InlineKeyboardButton(text="⬇️ Markdown", callback_data=f"md:{idea['id']}")])
    rows.append([InlineKeyboardButton(text="← К списку", callback_data="list")])
    return _kb(rows)


def confirm_del_kb(idea_id):
    return _kb([
        [InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"delyes:{idea_id}"),
         InlineKeyboardButton(text="Отмена", callback_data=f"open:{idea_id}")],
    ])


def launch_kb(idea_id):
    return _kb([
        [InlineKeyboardButton(text=f"🚀 Запуск · {LAUNCH_PRICE} ₽",
                              callback_data=f"launch:{idea_id}")],
    ])


def pay_kb(order_id):
    return _kb([
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"claim:{order_id}")],
        [InlineKeyboardButton(text="Отмена", callback_data=f"cancelord:{order_id}")],
    ])


def admin_order_kb(order_id):
    return _kb([
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"ordok:{order_id}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"ordno:{order_id}")],
    ])


def topup_kb():
    rows = [[InlineKeyboardButton(text=f"{n}⭐", callback_data=f"buy:{n}")]
            for n in TOPUP_PACKAGES]
    rows.append([InlineKeyboardButton(text="← Меню", callback_data="menu")])
    return _kb(rows)
