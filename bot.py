"""
Точка входа — запускает Telegram-бота и фоновый трекер VK.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import TELEGRAM_BOT_TOKEN
import db
from handlers import router
from telegram_resolver import close_telegram_resolver
from tracker import run_tracker

# Настройка логирования: уровень INFO, формат с временем и именем модуля
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)



async def main() -> None:
    """Инициализация и запуск бота вместе с трекером."""

    # Инициализируем базу данных (создаём таблицы, если нужно)
    logger.info("Инициализация базы данных...")
    await db.init_db()

    # Создаём объект бота с HTML как режимом разметки по умолчанию
    bot = Bot(
        token=TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Создаём диспетчер и регистрируем роутер с хэндлерами
    dp = Dispatcher()
    dp.include_router(router)

    # Запускаем трекер как фоновую asyncio-задачу
    tracker_task = asyncio.create_task(run_tracker(bot))
    logger.info("Бот запущен. Ожидаю сообщения...")

    try:
        # Запускаем polling (бесконечный цикл получения обновлений от Telegram)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        # При остановке (Ctrl+C или другой сигнал) отменяем задачу трекера
        tracker_task.cancel()
        try:
            await tracker_task
        except asyncio.CancelledError:
            pass
        await close_telegram_resolver()
        await bot.session.close()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания, завершение работы.")
