import asyncio
import logging
import time

from aiogram import Bot
from aiogram.exceptions import (
    TelegramRetryAfter,
    TelegramForbiddenError,
    TelegramAPIError,
    TelegramNetworkError,
    TelegramBadRequest
)

import db

logger = logging.getLogger(__name__)

# Максимальное количество попыток до перевода в failed
MAX_ATTEMPTS = 5
OUTBOX_WORKER_INTERVAL = 1.0  # сек между циклами


async def run_outbox_worker(bot: Bot) -> None:
    """Фоновый воркер, который просыпается и рассылает outbox-сообщения."""
    logger.info("Outbox Worker запущен")
    
    while True:
        try:
            pending_messages = await db.get_pending_outbox_messages(limit=30)
            if not pending_messages:
                await asyncio.sleep(OUTBOX_WORKER_INTERVAL)
                continue

            for msg in pending_messages:
                msg_id = msg["id"]
                chat_id = msg["chat_id"]
                text = msg["text"]
                parse_mode = msg["parse_mode"]
                disable_preview = msg["disable_preview"]
                attempt_count = msg["attempt_count"]

                now_ts = int(time.time())

                if attempt_count >= MAX_ATTEMPTS:
                    logger.warning("Message ID %s: превышен лимит попыток (%s). Снято с очереди.", msg_id, MAX_ATTEMPTS)
                    await db.mark_outbox_message_failed(msg_id, "Max attempts reached")
                    continue

                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode=parse_mode,
                        disable_web_page_preview=disable_preview,
                    )
                    await db.mark_outbox_message_sent(msg_id)
                    logger.debug("Outbox Message ID %s отправлено", msg_id)

                    # Небольшой sleep, чтобы не упереться в Telegram Broadcast Limits (30 messages per second)
                    await asyncio.sleep(0.05)

                except TelegramRetryAfter as e:
                    # FloodWait – это не критично, просто ждем
                    retry_after = e.retry_after
                    logger.warning("Message ID %s: FloodWait от TG на %s сек", msg_id, retry_after)
                    next_retry_at = now_ts + retry_after + 1
                    await db.schedule_outbox_message_retry(msg_id, next_retry_at, attempt_count + 1, str(e))
                    
                except TelegramForbiddenError as e:
                    # Пользователь заблокировал бота, retry не поможет
                    logger.warning("Message ID %s: Пользователь заблокировал бота (%s). Mark as failed.", msg_id, chat_id)
                    await db.mark_outbox_message_failed(msg_id, "Forbidden: bot was blocked by the user")

                except (TelegramNetworkError, TelegramAPIError) as e:
                    # Временные сбои (Timeout, Bad Gateway, и другие сетевые проблемы)
                    delay = min(3600, (2 ** attempt_count) * 5)
                    logger.error("Message ID %s: Временная ошибка сети: %s. Retry через %s сек", msg_id, e, delay)
                    next_retry_at = now_ts + delay
                    await db.schedule_outbox_message_retry(msg_id, next_retry_at, attempt_count + 1, str(e))

                except TelegramBadRequest as e:
                    # Неверный запрос (например, chat not found или markdown err), retry не поможет
                    logger.error("Message ID %s: BadRequest (возможно удаленный чат или битая разметка): %s. Mark as failed.", msg_id, e)
                    await db.mark_outbox_message_failed(msg_id, f"BadRequest: {e}")
                    
                except Exception as e:
                    # Неизвестная ошибка
                    delay = min(3600, (2 ** attempt_count) * 5)
                    logger.exception("Message ID %s: Неизвестная ошибка при отправке: %s", msg_id, e)
                    next_retry_at = now_ts + delay
                    await db.schedule_outbox_message_retry(msg_id, next_retry_at, attempt_count + 1, str(e))

            await asyncio.sleep(OUTBOX_WORKER_INTERVAL)

        except asyncio.CancelledError:
            logger.info("Outbox worker остановлен по запросу отмены.")
            break
        except Exception as e:
            logger.error("Глобальная ошибка в Outbox worker'е: %s", e)
            await asyncio.sleep(5.0)
