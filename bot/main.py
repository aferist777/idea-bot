import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from . import db
from .config import ANTHROPIC_API_KEY, BOT_TOKEN, MOCK_LLM, MODEL, OPENROUTER_API_KEY
from .handlers import router
from .orders import router as orders_router


async def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN missing in .env")
    if not (ANTHROPIC_API_KEY or OPENROUTER_API_KEY or MOCK_LLM):
        raise SystemExit("ANTHROPIC_API_KEY missing in .env")
    await db.init()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await bot.delete_webhook(drop_pending_updates=True)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(orders_router)   # before the catch-all text handler in `router`
    dp.include_router(router)
    me = await bot.me()
    where = "MOCK (canned answers)" if MOCK_LLM else MODEL
    print(f"idea-bot is running as @{me.username} on {where}. Ctrl+C to stop.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
