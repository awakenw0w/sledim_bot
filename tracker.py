"""
Модуль трекера — фоновая asyncio-задача, которая каждые N секунд
опрашивает VK API, отправляет уведомления при изменении статуса
и самовосстанавливает онлайн-сессии в базе.
"""

import asyncio
import hashlib
import html
import logging
import time as time_mod
from datetime import datetime, timezone, timedelta

from aiogram import Bot

import db
import vk_api
from config import ONLINE_CHECK_INTERVAL, PROFILE_CHECK_INTERVAL

logger = logging.getLogger(__name__)
_IS_ONLINE_RUNNING = False
_IS_PROFILE_RUNNING = False

RELATION_LIST_CONFIG = {
    vk_api.RELATION_LIST_FRIENDS: {
        "count_field": "friends_count",
        "plural_label": "друзья",
        "added_label": "Новый друг",
        "removed_label": "Удалён из друзей",
    },
    vk_api.RELATION_LIST_FOLLOWERS: {
        "count_field": "followers_count",
        "plural_label": "подписчики",
        "added_label": "Новый подписчик",
        "removed_label": "Подписчик исчез из списка",
    },
    vk_api.RELATION_LIST_SUBSCRIPTIONS: {
        "count_field": "subscriptions_count",
        "plural_label": "подписки",
        "added_label": "Новая подписка",
        "removed_label": "Подписка пропала из списка",
    },
}
NEW_PROFILE_BASELINE_FIELDS = {
    "profile_status_text",
    "avatar_url",
    "avatar_photo_id",
    "friends_count",
    "followers_count",
    "subscriptions_count",
}
RELATION_COUNT_FIELDS = {"friends_count", "followers_count", "subscriptions_count"}
WALL_NOTIFICATION_POST_LIMIT = 5


def _build_notification(user: dict, new_online: int, changed_at: int) -> str:
    """Формирует текст уведомления об изменении статуса."""
    profile = vk_api.extract_profile_snapshot(user)
    vk_id = user.get("id", "?")
    name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip() or f"ID {vk_id}"
    link = profile.get("profile_link") or vk_api.build_profile_link(int(vk_id) if str(vk_id).isdigit() else None)
    changed_at_str = vk_api.format_timestamp(changed_at)

    if new_online == 1:
        status_icon = "🟢"
        status_text = "вошёл в сеть"
    else:
        status_icon = "🔴"
        status_text = "вышел из сети"

    return "\n".join([
        f"{status_icon} <b>{_escape_html(name)}</b> {status_text}",
        f"🕐 Обнаружено: {changed_at_str}",
        f"🔗 <a href='{_escape_html(link)}'>{_escape_html(link)}</a>",
    ])


def _escape_html(value: str) -> str:
    return html.escape(value, quote=True)


def _truncate_for_message(value: str, limit: int = 180) -> str:
    normalized = value.strip()
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit - 1]}…"


def _build_profile_change_notification(
    user: dict,
    changes: list[dict],
    changed_at: int,
    detail_lines: list[str] | None = None,
) -> str:
    profile = vk_api.extract_profile_snapshot(user)
    vk_id = int(user.get("id", 0) or 0)
    name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip() or f"ID {vk_id}"
    link = profile.get("profile_link") or vk_api.build_profile_link(vk_id, profile.get("domain"))

    lines = [
        f"📝 <b>{_escape_html(name)}</b>",
        f"🕐 Обнаружено: {vk_api.format_timestamp(changed_at)}",
        f"🔗 <a href='{_escape_html(link)}'>{_escape_html(link)}</a>",
        "",
        "<b>Изменения профиля:</b>",
    ]

    if not changes and detail_lines:
        lines.append("• Обновился список связей профиля")

    for change in changes:
        field_name = str(change["field_name"])
        label = vk_api.PROFILE_FIELD_LABELS.get(field_name, field_name)
        if field_name == "avatar_url":
            lines.append(f"• <b>{_escape_html(label)}</b>: <code>обновлена</code>")
            continue

        old_value = _truncate_for_message(vk_api.format_profile_field_value(field_name, change.get("old_value")))
        new_value = _truncate_for_message(vk_api.format_profile_field_value(field_name, change.get("new_value")))
        lines.append(
            f"• <b>{_escape_html(label)}</b>: "
            f"<code>{_escape_html(old_value)}</code> → <code>{_escape_html(new_value)}</code>"
        )

    if detail_lines:
        lines.append("")
        lines.append("<b>Детали:</b>")
        lines.extend(detail_lines)

    return "\n".join(lines)


