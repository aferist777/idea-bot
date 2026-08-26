"""The paid "Запуск" track, settled by hand.

Bot issues an invoice with a code, the buyer transfers money and taps "Я оплатил",
the admin confirms in his own chat. No payment provider involved - which is fine for
the first dozen sales and honest about what it is.
"""
import html

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from . import billing, db
from .config import ADMIN_ID, LAUNCH_ENABLED, LAUNCH_PRICE, PAY_DETAILS, PAY_NAME
from .keyboards import admin_order_kb, main_menu, pay_kb

router = Router()

PRODUCT = "launch"

OFFER = (
    "🚀 <b>Запуск</b> — {price} ₽\n\n"
    "Разбор отвечает, стоит ли браться. «Запуск» отвечает, как именно это открыть:\n\n"
    "• <b>Финмодель</b> — вложения по статьям, постоянка, точка безубыточности "
    "в чеках за день, три сценария и таблица на год\n"
    "• <b>Локация</b> — поток, аренда по району, соседи и якоря рядом\n"
    "• <b>Юридический чек-лист</b> — режим, разрешения, проверки, касса, "
    "порядок и сроки, со ссылками на первоисточники\n"
    "• <b>Смета и поставщики</b> — что купить, почём, где, что взять б/у\n"
    "• <b>План 60 дней</b> — по неделям, с точками «стоп, если не вышло»\n\n"
    "Всё приходит отдельными печатными отчётами. По дороге я задам вопросы "
    "по твоему делу и попрошу принести пару своих цифр — так точнее.\n\n"
    "⚠️ Это не юридическая и не инвестиционная консультация: суммы и требования "
    "проверяй по первоисточникам, ссылки будут."
)


def _order_line(o):
    who = f"@{o['username']}" if o.get("username") else f"id{o['tg_id']}"
    return (f"#{o['id']} · {who} · разбор {o['idea_id']} · "
            f"{o['amount']} ₽ · {o['status']}")


@router.callback_query(F.data.startswith("launch:"))
async def cb_launch(cb: CallbackQuery):
    idea_id = int(cb.data.split(":")[1])
    idea = await db.get_idea(idea_id)
    if not idea or idea["tg_id"] != cb.from_user.id:
        await cb.answer("Не найдено", show_alert=True)
        return
    if await db.has_paid(cb.from_user.id, idea_id, PRODUCT):
        await cb.message.answer("По этому разбору «Запуск» уже оплачен.")
        await cb.answer()
        return

    if not PAY_DETAILS:
        await cb.message.answer(
            "Реквизиты не заданы — заполни PAY_DETAILS в .env, иначе платить некуда.")
        await cb.answer()
        return

    order = await db.create_order(cb.from_user.id, cb.from_user.username, idea_id,
                                  PRODUCT, LAUNCH_PRICE)
    await cb.message.answer(
        OFFER.format(price=LAUNCH_PRICE) + "\n\n"
        f"<b>Счёт №{order['id']}</b>\n"
        f"Перевод: <code>{html.escape(PAY_DETAILS)}</code>\n"
        + (f"Получатель: {html.escape(PAY_NAME)}\n" if PAY_NAME else "")
        + f"Сумма: <b>{order['amount']} ₽</b>\n"
        f"В комментарии укажи: <code>заказ {order['id']}</code>\n\n"
        "Перевёл — жми кнопку. Я проверю вручную и отпишусь; обычно в течение дня.",
        reply_markup=pay_kb(order["id"]))
    await cb.answer()


@router.callback_query(F.data.startswith("claim:"))
async def cb_claim(cb: CallbackQuery):
    order = await db.get_order(int(cb.data.split(":")[1]))
    if not order or order["tg_id"] != cb.from_user.id:
        await cb.answer("Счёт не найден", show_alert=True)
        return
    if order["status"] == "paid":
        await cb.answer("Этот счёт уже подтверждён", show_alert=True)
        return
    await db.set_order_status(order["id"], "claimed")
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cb.message.answer(
        f"Принял. Счёт №{order['id']} на проверке — напишу, как увижу платёж.",
        reply_markup=main_menu())
    await cb.answer()

    idea = await db.get_idea(order["idea_id"])
    who = f"@{cb.from_user.username}" if cb.from_user.username else f"id{cb.from_user.id}"
    await cb.bot.send_message(
        ADMIN_ID,
        f"💰 <b>Заявка на оплату</b>\n\n"
        f"Счёт №{order['id']} · {order['amount']} ₽\n"
        f"От: {who} (id{cb.from_user.id})\n"
        f"Разбор: {html.escape((idea or {}).get('title') or '—')}\n"
        f"Вердикт: {(idea or {}).get('verdict') or '—'}\n\n"
        "Проверь поступление и подтверди.",
        reply_markup=admin_order_kb(order["id"]))


@router.callback_query(F.data.startswith("cancelord:"))
async def cb_cancel_order(cb: CallbackQuery):
    order = await db.get_order(int(cb.data.split(":")[1]))
    if order and order["tg_id"] == cb.from_user.id and order["status"] != "paid":
        await db.set_order_status(order["id"], "canceled")
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cb.answer("Отменено")


# ---------------- admin side ----------------
@router.callback_query(F.data.startswith("ordok:"))
async def cb_order_ok(cb: CallbackQuery):
    if not billing.is_admin(cb.from_user.id):
        await cb.answer("Не для тебя", show_alert=True)
        return
    order = await db.get_order(int(cb.data.split(":")[1]))
    if not order:
        await cb.answer("Счёт не найден", show_alert=True)
        return
    await db.set_order_status(order["id"], "paid")
    await db.add_tx(order["tg_id"], "launch", order["amount"], f"Запуск, счёт {order['id']}")
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cb.message.answer(f"✅ Счёт №{order['id']} подтверждён.")
    await cb.answer()
    await cb.bot.send_message(
        order["tg_id"],
        f"✅ Оплата по счёту №{order['id']} подтверждена. Начинаем «Запуск» — "
        "первым будет финмодель, задам несколько вопросов по твоим цифрам.")


@router.callback_query(F.data.startswith("ordno:"))
async def cb_order_no(cb: CallbackQuery):
    if not billing.is_admin(cb.from_user.id):
        await cb.answer("Не для тебя", show_alert=True)
        return
    order = await db.get_order(int(cb.data.split(":")[1]))
    if not order:
        await cb.answer("Счёт не найден", show_alert=True)
        return
    await db.set_order_status(order["id"], "rejected")
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cb.message.answer(f"❌ Счёт №{order['id']} отклонён.")
    await cb.answer()
    await cb.bot.send_message(
        order["tg_id"],
        f"Не нашёл платёж по счёту №{order['id']}. Если платил — напиши мне, разберёмся.")


@router.message(Command("orders"))
async def cmd_orders(m: Message):
    if not billing.is_admin(m.from_user.id):
        return
    rows = await db.list_orders()
    if not rows:
        await m.answer("Заявок пока нет.")
        return
    waiting = [o for o in rows if o["status"] == "claimed"]
    text = "<b>Последние счета</b>\n\n" + "\n".join(_order_line(o) for o in rows)
    await m.answer(text)
    for o in waiting:
        await m.answer(f"Ждёт проверки: {_order_line(o)}", reply_markup=admin_order_kb(o["id"]))


def offer_visible(tg_id):
    """While the artefacts don't exist, only the admin may see the offer."""
    return LAUNCH_ENABLED or billing.is_admin(tg_id)
