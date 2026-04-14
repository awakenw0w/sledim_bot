import logging
from datetime import datetime
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import db
import vk_api
from ui_callbacks import (
    DeleteConfirmCallback,
    NavCallback,
    PageCallback,
    UserActionCallback,
)
from ui_format import (
    MSK,
    build_relation_privacy_lines,
    build_vk_name,
    escape_html,
    format_vk_profile_card,
    get_vk_link_formats_text,
)
from ui_keyboards import (
    back_main_inline_keyboard,
    delete_confirm_keyboard,
    main_menu_keyboard,
    tracked_list_paginated_keyboard,
    user_card_keyboard,
    user_picker_keyboard,
)
from ui_states import AddUserStates, SearchStates

from .common import safe_answer_callback

logger = logging.getLogger(__name__)

router = Router()

VK_LIST_PAGE_SIZE = 5
VK_SEARCH_SOURCE = "srh"
VK_SEARCH_QUERY_KEY = "vk_search_query"


def _normalize_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _normalize_search_query(raw_query: str | None) -> str | None:
    return " ".join(str(raw_query or "").split()) or None


def _normalize_source(source: str) -> str:
    normalized = str(source or "").strip()
    if normalized.startswith("r"):
        normalized = normalized[1:]
    if normalized.startswith("c"):
        normalized = normalized[1:]
    return normalized


def _build_vk_add_prompt_text() -> str:
    return (
        "<b>Добавление во ВКонтакте</b>\n"
        "Отправьте ссылку, короткое имя или ID профиля.\n\n"
        + get_vk_link_formats_text()
    )


def _build_vk_search_prompt_text(last_query: str | None = None) -> str:
    lines = [
        "<b>Поиск • ВКонтакте</b>",
        "Введите имя, ID, username или часть ссылки по уже отслеживаемым пользователям.",
    ]
    if last_query:
        lines.append(f"Последний запрос: <code>{escape_html(last_query)}</code>")
    return "\n".join(lines)


def _build_vk_search_title(query: str) -> str:
    return (
        "<b>Поиск • ВКонтакте</b>\n"
        f"Запрос: <code>{escape_html(query)}</code>"
    )


def _build_vk_search_empty_text(query: str) -> str:
    return (
        "<b>Поиск • ВКонтакте</b>\n"
        f"По запросу <code>{escape_html(query)}</code> ничего не найдено среди отслеживаемых профилей."
    )


def _build_vk_resolve_error_text(reason: str | None) -> str:
    if reason == "invalid_input":
        return "Не удалось распознать ссылку или ID. Проверьте ввод и попробуйте снова."
    if reason == "application_blocked":
        return (
            "VK сейчас недоступен: приложение для VK API заблокировано.\n"
            "Обновите <code>VK_ACCESS_TOKEN</code> и попробуйте снова."
        )
    if reason == "token_expired":
        return (
            "Не удалось добавить пользователя: <code>VK_ACCESS_TOKEN</code> истёк.\n"
            "Обновите токен в <code>.env</code> и перезапустите бота."
        )
    if reason == "token_invalid":
        return (
            "Не удалось добавить пользователя: VK отклонил <code>VK_ACCESS_TOKEN</code>.\n"
            "Проверьте токен в <code>.env</code> и перезапустите бота."
        )
    if reason in {"api_error", "api_unavailable"}:
        return "Не удалось связаться с VK API. Попробуйте чуть позже."
    return "Не удалось найти пользователя. Проверьте ссылку или ID."


async def _resolve_vk_user_from_input(raw_link: str) -> tuple[dict[str, Any] | None, str | None]:
    return await vk_api.resolve_user_by_vk_link_verbose(raw_link)


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
            vk_id,
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


