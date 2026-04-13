import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

import db
import vk_api
from ui_keyboards import (
    main_menu_keyboard,
    back_main_inline_keyboard,
    tracked_list_paginated_keyboard,
    user_card_keyboard,
    delete_confirm_keyboard
)
from ui_callbacks import (
    NavCallback,
    PageCallback,
    UserActionCallback,
    DeleteConfirmCallback
)
from ui_states import AddUserStates, SearchStates
from ui_format import (
    MSK,
    escape_html,
    format_vk_profile_card,
    build_vk_name,
    build_relation_privacy_lines,
    get_vk_link_formats_text
)

logger = logging.getLogger(__name__)

router = Router()

# --- Helpers ---

def _normalize_name(value: str) -> str:
    return " ".join(value.casefold().split())


async def _load_current_users_map(vk_ids: list[int]) -> dict[int, dict]:
    return {}


def _snapshot_from_detail(detail: dict) -> dict:
    vk_id = int(detail["vk_id"])
    online = int(detail.get("online", 0) or 0)
    last_seen = detail.get("last_seen")

    domain = detail.get("domain")
    profile_link = vk_api.build_profile_link(vk_id, domain)

    snapshot = {
        "vk_id": vk_id,
        "name": build_vk_name(
            detail.get("first_name", ""),
            detail.get("last_name", ""),
            vk_id
        ),
        "online": online,
        "last_seen": last_seen,
        "added_at": detail.get("added_at"),
        "profile_link": profile_link,
        "first_name": detail.get("first_name"),
        "last_name": detail.get("last_name"),
    }

    for field_name in db.PROFILE_CACHE_FIELDS:
        snapshot[field_name] = detail.get(field_name)

    return snapshot


async def _load_tracked_snapshots(chat_id: int) -> list[dict]:
    details = await db.get_tracked_users_details(chat_id, active_only=True)
    if not details:
        return []

    return [_snapshot_from_detail(detail) for detail in details]


async def _get_single_snapshot(chat_id: int, vk_id: int) -> dict | None:
    detail = await db.get_tracked_user_detail(chat_id, vk_id)
    if detail is None:
        return None

    return _snapshot_from_detail(detail)


async def _show_vk_list(message: Message, page: int = 1, source: str = "vk_list", title: str | None = None) -> None:
    snapshots = await _load_tracked_snapshots(message.chat.id)
    if not snapshots:
        await message.answer(
            "<b>Список • ВКонтакте</b>\n"
            "Пока здесь пусто. Добавьте первого пользователя.",
            reply_markup=main_menu_keyboard(),
        )
        return

    page_size = 5
    total_pages = (len(snapshots) + page_size - 1) // page_size
    page = max(1, min(page, total_pages))
    
    start_idx = (page - 1) * page_size
    chunk = snapshots[start_idx : start_idx + page_size]
    
    title = title or "<b>Список • ВКонтакте</b>"
    lines = [title]
    if total_pages > 1:
        lines.append(f"Страница {page} из {total_pages}")

    for snapshot in chunk:
        status = "🟢 онлайн" if snapshot["online"] else "🔴 офлайн"
        lines.append(
            f"• <b>{escape_html(snapshot['name'])}</b>\n"
            f"Статус: {status}\n"
            f"ID: <code>{snapshot['vk_id']}</code>\n"
            f"Ссылка: <a href='{snapshot['profile_link']}'>{snapshot['profile_link']}</a>"
        )

    text = "\n\n".join(lines)
    keyboard = tracked_list_paginated_keyboard(
        [(int(item["vk_id"]), str(item["name"])) for item in chunk],
        page=page,
        total_pages=total_pages,
        source=source
    )
    
    await message.answer(text, reply_markup=keyboard, disable_web_page_preview=True)


async def _show_user_card(message: Message, vk_id: int, source: str) -> None:
    snapshot = await _get_single_snapshot(message.chat.id, vk_id)
    if snapshot is None:
        await message.answer("Пользователь не найден в вашем списке.")
        return

    privacy_lines = await build_relation_privacy_lines(vk_id)
    text = format_vk_profile_card(snapshot, privacy_lines)
    await message.answer(
        text,
        reply_markup=user_card_keyboard(vk_id=vk_id, source=source),
        disable_web_page_preview=True
    )


async def _perform_add_vk_user(message: Message, user: dict) -> None:
    chat_id = message.chat.id
    vk_id = int(user["id"])

    if user.get("deactivated"):
        reason = user.get("deactivated", "удалён")
        await message.answer(f"Профиль <code>{vk_id}</code> недоступен: {reason}.")
        return

    added = await db.add_tracked_user(chat_id, vk_id)
    first_name = user.get("first_name", "")
    last_name = user.get("last_name", "")
    name = build_vk_name(first_name, last_name, vk_id)
    now_ts = int(datetime.now(tz=MSK).timestamp())

    await db.save_last_status(
        vk_id=vk_id,
        online=int(user.get("online", 0) or 0),
        last_seen=vk_api.extract_last_seen_ts(user) or 0,
        first_name=first_name,
        last_name=last_name,
    )

    if user.get("online", 0) == 1:
        await db.ensure_open_session(chat_id, vk_id, now_ts)

    profile_snapshot = vk_api.extract_profile_snapshot(user)
    await db.save_profile_cache(vk_id, profile_snapshot)

    if added:
        await message.answer(
            f"✅ Пользователь добавлен\n"
            f"<b>{name}</b>\n"
            f"ID: <code>{vk_id}</code>",
            reply_markup=main_menu_keyboard()
        )
    else:
        await message.answer(
            f"ℹ️ Пользователь уже есть в списке\n"
            f"<b>{name}</b>",
            reply_markup=main_menu_keyboard()
        )