def _build_relation_notification(
    user: dict,
    list_type: str,
    added_items: list[dict],
    removed_items: list[dict],
    changed_at: int,
    current_count: int | None,
) -> str:
    profile = vk_api.extract_profile_snapshot(user)
    vk_id = int(user.get("id", 0) or 0)
    name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip() or f"ID {vk_id}"
    link = profile.get("profile_link") or vk_api.build_profile_link(vk_id, profile.get("domain"))
    config = RELATION_LIST_CONFIG[list_type]

    lines = [
        f"👥 <b>{_escape_html(name)}</b>",
        f"🕐 Обнаружено: {vk_api.format_timestamp(changed_at)}",
        f"🔗 <a href='{_escape_html(link)}'>{_escape_html(link)}</a>",
        f"Раздел: <b>{_escape_html(config['plural_label'])}</b>",
    ]

    if current_count is not None:
        lines.append(f"Текущее количество: <b>{current_count}</b>")

    if added_items:
        lines.append("")
        lines.append("<b>Добавлены:</b>")
        lines.extend(_build_relation_detail_lines(config["added_label"], added_items, "➕"))

    if removed_items:
        lines.append("")
        lines.append("<b>Удалены:</b>")
        lines.extend(_build_relation_detail_lines(config["removed_label"], removed_items, "➖"))

    return "\n".join(lines)


def _format_wall_post_preview(post: dict, limit: int = 120) -> str:
    text = _truncate_for_message(str(post.get("text") or "").replace("\n", " "), limit=limit)
    if text:
        return text
    return "Без текста"


def _build_wall_posts_notification(
    user: dict,
    added_posts: list[dict],
    changed_at: int,
    total_count: int | None,
) -> str:
    profile = vk_api.extract_profile_snapshot(user)
    vk_id = int(user.get("id", 0) or 0)
    name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip() or f"ID {vk_id}"
    link = profile.get("profile_link") or vk_api.build_profile_link(vk_id, profile.get("domain"))

    lines = [
        f"📝 <b>{_escape_html(name)}</b>",
        f"🕐 Обнаружено: {vk_api.format_timestamp(changed_at)}",
        f"🔗 <a href='{_escape_html(link)}'>{_escape_html(link)}</a>",
        "",
        "<b>Новые записи на стене:</b>",
    ]

    for post in added_posts[:WALL_NOTIFICATION_POST_LIMIT]:
        post_link = str(post.get("post_link") or "").strip()
        created_at = vk_api.format_timestamp(post.get("created_at"))
        preview = _escape_html(_format_wall_post_preview(post))
        if post_link:
            lines.append(f"• <a href='{_escape_html(post_link)}'>Новый пост</a> — {created_at}")
        else:
            lines.append(f"• Новый пост — {created_at}")
        lines.append(f"  {preview}")

    extra_count = len(added_posts) - WALL_NOTIFICATION_POST_LIMIT
    if extra_count > 0:
        lines.append(f"• И ещё {extra_count} шт.")

    if total_count is not None:
        lines.append("")
        lines.append(f"Всего в текущем снимке стены: <b>{total_count}</b>")

    return "\n".join(lines)


def _build_wall_post_change_records(added_posts: list[dict]) -> list[dict]:
    records: list[dict] = []
    for post in added_posts:
        post_link = str(post.get("post_link") or "").strip()
        text = str(post.get("text") or "").strip()
        combined_value = post_link if not text else f"{post_link}\n{text}"
        records.append(
            {
                "field_name": "wall_post",
                "old_value": None,
                "new_value": combined_value or None,
            }
        )
    return records