def _snapshot_from_api_user(user: dict[str, Any], tracked_snapshot: dict | None = None) -> dict:
    vk_id = int(user["id"])
    first_name = user.get("first_name", "")
    last_name = user.get("last_name", "")
    domain = user.get("domain") or user.get("screen_name")
    live_profile = vk_api.extract_profile_snapshot(user)

    snapshot = {
        "vk_id": vk_id,
        "name": build_vk_name(first_name, last_name, vk_id),
        "online": int(user.get("online", tracked_snapshot.get("online", 0) if tracked_snapshot else 0) or 0),
        "last_seen": vk_api.extract_last_seen_ts(user) or (tracked_snapshot.get("last_seen") if tracked_snapshot else None),
        "added_at": tracked_snapshot.get("added_at") if tracked_snapshot else None,
        "profile_link": vk_api.build_profile_link(vk_id, domain or (tracked_snapshot.get("domain") if tracked_snapshot else None)),
        "first_name": first_name,
        "last_name": last_name,
    }

    for field_name in db.PROFILE_CACHE_FIELDS:
        snapshot[field_name] = tracked_snapshot.get(field_name) if tracked_snapshot else None

    snapshot.update(live_profile)
    snapshot["name"] = build_vk_name(snapshot.get("first_name", ""), snapshot.get("last_name", ""), vk_id)
    snapshot["profile_link"] = snapshot.get("profile_link") or vk_api.build_profile_link(vk_id, domain)
    return snapshot


def _matches_vk_search(snapshot: dict, query: str) -> bool:
    normalized_query = _normalize_name(query)
    candidates = (
        snapshot.get("name"),
        snapshot.get("first_name"),
        snapshot.get("last_name"),
        snapshot.get("domain"),
        snapshot.get("profile_link"),
        str(snapshot.get("vk_id") or ""),
    )
    return any(
        normalized_query in _normalize_name(str(candidate))
        for candidate in candidates
        if candidate
    )


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


async def _show_vk_report_user_picker(message: Message) -> None:
    details = await db.get_tracked_users_details(message.chat.id, active_only=True)
    if not details:
        await message.answer("В списке пока нет пользователей.", reply_markup=main_menu_keyboard())
        return

    items = [
        (
            int(item["vk_id"]),
            f"{item.get('first_name', '')} {item.get('last_name', '')}".strip() or f"ID {item['vk_id']}",
        )
        for item in details
    ]
    await message.answer(
        "<b>Онлайн • ВКонтакте</b>\nВыберите пользователя.",
        reply_markup=user_picker_keyboard(items, source="orp", back_target="vk_menu"),
    )


