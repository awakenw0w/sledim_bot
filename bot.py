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
from telegram_monitor import run_telegram_monitor
from telegram_resolver import close_telegram_resolver
from tracker import run_tracker
from outbox_worker import run_outbox_worker

# Настройка логирования: уровень INFO, формат с временем и именем модуля
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def _await_background_task(task: asyncio.Task, name: str) -> None:
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.exception("Фоновая задача %s завершилась с ошибкой во время остановки: %s", name, exc)


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
    telegram_monitor_task = asyncio.create_task(run_telegram_monitor(bot))
    outbox_task = asyncio.create_task(run_outbox_worker(bot))
    logger.info("Бот запущен. Ожидаю сообщения...")

    try:
        # Запускаем polling (бесконечный цикл получения обновлений от Telegram)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except asyncio.CancelledError:
        logger.info("Получен запрос на остановку polling, начинаю завершение фоновых задач.")
    finally:
        # При остановке (Ctrl+C или другой сигнал) отменяем задачи трекеров и воркера
        tracker_task.cancel()
        telegram_monitor_task.cancel()
        outbox_task.cancel()
        await _await_background_task(tracker_task, "tracker")
        await _await_background_task(telegram_monitor_task, "telegram_monitor")
        await _await_background_task(outbox_task, "outbox_worker")
        await close_telegram_resolver()
        await db.close_db()
        await bot.session.close()
        logger.info("Бот остановлен.")
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Получен сигнал прерывания, завершение работы.")