def _build_profile_changes(old_profile: dict | None, new_profile: dict) -> list[dict]:
    if old_profile is None:
        return []

    changes: list[dict] = []
    old_avatar_key = old_profile.get("avatar_photo_id") or old_profile.get("avatar_url")
    new_avatar_key = new_profile.get("avatar_photo_id") or new_profile.get("avatar_url")
    if old_avatar_key != new_avatar_key and (
        "avatar_photo_id" in new_profile or "avatar_url" in new_profile
    ):
        changes.append(
            {
                "field_name": "avatar_url",
                "old_value": old_profile.get("avatar_url"),
                "new_value": new_profile.get("avatar_url"),
            }
        )

    for field_name in db.PROFILE_CACHE_FIELDS:
        if field_name in {"avatar_url", "avatar_photo_id"}:
            continue
        if field_name not in new_profile:
            continue

        old_value = old_profile.get(field_name)
        new_value = new_profile.get(field_name)
        if old_value == new_value:
            continue

        changes.append(
            {
                "field_name": field_name,
                "old_value": old_value,
                "new_value": new_value,
            }
        )

    return changes


def _merge_change_records(primary: list[dict], extra: list[dict]) -> list[dict]:
    seen = {str(item["field_name"]) for item in primary}
    merged = list(primary)
    for item in extra:
        field_name = str(item["field_name"])
        if field_name in seen:
            continue
        merged.append(item)
        seen.add(field_name)
    return merged


def _prime_profile_baseline(old_profile: dict | None, new_profile: dict) -> dict | None:
    if old_profile is None:
        return None

    primed = dict(old_profile)
    for field_name in NEW_PROFILE_BASELINE_FIELDS:
        if primed.get(field_name) is None and field_name in new_profile:
            primed[field_name] = new_profile.get(field_name)
    return primed


def _normalize_count(value) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _entity_key(item: dict) -> tuple[str, int]:
    return (str(item.get("entity_type") or ""), int(item.get("entity_id") or 0))


def _entity_name(item: dict) -> str:
    first_name = str(item.get("first_name") or "").strip()
    last_name = str(item.get("last_name") or "").strip()
    title = str(item.get("title") or "").strip()
    return f"{first_name} {last_name}".strip() or title or f"ID {item.get('entity_id')}"


def _build_relation_detail_lines(label: str, items: list[dict], icon: str, limit: int = 3) -> list[str]:
    lines: list[str] = []
    for item in items[:limit]:
        link = str(item.get("profile_link") or "").strip()
        name = _escape_html(_entity_name(item))
        if link:
            lines.append(f"{icon} <b>{_escape_html(label)}</b>: <a href='{_escape_html(link)}'>{name}</a>")
        else:
            lines.append(f"{icon} <b>{_escape_html(label)}</b>: {name}")

    extra_count = len(items) - limit
    if extra_count > 0:
        lines.append(f"• И ещё {extra_count} шт.")
    return lines


def _diff_relation_items(old_items: list[dict], new_items: list[dict]) -> tuple[list[dict], list[dict]]:
    old_map = {_entity_key(item): item for item in old_items}
    new_map = {_entity_key(item): item for item in new_items}

    added_keys = [key for key in new_map if key not in old_map]
    removed_keys = [key for key in old_map if key not in new_map]
    return [new_map[key] for key in added_keys], [old_map[key] for key in removed_keys]


def _diff_wall_posts(old_items: list[dict], new_items: list[dict]) -> list[dict]:
    old_post_ids = {int(item.get("post_id") or 0) for item in old_items}
    added_posts = [item for item in new_items if int(item.get("post_id") or 0) not in old_post_ids]
    return sorted(
        added_posts,
        key=lambda item: (
            int(item.get("created_at") or 0),
            int(item.get("post_id") or 0),
        ),
        reverse=True,
    )


