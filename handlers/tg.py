import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, SharedUser

import db
from telegram_resolver import (
    resolve_telegram_user,
    normalize_telegram_lookup,
    TelegramResolverInvalidInputError,
    TelegramResolverNotFoundError,
    TelegramResolverPeerTypeError,
    TelegramResolverUnavailableError,
)
from ui_keyboards import (
    main_menu_keyboard,
    tg_add_user_reply_keyboard,
    tg_tracked_list_paginated_keyboard,
    tg_user_card_keyboard,
    tg_delete_confirm_keyboard,
    back_main_inline_keyboard
)
from ui_callbacks import (
    NavCallback,
    PageCallback,
    TgUserActionCallback,
    TgDeleteConfirmCallback
)
from ui_states import AddUserStates
from ui_format import (
    escape_html,
    format_tg_profile_card,
    build_tg_button_label,
    build_tg_display_name,
    format_added_at,
    build_tg_status_label,
    build_tg_activity_line
)

logger = logging.getLogger(__name__)

router = Router()

# --- Helpers ---

async def _remember_telegram_user(user) -> None:
    if not user:
        return
    await db.upsert_tg_known_user(
        telegram_user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        profile_link=f"tg://user?id={user.id}",
        is_bot=user.is_bot,
    )


async def _show_tg_list(message: Message, page: int = 1, source: str = "tg_list") -> None:
    tg_users = await db.get_tg_tracked_users_details(message.chat.id)
    if not tg_users:
        await message.answer(
            "<b>Список • Telegram</b>\n"
            "Пока здесь пусто. Добавьте первого пользователя.",
            reply_markup=main_menu_keyboard(),
        )
        return

    page_size = 5
    total_pages = (len(tg_users) + page_size - 1) // page_size
    page = max(1, min(page, total_pages))
    
    start_idx = (page - 1) * page_size
    chunk = tg_users[start_idx : start_idx + page_size]
    
    lines = ["<b>Список • Telegram</b>"]
    if total_pages > 1:
        lines.append(f"Страница {page} из {total_pages}")
    for item in chunk:
        display_name = build_tg_display_name(item)
        username = str(item.get("username") or "").strip()
        user_lines = [
            f"👤 <b>{escape_html(display_name)}</b>",
            f"ID: <code>{item['telegram_user_id']}</code>",
        ]
        if username:
            user_lines.append(f"Ник: <code>@{escape_html(username)}</code>")
        user_lines.append(f"В списке с: {format_added_at(item.get('added_at'))}")
        lines.append("\n".join(user_lines))

    text = "\n\n".join(lines)
    keyboard = tg_tracked_list_paginated_keyboard(
        [{**item, "button_label": build_tg_button_label(item)} for item in chunk],
        page=page,
        total_pages=total_pages,
        source=source
    )
    await message.answer(text, reply_markup=keyboard)


async def _perform_add_tg_user(message: Message, tg_user: dict) -> None:
    source_value = str(tg_user.get("lookup_value") or tg_user.get("username") or tg_user["telegram_user_id"])
    username = str(tg_user.get("username") or "").strip() or None
    profile_link = str(tg_user.get("profile_link") or "").strip() or None
    if profile_link is None:
        profile_link = f"https://t.me/{username}" if username else f"tg://user?id={int(tg_user['telegram_user_id'])}"

    await db.upsert_tg_known_user(
        telegram_user_id=int(tg_user["telegram_user_id"]),
        username=username,
        first_name=tg_user.get("first_name"),
        last_name=tg_user.get("last_name"),
        access_hash=tg_user.get("access_hash"),
        profile_link=profile_link,
        avatar_photo_id=tg_user.get("avatar_photo_id"),
        avatar_dc_id=tg_user.get("avatar_dc_id"),
        avatar_has_video=bool(tg_user.get("avatar_has_video", False)),
        gifts_count=tg_user.get("gifts_count"),
        gifts_supported=tg_user.get("gifts_supported"),
        is_bot=False,
    )
    await db.sync_tg_tracked_user_profile(
        int(tg_user["telegram_user_id"]),
        username=username,
        first_name=tg_user.get("first_name"),
        last_name=tg_user.get("last_name"),
    )

    if tg_user.get("status_text") or tg_user.get("last_seen_at") is not None:
        await db.save_tg_last_status(
            telegram_user_id=int(tg_user["telegram_user_id"]),
            status_text=tg_user.get("status_text"),
            last_seen_at=tg_user.get("last_seen_at"),
            is_online=tg_user.get("is_online"),
            status_kind=tg_user.get("status_kind"),
            activity_at=tg_user.get("activity_at"),
        )

    added = await db.add_tg_tracked_user(
        chat_id=message.chat.id,
        telegram_user_id=int(tg_user["telegram_user_id"]),
        username=username,
        first_name=tg_user.get("first_name"),
        last_name=tg_user.get("last_name"),
        source_value=source_value,
    )
    display_name = build_tg_display_name(tg_user)
    username_line = f"\nНик: <code>@{escape_html(username)}</code>" if username else ""
    result_prefix = "Пользователь добавлен" if added else "Пользователь уже в списке, данные обновлены"
    await message.answer(
        f"✅ {result_prefix}\n"
        f"<b>{escape_html(display_name)}</b>\n"
        f"ID: <code>{tg_user['telegram_user_id']}</code>{username_line}",
        reply_markup=main_menu_keyboard(),
    )


