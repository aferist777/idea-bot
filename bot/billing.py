"""Stars, free runs, referrals.

Charged once, when an analysis starts. A paid-for teardown can then be paused and
resumed forever, and "поправить" is free up to REGEN_LIMIT per step.
"""
from . import db
from .config import ADMIN_ID, FAST_COST, FULL_COST, REFERRAL_REWARD


def is_admin(tg_id):
    return tg_id == ADMIN_ID


def cost(mode):
    return FAST_COST if mode == "fast" else FULL_COST


async def charge_run(user, tg_id, mode):
    """(ok, how): admin / free_run / balance / need_topup."""
    if is_admin(tg_id):
        return True, "admin"
    if (user.get("free_runs") or 0) > 0:
        await db.add_free_runs(tg_id, -1)
        await db.add_tx(tg_id, "spend", 0, f"разбор ({mode}, бесплатный)")
        return True, "free_run"
    price = cost(mode)
    if (user.get("balance") or 0) >= price:
        await db.add_balance(tg_id, -price, "spend", f"разбор ({mode})")
        return True, "balance"
    return False, "need_topup"


async def apply_topup(tg_id, n):
    await db.add_balance(tg_id, n, "topup", f"пополнение {n}⭐")


async def maybe_qualify_referral(tg_id):
    """Call once the referee reaches a verdict; pays the referrer a single time."""
    ref = await db.qualify_referral(tg_id)
    if ref:
        await db.add_free_runs(ref, REFERRAL_REWARD)
        await db.add_tx(ref, "referral", 0, f"+{REFERRAL_REWARD} разбор за друга")
    return ref