async def _collect_relation_change_details(
    vk_id: int,
    list_type: str,
    current_count: int | None,
) -> list[str]:
    config = RELATION_LIST_CONFIG[list_type]
    previous_meta = await db.get_profile_list_meta(vk_id, list_type)
    current_snapshot = await vk_api.get_relation_snapshot(vk_id, list_type, current_count)
    detail_lines: list[str] = []

    if current_snapshot.get("complete"):
        current_items = list(current_snapshot.get("items") or [])
        if previous_meta is not None and int(previous_meta.get("is_complete") or 0) == 1:
            previous_items = await db.get_profile_list_items(vk_id, list_type)
            added_items, removed_items = _diff_relation_items(previous_items, current_items)

            if added_items:
                detail_lines.extend(
                    _build_relation_detail_lines(config["added_label"], added_items, "➕")
                )
            if removed_items:
                detail_lines.extend(
                    _build_relation_detail_lines(config["removed_label"], removed_items, "➖")
                )

            if not added_items and not removed_items:
                detail_lines.append(
                    f"• По списку «{config['plural_label']}» изменение количества есть, "
                    "но конкретный аккаунт определить не удалось."
                )
        else:
            detail_lines.append(
                f"• По списку «{config['plural_label']}» точный аккаунт пока определить нельзя: "
                "предыдущий полный снимок ещё не был сохранён."
            )

        await db.save_profile_list_snapshot(
            vk_id=vk_id,
            list_type=list_type,
            total_count=_normalize_count(current_snapshot.get("count")),
            is_complete=True,
            reason=None,
            items=current_items,
        )
        return detail_lines

    reason = str(current_snapshot.get("reason") or "").strip()
    if reason:
        detail_lines.append(
            f"• По списку «{config['plural_label']}» точный аккаунт определить нельзя: {reason}"
        )
    else:
        detail_lines.append(
            f"• По списку «{config['plural_label']}» точный аккаунт определить нельзя: "
            "список недоступен через VK API."
        )

    await db.save_profile_list_snapshot(
        vk_id=vk_id,
        list_type=list_type,
        total_count=_normalize_count(current_snapshot.get("count")),
        is_complete=False,
        reason=reason or "Список недоступен через VK API.",
        items=None,
    )
    return detail_lines


async def _sync_relation_list(vk_id: int, list_type: str, old_profile: dict | None, profile_snapshot: dict, prefetch_snapshot: dict | None = None) -> tuple[list[dict], list[str], list[dict]]:
    config = RELATION_LIST_CONFIG[list_type]
    count_field = str(config["count_field"])

    previous_count = _normalize_count(old_profile.get(count_field)) if old_profile is not None else None
    previous_meta = await db.get_profile_list_meta(vk_id, list_type)
    previous_meta_count = _normalize_count(previous_meta.get("total_count")) if previous_meta is not None else None
    expected_count = _normalize_count(profile_snapshot.get(count_field))
    if expected_count is None:
        expected_count = previous_meta_count

    current_snapshot = prefetch_snapshot or await vk_api.get_relation_snapshot(vk_id, list_type, expected_count)
    snapshot_count = _normalize_count(current_snapshot.get("count"))
    if snapshot_count is not None:
        profile_snapshot[count_field] = snapshot_count

    current_count = _normalize_count(profile_snapshot.get(count_field))
    old_effective_count = previous_count if previous_count is not None else previous_meta_count

    change_records: list[dict] = []
    relation_events: list[dict] = []
    if old_profile is not None and old_effective_count != current_count:
        change_records.append(
            {
                "field_name": count_field,
                "old_value": old_effective_count,
                "new_value": current_count,
            }
        )

    detail_lines: list[str] = []
    if current_snapshot.get("complete"):
        current_items = list(current_snapshot.get("items") or [])
        previous_complete = previous_meta is not None and int(previous_meta.get("is_complete") or 0) == 1

        if previous_complete:
            previous_items = await db.get_profile_list_items(vk_id, list_type)
            added_items, removed_items = _diff_relation_items(previous_items, current_items)

            if added_items:
                detail_lines.extend(
                    _build_relation_detail_lines(config["added_label"], added_items, "➕")
                )
            if removed_items:
                detail_lines.extend(
                    _build_relation_detail_lines(config["removed_label"], removed_items, "➖")
                )

            if change_records and not added_items and not removed_items:
                detail_lines.append(
                    f"• По списку «{config['plural_label']}» изменение количества есть, "
                    "но конкретный аккаунт определить не удалось."
                )

            if added_items or removed_items:
                relation_events.append(
                    {
                        "list_type": list_type,
                        "added_items": added_items,
                        "removed_items": removed_items,
                        "current_count": current_count,
                    }
                )
        elif old_profile is not None and change_records:
            detail_lines.append(
                f"• По списку «{config['plural_label']}» точный аккаунт пока определить нельзя: "
                "предыдущий полный снимок ещё не был сохранён."
            )

        await db.save_profile_list_snapshot(
            vk_id=vk_id,
            list_type=list_type,
            total_count=current_count,
            is_complete=True,
            reason=None,
            items=current_items,
        )
        return change_records, detail_lines, relation_events

    reason = str(current_snapshot.get("reason") or "").strip()
    # Не шлём повторяющиеся уведомления только из-за недоступности списка.
    # Если список скрыт приватностью и не было реального изменения счётчика,
    # пользователь увидит это состояние в карточке, а бот не будет спамить.
    if change_records and reason:
        detail_lines.append(
            f"• По списку «{config['plural_label']}» точный аккаунт определить нельзя: {reason}"
        )
    elif change_records:
        detail_lines.append(
            f"• По списку «{config['plural_label']}» точный аккаунт определить нельзя: "
            "список недоступен через VK API."
        )

    await db.save_profile_list_snapshot(
        vk_id=vk_id,
        list_type=list_type,
        total_count=current_count,
        is_complete=False,
        reason=reason or "Список недоступен через VK API.",
        items=None,
    )
    return change_records, detail_lines, relation_events


