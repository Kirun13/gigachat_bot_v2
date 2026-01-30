"""
Bot entry point.
"""

import asyncio
import logging
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import BOT_TOKEN, DATABASE_PATH
from bot.db import init_database
from bot.handlers import commands, messages

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


async def main():
    """Main bot startup function."""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set! Create .env file with BOT_TOKEN=...")
        sys.exit(1)
    
    db_path = Path(DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info("Initializing database...")
    await init_database()
    
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    
    dp.include_router(commands.router)
    dp.include_router(messages.router)
    
    logger.info("Bot starting...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