# --- Handlers ---

@router.callback_query(NavCallback.filter(F.target == "tg_list"))
async def cb_tg_list(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await _show_tg_list(callback.message)


@router.callback_query(NavCallback.filter(F.target == "tg_add"))
async def cb_tg_add_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddUserStates.waiting_for_tg_link)
    await callback.message.answer(
        "<b>Добавление в Telegram</b>\n"
        "Отправьте ссылку, ник или ID пользователя.\n\n"
        "Подойдут варианты:\n"
        "• <code>username</code>\n"
        "• <code>@username</code>\n"
        "• <code>t.me/username</code>\n"
        "• <code>123456789</code>\n\n"
        "Или выберите пользователя кнопкой ниже.",
        reply_markup=tg_add_user_reply_keyboard(),
    )
    await callback.answer()


@router.callback_query(PageCallback.filter(F.source == "tg_list"))
async def cb_tg_list_pagination(callback: CallbackQuery, callback_data: PageCallback) -> None:
    await callback.answer()
    await callback.message.delete()
    await _show_tg_list(callback.message, page=callback_data.page)


@router.callback_query(TgUserActionCallback.filter(F.action == "card"))
async def cb_tg_card(callback: CallbackQuery, callback_data: TgUserActionCallback) -> None:
    await callback.answer()
    detail = await db.get_tg_tracked_user_detail(callback.message.chat.id, callback_data.tg_id)
    if detail is None:
        await callback.message.answer("Пользователь не найден в вашем списке.")
    else:
        text = format_tg_profile_card(detail)
        await callback.message.answer(
            text,
            reply_markup=tg_user_card_keyboard(callback_data.tg_id, callback_data.src),
            disable_web_page_preview=True
        )


@router.callback_query(TgUserActionCallback.filter(F.action == "profile"))
async def cb_tg_profile_alias(callback: CallbackQuery, callback_data: TgUserActionCallback) -> None:
    await cb_tg_card(callback, callback_data)


@router.callback_query(TgUserActionCallback.filter(F.action == "delete"))
async def cb_tg_delete_confirm(callback: CallbackQuery, callback_data: TgUserActionCallback) -> None:
    await callback.answer()
    detail = await db.get_tg_tracked_user_detail(callback.message.chat.id, callback_data.tg_id)
    if detail:
        await callback.message.answer(
            f"Удалить <b>{escape_html(build_tg_display_name(detail))}</b> из списка?",
            reply_markup=tg_delete_confirm_keyboard(callback_data.tg_id, callback_data.src),
        )


@router.callback_query(TgDeleteConfirmCallback.filter())
async def cb_tg_delete_perform(callback: CallbackQuery, callback_data: TgDeleteConfirmCallback) -> None:
    await callback.answer()
    if callback_data.confirm:
        await db.remove_tg_tracked_user(callback.message.chat.id, callback_data.tg_id)
        await callback.message.answer("✅ Пользователь удален.")
        await callback.message.delete()
        await _show_tg_list(callback.message, source=callback_data.src)
    else:
        await callback.message.delete()


@router.message(AddUserStates.waiting_for_tg_link)
async def process_tg_add_input(message: Message, state: FSMContext) -> None:
    # Обработка shared user (если пришло через кнопку)
    if message.user_shared:
        telegram_user_id = int(message.user_shared.user_id)
        # Получаем данные из shared_user (AIogram 3.x)
        shared = message.user_shared
        
        # К сожалению, user_shared в Telegram Bot API не возвращает полные данные без дополнительного запроса
        # Но у нас есть кнопка "request_name=True, request_username=True", 
        # однако в AIogram 3.2+ SharedUser содержит эти поля.
        
        payload = {
            "telegram_user_id": telegram_user_id,
            "username": shared.username,
            "first_name": shared.first_name,
            "last_name": shared.last_name,
        }
        await state.clear()
        await _perform_add_tg_user(message, payload)
        return

    # Обычный текстовый ввод
    raw_value = (message.text or "").strip()
    if not raw_value:
        return

    try:
        resolved = await resolve_telegram_user(raw_value)
        await state.clear()
        # Преобразуем объект ResolverResult в словарь для _perform_add_tg_user
        await _perform_add_tg_user(message, {
            "telegram_user_id": resolved.telegram_user_id,
            "username": resolved.username,
            "first_name": resolved.first_name,
            "last_name": resolved.last_name,
            "access_hash": resolved.access_hash,
            "profile_link": resolved.profile_link,
            "avatar_photo_id": resolved.avatar_photo_id,
            "avatar_dc_id": resolved.avatar_dc_id,
            "avatar_has_video": resolved.avatar_has_video,
            "gifts_count": resolved.gifts_count,
            "gifts_supported": resolved.gifts_supported,
            "status_text": resolved.status_text,
            "last_seen_at": resolved.last_seen_at,
            "is_online": resolved.is_online,
            "status_kind": resolved.status_kind,
            "activity_at": resolved.activity_at,
            "lookup_value": resolved.lookup_value,
        })
    except (TelegramResolverInvalidInputError, TelegramResolverNotFoundError, TelegramResolverPeerTypeError) as e:
        await message.answer(str(e))
    except TelegramResolverUnavailableError:
        await message.answer("Telegram временно недоступен. Попробуйте позже.")