async def _ensure_relation_snapshot_baseline(vk_id: int, list_type: str, current_count: int | None) -> None:
    existing_meta = await db.get_profile_list_meta(vk_id, list_type)
    if existing_meta is not None:
        return

    snapshot = await vk_api.get_relation_snapshot(vk_id, list_type, current_count)
    await db.save_profile_list_snapshot(
        vk_id=vk_id,
        list_type=list_type,
        total_count=_normalize_count(snapshot.get("count")),
        is_complete=bool(snapshot.get("complete")),
        reason=str(snapshot.get("reason") or "").strip() or None,
        items=list(snapshot.get("items") or []) if snapshot.get("complete") else None,
    )


async def _sync_wall_posts(vk_id: int, prefetch_snapshot: dict | None = None) -> tuple[list[dict], int | None]:
    previous_meta = await db.get_wall_post_meta(vk_id)
    current_snapshot = prefetch_snapshot or await vk_api.get_recent_wall_posts(vk_id)
    current_total_count = _normalize_count(current_snapshot.get("count"))

    if not current_snapshot.get("available"):
        await db.save_wall_post_snapshot(
            vk_id=vk_id,
            total_count=current_total_count,
            is_available=False,
            reason=str(current_snapshot.get("reason") or "").strip() or None,
            items=None,
        )
        return [], current_total_count

    current_items = list(current_snapshot.get("items") or [])
    added_posts: list[dict] = []
    if previous_meta is not None and int(previous_meta.get("is_available") or 0) == 1:
        previous_items = await db.get_wall_post_items(vk_id)
        added_posts = _diff_wall_posts(previous_items, current_items)

    await db.save_wall_post_snapshot(
        vk_id=vk_id,
        total_count=current_total_count,
        is_available=True,
        reason=None,
        items=current_items,
    )
    return added_posts, current_total_count


def _should_send_status_notification(mode: str, new_online: int) -> bool:
    normalized_mode = (mode or "").strip().lower()
    if normalized_mode == "off":
        return False
    if normalized_mode == "all":
        return True
    if normalized_mode == "online":
        return new_online == 1
    if normalized_mode == "offline":
        return new_online == 0
    return True


PROFILE_CHANGE_NOTIFICATION_FIELD_MAP = {
    "first_name": "name",
    "last_name": "name",
    "avatar_url": "avatar",
    "profile_status_text": "status",
    "domain": "link",
    "is_closed": "privacy",
    "city": "fields",
    "country": "fields",
    "about": "fields",
    "bdate": "fields",
    "relation": "fields",
    "site": "fields",
    "interests": "fields",
    "books": "fields",
    "movies": "fields",
    "activities": "fields",
    "games": "fields",
    "quotes": "fields",
    "wall_post": "posts",
    "friends_count": "counts",
    "followers_count": "counts",
    "subscriptions_count": "counts",
}


def _filter_profile_changes_by_settings(changes: list[dict], settings: dict[str, bool]) -> list[dict]:
    filtered_changes: list[dict] = []
    for change in changes:
        field_name = str(change.get("field_name") or "")
        settings_key = PROFILE_CHANGE_NOTIFICATION_FIELD_MAP.get(field_name, "fields")
        if bool(settings.get(settings_key, True)):
            filtered_changes.append(change)
    return filtered_changes


