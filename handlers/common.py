import logging
from typing import Any, Awaitable, Callable

from aiogram import Router, F
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest

from config import REQUIRED_CHANNEL_ID, REQUIRED_CHANNEL_LINK
from ui_format import get_subscription_required_text, build_subscription_keyboard
from ui_callbacks import NavCallback, PageCallback

logger = logging.getLogger(__name__)

router = Router()

ALLOWED_MEMBER_STATUSES = {"member", "administrator", "creator"}
CHECK_SUBSCRIPTION_CALLBACK = "check_required_subscription"

# --- Middlewares ---

class SubscriptionRequiredMessageMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        # Пропускаем команду /start, чтобы пользователь мог увидеть приветствие
        if event.text and event.text.startswith("/start"):
            return await handler(event, data)

        if not await _has_required_subscription(data["bot"], event.from_user.id):
            await _send_subscription_required(event)
            return

        return await handler(event, data)


class SubscriptionRequiredCallbackMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[CallbackQuery, dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        # Пропускаем сам callback проверки подписки
        if event.data == CHECK_SUBSCRIPTION_CALLBACK:
            return await handler(event, data)

        if not await _has_required_subscription(data["bot"], event.from_user.id):
            await _send_subscription_required(event)
            await event.answer()
            return

        return await handler(event, data)


# --- Helpers ---

async def _has_required_subscription(bot, user_id: int) -> bool:
    if REQUIRED_CHANNEL_ID is None:
        return True # Если не настроено, считаем что ок

    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL_ID, user_id)
    except TelegramBadRequest as exc:
        logger.warning(f"Не удалось проверить подписку пользователя {user_id}: {exc}")
        return False

    return member.status in ALLOWED_MEMBER_STATUSES


async def _send_subscription_required(target: Message | CallbackQuery) -> None:
    text = get_subscription_required_text(REQUIRED_CHANNEL_ID)
    keyboard_data = build_subscription_keyboard(REQUIRED_CHANNEL_LINK)
    
    inline_keyboard = [
        [InlineKeyboardButton(text=btn["text"], url=btn.get("url"), callback_data=btn.get("callback_data"))]
        for btn in keyboard_data
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

    if isinstance(target, Message):
        await target.answer(text, reply_markup=reply_markup)
    elif target.message:
        await target.message.answer(text, reply_markup=reply_markup)


# --- Common Handlers ---

@router.callback_query(F.data == CHECK_SUBSCRIPTION_CALLBACK)
async def cb_check_subscription(callback: CallbackQuery) -> None:
    if await _has_required_subscription(callback.bot, callback.from_user.id):
        await callback.message.answer("✅ Готово. Теперь бот доступен.")
        await callback.message.delete()
    else:
        await callback.answer("Вы еще не подписаны на канал.", show_alert=True)


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()
