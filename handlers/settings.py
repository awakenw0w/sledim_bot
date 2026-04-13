import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

import db
from ui_keyboards import notification_settings_keyboard, tg_notification_settings_keyboard
from ui_callbacks import (
    NavCallback,
    NotifyModeCallback, 
    NotifyToggleCallback,
    TgNotifyModeCallback,
    TgNotifyToggleCallback
)
from ui_format import (
    NOTIFICATION_MODE_LABELS, 
    CHANGE_NOTIFICATION_LABELS, 
    TG_CHANGE_NOTIFICATION_LABELS,
    TG_NOTIFICATION_TOGGLE_LABELS,
    escape_html
)

logger = logging.getLogger(__name__)

router = Router()

# --- Helpers ---

async def _show_vk_notification_settings(callback: CallbackQuery, text: str | None = None) -> None:
    chat_id = callback.message.chat.id
    current_mode = await db.get_notification_mode(chat_id)
    change_settings = await db.get_change_notification_settings(chat_id)
    
    await callback.message.answer(
        text or (
            "<b>Уведомления • ВКонтакте</b>\n"
            "Выберите, о чем сообщать."
        ),
        reply_markup=notification_settings_keyboard(current_mode, change_settings, back_target="notification_hub")
    )


async def _show_tg_notification_settings(callback: CallbackQuery, text: str | None = None) -> None:
    chat_id = callback.message.chat.id
    current_mode = await db.get_tg_notification_mode(chat_id)
    activity_enabled = await db.get_tg_activity_notification_enabled(chat_id)
    change_settings = await db.get_tg_change_notification_settings(chat_id)
    
    await callback.message.answer(
        text or (
            "<b>Уведомления • Telegram</b>\n"
            "Выберите, о чем сообщать."
        ),
        reply_markup=tg_notification_settings_keyboard(
            current_mode, 
            activity_enabled, 
            change_settings, 
            back_target="notification_hub"
        )
    )


# --- Handlers ---

@router.callback_query(NavCallback.filter(F.target == "notify_vk"))
async def cb_nav_notify_vk(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _show_vk_notification_settings(callback)
    await callback.message.delete()
    await callback.answer()


@router.callback_query(NavCallback.filter(F.target == "notify_tg"))
async def cb_nav_notify_tg(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _show_tg_notification_settings(callback)
    await callback.message.delete()
    await callback.answer()


@router.callback_query(NotifyModeCallback.filter())
async def cb_vk_notify_mode(callback: CallbackQuery, callback_data: NotifyModeCallback) -> None:
    mode = await db.set_notification_mode(callback.message.chat.id, callback_data.mode)
    label = NOTIFICATION_MODE_LABELS.get(mode, mode)
    await callback.message.delete()
    await _show_vk_notification_settings(callback, text=f"✅ Режим обновлен: <b>{label}</b>")
    await callback.answer()


@router.callback_query(NotifyToggleCallback.filter())
async def cb_vk_notify_toggle(callback: CallbackQuery, callback_data: NotifyToggleCallback) -> None:
    enabled = await db.toggle_change_notification(callback.message.chat.id, callback_data.key)
    label = CHANGE_NOTIFICATION_LABELS.get(callback_data.key, callback_data.key)
    status = "включены" if enabled else "отключены"
    await callback.message.delete()
    await _show_vk_notification_settings(callback, text=f"✅ <b>{escape_html(label)}</b>: {status}.")
    await callback.answer()


@router.callback_query(TgNotifyModeCallback.filter())
async def cb_tg_notify_mode(callback: CallbackQuery, callback_data: TgNotifyModeCallback) -> None:
    mode = await db.set_tg_notification_mode(callback.message.chat.id, callback_data.mode)
    label = NOTIFICATION_MODE_LABELS.get(mode, mode)
    await callback.message.delete()
    await _show_tg_notification_settings(callback, text=f"✅ Режим обновлен: <b>{label}</b>")
    await callback.answer()


@router.callback_query(TgNotifyToggleCallback.filter())
async def cb_tg_notify_toggle(callback: CallbackQuery, callback_data: TgNotifyToggleCallback) -> None:
    chat_id = callback.message.chat.id
    if callback_data.key == "activity":
        enabled = await db.toggle_tg_activity_notification(chat_id)
        label = TG_NOTIFICATION_TOGGLE_LABELS["activity"]
    else:
        enabled = await db.toggle_tg_change_notification(chat_id, callback_data.key)
        label = TG_CHANGE_NOTIFICATION_LABELS.get(callback_data.key, callback_data.key)
    
    status = "включены" if enabled else "отключены"
    await callback.message.delete()
    await _show_tg_notification_settings(callback, text=f"✅ <b>{escape_html(label)}</b>: {status}.")
    await callback.answer()