async def _reconcile_sessions(chat_id: int, vk_id: int, new_online: int, now_ts: int) -> None:
    """
    Синхронизирует онлайн-сессию с текущим статусом.

    Нужно для случая, когда:
    - пользователь уже был онлайн до обновления кода;
    - бот перезапускался;
    - last_status уже говорит online, но открытой сессии в БД нет.
    """
    open_session = await db.get_open_session(chat_id, vk_id)

    if new_online == 1 and open_session is None:
        await db.start_online_session(chat_id, vk_id, now_ts)
        logger.info(
            "Открыта отсутствовавшая онлайн-сессия: chat_id=%s, vk_id=%s",
            chat_id, vk_id,
        )

    elif new_online == 0 and open_session is not None:
        await db.end_online_session(chat_id, vk_id, now_ts)
        logger.info(
            "Закрыта зависшая онлайн-сессия: chat_id=%s, vk_id=%s",
            chat_id, vk_id,
        )


def _build_watchers_by_vk(pairs: list[tuple[int, int]]) -> tuple[list[int], dict[int, list[int]]]:
    vk_ids = list({vk_id for _, vk_id in pairs})
    watchers_by_vk: dict[int, list[int]] = {}
    for chat_id, vk_id in pairs:
        watchers_by_vk.setdefault(vk_id, []).append(chat_id)
    return vk_ids, watchers_by_vk


async def _check_online_and_notify(bot: Bot) -> None:
    global _IS_ONLINE_RUNNING
    if _IS_ONLINE_RUNNING:
        logger.warning("Overlap protection: _check_online_and_notify is already running.")
        return
    _IS_ONLINE_RUNNING = True
    t0 = time_mod.time()
    
    try:
        pairs = await db.get_all_active_pairs()
        if not pairs:
            return

        vk_ids, watchers_by_vk = _build_watchers_by_vk(pairs)
        users_data = await vk_api.get_users_status(vk_ids)
        if users_data is None:
            logger.warning("VK API не ответил, пропускаем цикл онлайн-проверки")
            return

        now_ts = int(time_mod.time())
        last_known_statuses = await db.get_multiple_last_status(vk_ids)
        statuses_to_save = []
        outbox_count = 0

        for user in users_data:
            vk_id = user.get("id")
            if not vk_id:
                continue

            new_online = int(user.get("online", 0) or 0)
            new_last_seen = vk_api.extract_last_seen_ts(user) or 0
            first_name = user.get("first_name", "")
            last_name = user.get("last_name", "")

            old_status = last_known_statuses.get(vk_id)
            related_chat_ids = watchers_by_vk.get(vk_id, [])

            for chat_id in related_chat_ids:
                try:
                    await _reconcile_sessions(chat_id, vk_id, new_online, now_ts)
                except Exception as exc:
                    logger.error("Ошибка согласования сессий chat_id=%s, vk_id=%s: %s", chat_id, vk_id, exc)

            statuses_to_save.append({
                "vk_id": vk_id,
                "online": new_online,
                "last_seen": new_last_seen,
                "first_name": first_name,
                "last_name": last_name,
            })
            
            if old_status is None:
                continue

            old_online = int(old_status.get("online", 0) or 0)
            if old_online == new_online:
                continue

            message_text = _build_notification(user, new_online, now_ts)
            for chat_id in related_chat_ids:
                try:
                    notification_mode = await db.get_notification_mode(chat_id)
                    if not _should_send_status_notification(notification_mode, new_online):
                        continue

                    m_hash = hashlib.md5(f"vk_status|{chat_id}|{vk_id}|{new_online}|{now_ts}".encode()).hexdigest()
                    await db.enqueue_outbox_message(
                        source="vk",
                        chat_id=chat_id,
                        text=message_text,
                        message_hash=m_hash,
                        parse_mode="HTML",
                        disable_preview=True,
                    )
                    logger.debug("Уведомление отправлено в очередь: chat_id=%s, vk_id=%s, online=%s", chat_id, vk_id, new_online)
                    outbox_count += 1
                except Exception as exc:
                    logger.error("Не удалось добавить уведомление в очередь chat_id=%s, vk_id=%s: %s", chat_id, vk_id, exc)

        await db.save_multiple_last_statuses(statuses_to_save)
        
        elapsed = time_mod.time() - t0
        logger.info("[VK Tracker] Online check completed for %s users in %.2fs. Outbox messages: %s", len(users_data), elapsed, outbox_count)
    finally:
        _IS_ONLINE_RUNNING = False

