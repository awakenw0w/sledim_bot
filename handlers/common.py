import logging
from typing import Any, Awaitable, Callable

from aiogram import Router, F
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import Message, CallbackQuery, ErrorEvent
from aiogram.exceptions import TelegramBadRequest

logger = logging.getLogger(__name__)

router = Router()

CHECK_SUBSCRIPTION_CALLBACK = "check_required_subscription"


def _is_stale_callback_error(exc: TelegramBadRequest) -> bool:
    message = str(exc).casefold()
    return (
        "query is too old" in message
        or "query id is invalid" in message
        or "response timeout expired" in message
    )


async def safe_answer_callback(callback: CallbackQuery, *args, **kwargs) -> bool:
    try:
        await callback.answer(*args, **kwargs)
        return True
    except TelegramBadRequest as exc:
        if _is_stale_callback_error(exc):
            logger.info("Игнорируем устаревший callback query: %s", callback.data)
            return False
        raise

# --- Middlewares ---

class SubscriptionRequiredMessageMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        return await handler(event, data)


class SubscriptionRequiredCallbackMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[CallbackQuery, dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        return await handler(event, data)


# --- Helpers ---

async def _has_required_subscription(bot, user_id: int) -> bool:
    return True


async def _send_subscription_required(target: Message | CallbackQuery) -> None:
    if isinstance(target, Message):
        await target.answer("Бот доступен без обязательной подписки.")
    elif target.message:
        await target.message.answer("Бот доступен без обязательной подписки.")


# --- Common Handlers ---

@router.callback_query(F.data == CHECK_SUBSCRIPTION_CALLBACK)
async def cb_check_subscription(callback: CallbackQuery) -> None:
    await safe_answer_callback(callback, "Обязательная подписка отключена.", show_alert=False)
    if callback.message:
        await callback.message.answer("✅ Бот доступен без обязательной подписки.")


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await safe_answer_callback(callback)


@router.errors()
async def cb_ignore_stale_callback_error(event: ErrorEvent) -> bool | None:
    exc = event.exception
    if not isinstance(exc, TelegramBadRequest):
        return None
    if not _is_stale_callback_error(exc):
        return None

    callback_data = None
    if event.update.callback_query is not None:
        callback_data = event.update.callback_query.data
    logger.info("Пойман устаревший callback query, ошибка подавлена: %s", callback_data)
    return True