async def _show_vk_list(
    message: Message,
    page: int = 1,
    source: str = "vk_list",
    title: str | None = None,
    snapshots: list[dict] | None = None,
    empty_text: str | None = None,
) -> None:
    if snapshots is None:
        snapshots = await _load_tracked_snapshots(message.chat.id)

    if not snapshots:
        if empty_text is None:
            await message.answer(
                "<b>Список • ВКонтакте</b>\n"
                "Пока здесь пусто. Добавьте первого пользователя.",
                reply_markup=main_menu_keyboard(),
            )
        else:
            await message.answer(
                empty_text,
                reply_markup=back_main_inline_keyboard("search_prompt" if source == VK_SEARCH_SOURCE else "vk_menu"),
            )
        return

    total_pages = (len(snapshots) + VK_LIST_PAGE_SIZE - 1) // VK_LIST_PAGE_SIZE
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * VK_LIST_PAGE_SIZE
    chunk = snapshots[start_idx:start_idx + VK_LIST_PAGE_SIZE]

    list_title = title or "<b>Список • ВКонтакте</b>"
    lines = [list_title]
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

    keyboard = tracked_list_paginated_keyboard(
        [(int(item["vk_id"]), str(item["name"])) for item in chunk],
        page=page,
        total_pages=total_pages,
        source=source,
    )
    await message.answer(
        "\n\n".join(lines),
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


async def _show_user_card(
    message: Message,
    vk_id: int,
    source: str,
    snapshot: dict | None = None,
    allow_actions: bool = True,
) -> None:
    if snapshot is None:
        snapshot = await _get_single_snapshot(message.chat.id, vk_id)
    if snapshot is None:
        await message.answer("Пользователь не найден в вашем списке.")
        return

    privacy_lines = await build_relation_privacy_lines(vk_id)
    text = format_vk_profile_card(snapshot, privacy_lines)
    reply_markup = user_card_keyboard(vk_id=vk_id, source=source) if allow_actions else back_main_inline_keyboard("vk_menu")
    await message.answer(
        text,
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )


async def _show_vk_search_prompt(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    last_query = _normalize_search_query(data.get(VK_SEARCH_QUERY_KEY))
    await state.set_state(SearchStates.waiting_for_query)
    await message.answer(
        _build_vk_search_prompt_text(last_query),
        reply_markup=back_main_inline_keyboard("vk_menu"),
    )


async def _show_vk_search_results(message: Message, state: FSMContext, page: int = 1) -> None:
    data = await state.get_data()
    query = _normalize_search_query(data.get(VK_SEARCH_QUERY_KEY))
    if query is None:
        await _show_vk_search_prompt(message, state)
        return

    snapshots = await _load_tracked_snapshots(message.chat.id)
    matches = [snapshot for snapshot in snapshots if _matches_vk_search(snapshot, query)]
    await state.set_state(SearchStates.viewing_results)
    await _show_vk_list(
        message,
        page=page,
        source=VK_SEARCH_SOURCE,
        title=_build_vk_search_title(query),
        snapshots=matches,
        empty_text=_build_vk_search_empty_text(query),
    )


async def _perform_vk_search(message: Message, state: FSMContext, raw_query: str) -> None:
    query = _normalize_search_query(raw_query)
    if query is None:
        await _show_vk_search_prompt(message, state)
        return

    await state.update_data({VK_SEARCH_QUERY_KEY: query})
    await _show_vk_search_results(message, state, page=1)


async def _show_post_delete_context(message: Message, state: FSMContext, source: str) -> None:
    normalized_source = _normalize_source(source)
    if normalized_source == VK_SEARCH_SOURCE:
        await _show_vk_search_results(message, state, page=1)
        return
    if normalized_source == "orp":
        await _show_vk_report_user_picker(message)
        return
    await _show_vk_list(message)


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
            reply_markup=main_menu_keyboard(),
        )
    else:
        await message.answer(
            f"ℹ️ Пользователь уже есть в списке\n"
            f"<b>{name}</b>",
            reply_markup=main_menu_keyboard(),
        )


@router.callback_query(NavCallback.filter(F.target == "vk_list"))
async def cb_vk_list(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_answer_callback(callback)
    await state.clear()
    await _show_vk_list(callback.message)


@router.callback_query(NavCallback.filter(F.target == "search_prompt"))
async def cb_vk_search_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_answer_callback(callback)
    await callback.message.delete()
    await _show_vk_search_prompt(callback.message, state)


@router.callback_query(NavCallback.filter(F.target == "search_results"))
async def cb_vk_search_results(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_answer_callback(callback)
    await callback.message.delete()
    await _show_vk_search_results(callback.message, state)


@router.callback_query(NavCallback.filter(F.target == "vk_add"))
async def cb_vk_add_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_answer_callback(callback)
    await state.set_state(AddUserStates.waiting_for_vk_link)
    await callback.message.answer(
        _build_vk_add_prompt_text(),
        reply_markup=back_main_inline_keyboard("vk_menu"),
    )


@router.callback_query(PageCallback.filter(F.source == "vk_list"))
async def cb_vk_list_pagination(callback: CallbackQuery, callback_data: PageCallback) -> None:
    await safe_answer_callback(callback)
    await callback.message.delete()
    await _show_vk_list(callback.message, page=callback_data.page)


@router.callback_query(PageCallback.filter(F.source == VK_SEARCH_SOURCE))
async def cb_vk_search_pagination(callback: CallbackQuery, callback_data: PageCallback, state: FSMContext) -> None:
    await safe_answer_callback(callback)
    await callback.message.delete()
    await _show_vk_search_results(callback.message, state, page=callback_data.page)


@router.callback_query(UserActionCallback.filter(F.action == "card"))
async def cb_vk_card(callback: CallbackQuery, callback_data: UserActionCallback) -> None:
    await safe_answer_callback(callback)
    await _show_user_card(callback.message, callback_data.vk_id, callback_data.src)


@router.callback_query(UserActionCallback.filter(F.action == "delete"))
async def cb_vk_delete_confirm(callback: CallbackQuery, callback_data: UserActionCallback) -> None:
    await safe_answer_callback(callback)
    snapshot = await _get_single_snapshot(callback.message.chat.id, callback_data.vk_id)
    if snapshot:
        await callback.message.answer(
            f"Удалить <b>{snapshot['name']}</b> из списка?",
            reply_markup=delete_confirm_keyboard(callback_data.vk_id, callback_data.src),
        )


@router.callback_query(DeleteConfirmCallback.filter())
async def cb_vk_delete_perform(callback: CallbackQuery, callback_data: DeleteConfirmCallback, state: FSMContext) -> None:
    await safe_answer_callback(callback)
    if callback_data.confirm:
        await db.remove_tracked_user(callback.message.chat.id, callback_data.vk_id)
        await callback.message.answer("✅ Пользователь удален.")
        await callback.message.delete()
        await _show_post_delete_context(callback.message, state, callback_data.src)
        return

    await callback.message.delete()


@router.message(AddUserStates.waiting_for_vk_link)
async def process_vk_add_link(message: Message, state: FSMContext) -> None:
    raw_link = (message.text or "").strip()
    user, reason = await _resolve_vk_user_from_input(raw_link)
    if not user:
        await message.answer(_build_vk_resolve_error_text(reason))
        return

    await state.clear()
    await _perform_add_vk_user(message, user)


@router.message(SearchStates.waiting_for_query)
async def process_vk_search_query(message: Message, state: FSMContext) -> None:
    await _perform_vk_search(message, state, message.text or "")


@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await state.set_state(AddUserStates.waiting_for_vk_link)
        await message.answer(
            _build_vk_add_prompt_text(),
            reply_markup=back_main_inline_keyboard("vk_menu"),
        )
        return

    user, reason = await _resolve_vk_user_from_input(parts[1])
    if user:
        await _perform_add_vk_user(message, user)
    else:
        await message.answer(_build_vk_resolve_error_text(reason))


@router.message(Command("list"))
async def cmd_list(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_vk_list(message)


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Используйте: <code>/status ссылка</code> или <code>/status ID</code>.")
        return

    user, reason = await _resolve_vk_user_from_input(parts[1])
    if not user:
        await message.answer(_build_vk_resolve_error_text(reason))
        return

    vk_id = int(user["id"])
    tracked_snapshot = await _get_single_snapshot(message.chat.id, vk_id)
    live_snapshot = _snapshot_from_api_user(user, tracked_snapshot)
    await _show_user_card(
        message,
        vk_id,
        source="cmd",
        snapshot=live_snapshot,
        allow_actions=tracked_snapshot is not None,
    )


@router.message(Command("find"))
async def cmd_find(message: Message, state: FSMContext) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await _show_vk_search_prompt(message, state)
        return

    await _perform_vk_search(message, state, parts[1])


@router.message(Command("remove"))
async def cmd_remove(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Используйте: <code>/remove ссылка</code> или <code>/remove ID</code>.")
        return

    user, reason = await _resolve_vk_user_from_input(parts[1])
    if user:
        removed = await db.remove_tracked_user(message.chat.id, int(user["id"]))
        if removed:
            await message.answer(f"✅ Пользователь <code>{user['id']}</code> удален.")
        else:
            await message.answer("Пользователь не найден в вашем списке.")
    else:
        await message.answer(_build_vk_resolve_error_text(reason))