async def _check_profile_and_notify(bot: Bot) -> None:
    global _IS_PROFILE_RUNNING
    if _IS_PROFILE_RUNNING:
        logger.warning("Overlap protection: _check_profile_and_notify is already running.")
        return
    _IS_PROFILE_RUNNING = True
    t0 = time_mod.time()
    
    try:
        pairs = await db.get_all_active_pairs()
        if not pairs:
            return

        vk_ids, watchers_by_vk = _build_watchers_by_vk(pairs)
        users_data = await vk_api.get_users_status(vk_ids)
        if users_data is None:
            logger.warning("VK API не ответил, пропускаем цикл проверки профиля")
            return

        users_map: dict[int, dict] = {u["id"]: u for u in users_data if "id" in u}
        now_ts = int(time_mod.time())
        
        cached_profiles = await db.get_multiple_profile_caches(vk_ids)
        profiles_to_save = {}
        outbox_count = 0

        # VK execute batching: chunk users by 5 to stay within 25 methods per request
        CHUNK_SIZE = 5
        for i in range(0, len(vk_ids), CHUNK_SIZE):
            chunk_ids = vk_ids[i:i + CHUNK_SIZE]
            
            # Fetch bulk data for relations and wall
            batch_data = await vk_api.get_batch_profile_data(chunk_ids)
            
            for vk_id in chunk_ids:
                user = users_map.get(vk_id)
                if user is None:
                    continue

                profile_snapshot = vk_api.extract_profile_snapshot(user)
                old_profile_raw = cached_profiles.get(vk_id)
                old_profile = _prime_profile_baseline(old_profile_raw, profile_snapshot)
                related_chat_ids = watchers_by_vk.get(vk_id, [])

                # Get prefetched data for this user
                user_batch = batch_data.get(vk_id, {})

                relation_change_records: list[dict] = []
                relation_detail_lines: list[str] = []
                relation_events: list[dict] = []
                for list_type in RELATION_LIST_CONFIG:
                    # Map raw data to what sync_relation expects (normalization happens inside sync_relation)
                    raw_rel_data = user_batch.get(list_type)
                    prefetch_rel = None
                    if raw_rel_data is not None:
                        prefetch_rel = vk_api._process_relation_response(raw_rel_data, list_type)
                    
                    records, detail_lines, events = await _sync_relation_list(vk_id, list_type, old_profile, profile_snapshot, prefetch_snapshot=prefetch_rel)
                    relation_change_records.extend(records)
                    relation_detail_lines.extend(detail_lines)
                    relation_events.extend(events)

                # Prefetch wall
                raw_wall_data = user_batch.get("wall")
                prefetch_wall = None
                if raw_wall_data is not None:
                    prefetch_wall = vk_api._process_wall_response(raw_wall_data)
                
                new_wall_posts, wall_post_total_count = await _sync_wall_posts(vk_id, prefetch_snapshot=prefetch_wall)

                profiles_to_save[vk_id] = profile_snapshot

                profile_changes = _build_profile_changes(old_profile, profile_snapshot)
                profile_changes = _merge_change_records(profile_changes, relation_change_records)
                if new_wall_posts:
                    profile_changes.extend(_build_wall_post_change_records(new_wall_posts))
                if profile_changes:
                    await db.add_profile_changes(vk_id, profile_changes, now_ts)

                profile_changes_for_message = list(profile_changes)
                if relation_events:
                    profile_changes_for_message = [
                        change for change in profile_changes_for_message
                        if str(change.get("field_name")) not in RELATION_COUNT_FIELDS
                    ]

                detail_lines_for_message = [] if relation_events else relation_detail_lines
                if profile_changes_for_message or detail_lines_for_message:
                    for chat_id in related_chat_ids:
                        try:
                            change_settings = await db.get_change_notification_settings(chat_id)
                            filtered_profile_changes = _filter_profile_changes_by_settings(
                                profile_changes_for_message,
                                change_settings,
                            )
                            filtered_detail_lines = (
                                detail_lines_for_message if bool(change_settings.get("relations", True)) else []
                            )
                            if not filtered_profile_changes and not filtered_detail_lines:
                                continue

                            profile_message_text = _build_profile_change_notification(
                                user,
                                filtered_profile_changes,
                                now_ts,
                                detail_lines=filtered_detail_lines,
                            )
                            m_hash = hashlib.md5(f"vk_profile|{chat_id}|{vk_id}|{now_ts}".encode()).hexdigest()
                            await db.enqueue_outbox_message(
                                source="vk",
                                chat_id=chat_id,
                                text=profile_message_text,
                                message_hash=m_hash,
                                parse_mode="HTML",
                                disable_preview=True,
                            )
                            logger.debug("Уведомление об изменении в очереди: vk_id=%s", vk_id)
                            outbox_count += 1
                        except Exception as exc:
                            logger.error("Не удалось добавить в очередь профиль chat_id=%s: %s", chat_id, exc)

                if relation_events:
                    for event in relation_events:
                        relation_message_text = _build_relation_notification(
                            user,
                            list_type=str(event["list_type"]),
                            added_items=list(event.get("added_items") or []),
                            removed_items=list(event.get("removed_items") or []),
                            changed_at=now_ts,
                            current_count=_normalize_count(event.get("current_count")),
                        )
                        for chat_id in related_chat_ids:
                            try:
                                change_settings = await db.get_change_notification_settings(chat_id)
                                if not bool(change_settings.get("relations", True)):
                                    continue
                                m_hash = hashlib.md5(f"vk_relation|{chat_id}|{vk_id}|{event['list_type']}|{now_ts}".encode()).hexdigest()
                                await db.enqueue_outbox_message(
                                    source="vk",
                                    chat_id=chat_id,
                                    text=relation_message_text,
                                    message_hash=m_hash,
                                    parse_mode="HTML",
                                    disable_preview=True,
                                )
                                outbox_count += 1
                            except Exception as exc:
                                logger.error("Ошибка связей chat_id=%s: %s", chat_id, exc)

                if new_wall_posts:
                    wall_message_text = _build_wall_posts_notification(
                        user,
                        added_posts=new_wall_posts,
                        changed_at=now_ts,
                        total_count=wall_post_total_count,
                    )
                    for chat_id in related_chat_ids:
                        try:
                            change_settings = await db.get_change_notification_settings(chat_id)
                            if not bool(change_settings.get("posts", True)):
                                continue
                            m_hash = hashlib.md5(f"vk_posts|{chat_id}|{vk_id}|{now_ts}".encode()).hexdigest()
                            await db.enqueue_outbox_message(
                                source="vk",
                                chat_id=chat_id,
                                text=wall_message_text,
                                message_hash=m_hash,
                                parse_mode="HTML",
                                disable_preview=True,
                            )
                            outbox_count += 1
                        except Exception as exc:
                            logger.error("Ошибка постов chat_id=%s: %s", chat_id, exc)

        await db.save_multiple_profile_caches(profiles_to_save)
        elapsed = time_mod.time() - t0
        logger.info("[VK Tracker] Profile check completed for %s users in %.2fs. Outbox messages: %s", len(vk_ids), elapsed, outbox_count)
    finally:
        _IS_PROFILE_RUNNING = False

async def run_tracker(bot: Bot) -> None:
    logger.info(
        "Трекер запущен. Онлайн: раз в %s сек. Профиль: раз в %s сек.",
        ONLINE_CHECK_INTERVAL,
        PROFILE_CHECK_INTERVAL,
    )
    last_profile_check_at = 0.0
    while True:
        loop_started_at = time_mod.time()
        try:
            await _check_online_and_notify(bot)
            if loop_started_at - last_profile_check_at >= PROFILE_CHECK_INTERVAL:
                await _check_profile_and_notify(bot)
                last_profile_check_at = time_mod.time()
        except asyncio.CancelledError:
            logger.info("Трекер остановлен.")
            break
        except Exception as exc:
            logger.exception("Ошибка в цикле трекера: %s", exc)

        sleep_for = max(ONLINE_CHECK_INTERVAL - (time_mod.time() - loop_started_at), 0)
        await asyncio.sleep(sleep_for)