# --- Handlers ---

@router.callback_query(NavCallback.filter(F.target == "vk_list"))
async def cb_vk_list(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await _show_vk_list(callback.message)


@router.callback_query(NavCallback.filter(F.target == "vk_add"))
async def cb_vk_add_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddUserStates.waiting_for_vk_link)
    await callback.message.answer(
        "<b>Добавление во ВКонтакте</b>\n"
        "Отправьте ссылку, короткое имя или ID профиля.\n\n"
        + get_vk_link_formats_text(),
        reply_markup=back_main_inline_keyboard("vk_menu")
    )
    await callback.answer()


@router.callback_query(PageCallback.filter(F.source == "vk_list"))
async def cb_vk_list_pagination(callback: CallbackQuery, callback_data: PageCallback) -> None:
    await callback.answer()
    # Удаляем старое сообщение или редактируем? Пользователь просил "не ломать UX".
    # Для лучшего UX при пагинации лучше редактировать текущее сообщение.
    await callback.message.delete()
    await _show_vk_list(callback.message, page=callback_data.page)


@router.callback_query(UserActionCallback.filter(F.action == "card"))
async def cb_vk_card(callback: CallbackQuery, callback_data: UserActionCallback) -> None:
    await callback.answer()
    await _show_user_card(callback.message, callback_data.vk_id, callback_data.src)


@router.callback_query(UserActionCallback.filter(F.action == "delete"))
async def cb_vk_delete_confirm(callback: CallbackQuery, callback_data: UserActionCallback) -> None:
    await callback.answer()
    snapshot = await _get_single_snapshot(callback.message.chat.id, callback_data.vk_id)
    if snapshot:
        await callback.message.answer(
            f"Удалить <b>{snapshot['name']}</b> из списка?",
            reply_markup=delete_confirm_keyboard(callback_data.vk_id, callback_data.src)
        )


@router.callback_query(DeleteConfirmCallback.filter())
async def cb_vk_delete_perform(callback: CallbackQuery, callback_data: DeleteConfirmCallback) -> None:
    await callback.answer()
    if callback_data.confirm:
        await db.remove_tracked_user(callback.message.chat.id, callback_data.vk_id)
        await callback.message.answer("✅ Пользователь удален.")
        await callback.message.delete()
        # Возвращаемся в список
        await _show_vk_list(callback.message, source=callback_data.src)
    else:
        await callback.message.delete()


@router.message(AddUserStates.waiting_for_vk_link)
async def process_vk_add_link(message: Message, state: FSMContext) -> None:
    raw_link = message.text.strip()
    user = await vk_api.resolve_user_by_vk_link(raw_link)
    if not user:
        await message.answer("Не удалось найти пользователя. Проверьте ссылку или ID.")
        return

    await state.clear()
    await _perform_add_vk_user(message, user)


@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await cb_vk_add_prompt(None, state) # Имитируем вызов промпта
        return
    
    user = await vk_api.resolve_user_by_vk_link(parts[1])
    if user:
        await _perform_add_vk_user(message, user)
    else:
        await message.answer("Пользователь не найден.")


@router.message(Command("list"))
async def cmd_list(message: Message) -> None:
    await _show_vk_list(message)


@router.message(Command("status"))
async def cmd_status(message: Message, state: FSMContext) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Используйте: <code>/status ссылка</code> или <code>/status ID</code>.")
        return
    
    user = await vk_api.resolve_user_by_vk_link(parts[1])
    if user:
        await _show_user_card(message, int(user["id"]), source="cmd")
    else:
        await message.answer("Пользователь не найден.")


@router.message(Command("find"))
async def cmd_find(message: Message, state: FSMContext) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await state.set_state(SearchStates.waiting_for_query)
        await message.answer("Введите имя для поиска.")
        return
    
    # Здесь логика поиска (упрощенно)
    snapshots = await _load_tracked_snapshots(message.chat.id)
    query = parts[1].strip().lower()
    matches = [s for s in snapshots if query in s["name"].lower()]
    
    if not matches:
        await message.answer("Ничего не найдено.")
    else:
        # Показываем список результатов (первая страница)
        await _show_vk_list(message, page=1, source="search", title=f"<b>Поиск • ВКонтакте</b>\nЗапрос: <code>{escape_html(parts[1])}</code>")


@router.message(Command("remove"))
async def cmd_remove(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Используйте: <code>/remove ссылка</code> или <code>/remove ID</code>.")
        return
    
    user = await vk_api.resolve_user_by_vk_link(parts[1])
    if user:
        removed = await db.remove_tracked_user(message.chat.id, int(user["id"]))
        if removed:
            await message.answer(f"✅ Пользователь <code>{user['id']}</code> удален.")
        else:
            await message.answer("Пользователь не найден в вашем списке.")
    else:
        await message.answer("Не удалось найти пользователя.")
