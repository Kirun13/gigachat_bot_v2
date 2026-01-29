"""
Точка входа для бота.
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

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)


async def main():
    """Главная функция запуска бота."""
    
    # Проверка токена
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен! Создайте .env файл с BOT_TOKEN=...")
        sys.exit(1)
    
    # Создание директории для базы данных
    db_path = Path(DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Инициализация базы данных
    logger.info("Инициализация базы данных...")
    await init_database()
    
    # Создание бота и диспетчера
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    
    # Регистрация обработчиков
    dp.include_router(commands.router)
    dp.include_router(messages.router)
    
    # Запуск
    logger.info("Бот запускается...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
