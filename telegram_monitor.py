"""
Фоновый Telegram-monitor.
Получает статусы и базовые поля профиля через MTProto userbot, ведет историю
online/activity, фиксирует изменения профиля и отправляет TG-уведомления
по отдельным настройкам без смешивания с VK-веткой.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import logging
import time
from datetime import datetime, timedelta, timezone

from aiogram import Bot

import db
from config import ONLINE_CHECK_INTERVAL
from telegram_resolver import (
    TelegramResolverNotFoundError,
    TelegramResolverPeerTypeError,
    TelegramResolverUnavailableError,
    fetch_telegram_user_snapshot,
)

logger = logging.getLogger(__name__)

MSK = timezone(timedelta(hours=3))
ACTIVITY_KIND_RANK = {
    "unknown": 0,
    "hidden": 0,
    "last_month": 1,
    "last_week": 2,
    "recently": 3,
    "offline": 4,
    "online": 5,
}
TG_CHANGE_LABELS = {
    "first_name": "Имя [TG]",
    "last_name": "Фамилия [TG]",
    "username": "Username [TG]",
    "avatar": "Аватарка [TG]",
    "gifts": "Подарки [TG]",
    "bio": "Bio [TG]",
}
TG_CHANGE_SETTING_KEYS = {
    "first_name": "first_name",
    "last_name": "last_name",
    "username": "username",
    "avatar": "avatar",
    "gifts": "gifts",
    "bio": "bio",
}


def _escape_html(value: object) -> str:
    return html.escape(str(value), quote=True)


def _format_timestamp(ts: int | None) -> str:
    if ts is None:
        return "неизвестно"
    return datetime.fromtimestamp(int(ts), tz=MSK).strftime("%d.%m.%Y %H:%M:%S")


def _string_or_none(value: object | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _normalize_username(value: object | None) -> str | None:
    normalized = str(value or "").strip().lstrip("@")
    return normalized or None


def _build_display_name(snapshot, fallback: dict | None = None) -> str:
    first_name = _string_or_none(getattr(snapshot, "first_name", None)) if snapshot is not None else None
    last_name = _string_or_none(getattr(snapshot, "last_name", None)) if snapshot is not None else None
    username = _normalize_username(getattr(snapshot, "username", None)) if snapshot is not None else None

    if fallback is not None:
        first_name = first_name or _string_or_none(fallback.get("first_name"))
        last_name = last_name or _string_or_none(fallback.get("last_name"))
        username = username or _normalize_username(fallback.get("username"))

    full_name = f"{first_name or ''} {last_name or ''}".strip()
    if full_name:
        return full_name
    if username:
        return f"@{username}"

    telegram_user_id = getattr(snapshot, "telegram_user_id", None)
    if telegram_user_id is None and fallback is not None:
        telegram_user_id = fallback.get("telegram_user_id")
    return f"ID {int(telegram_user_id)}"


def _should_send_status_notification(mode: str, became_online: bool) -> bool:
    normalized_mode = (mode or "").strip().lower()
    if normalized_mode == "off":
        return False
    if normalized_mode == "all":
        return True
    if normalized_mode == "online":
        return became_online
    if normalized_mode == "offline":
        return not became_online
    return True


def _format_profile_change_value(change_type: str, value: str | None) -> str:
    normalized = _string_or_none(value)

    if change_type in {"first_name", "last_name"}:
        return normalized or "не указано"

    if change_type == "username":
        return f"@{normalized}" if normalized else "не указан"

    if change_type == "avatar":
        return f"photo_id {normalized}" if normalized else "аватарка отсутствует"

    if change_type == "gifts":
        return f"{normalized} подарков" if normalized is not None else "нет данных"

    return normalized or "не указано"


def _build_status_notification(snapshot, became_online: bool, detected_at: int) -> str:
    display_name = _build_display_name(snapshot)
    username = _normalize_username(getattr(snapshot, "username", None))
    status_text = str(getattr(snapshot, "status_text", None) or "статус не получен").strip()
    profile_link = str(getattr(snapshot, "profile_link", None) or f"tg://user?id={int(snapshot.telegram_user_id)}").strip()

    if became_online:
        icon = "🟢"
        event_text = "вошел(ла) в онлайн [TG]"
    else:
        icon = "🔴"
        event_text = "вышел(ла) из онлайна [TG]"

    lines = [
        f"{icon} <b>{_escape_html(display_name)}</b> {event_text}",
        f"ID: <code>{int(snapshot.telegram_user_id)}</code>",
        f"🕐 Обнаружено: {_format_timestamp(detected_at)}",
        f"Текущий статус: <b>{_escape_html(status_text)}</b>",
    ]
    if username:
        lines.append(f"Username: <code>@{_escape_html(username)}</code>")
    if not became_online and getattr(snapshot, "last_seen_at", None) is not None:
        lines.append(f"Last seen: {_format_timestamp(snapshot.last_seen_at)}")
    lines.append(f"🔗 <a href='{_escape_html(profile_link)}'>{_escape_html(profile_link)}</a>")
    return "\n".join(lines)


def _build_activity_details(old_status: dict | None, snapshot) -> str:
    new_last_seen = getattr(snapshot, "last_seen_at", None)
    old_last_seen = None if old_status is None else old_status.get("last_seen_at")
    if new_last_seen is not None and (old_last_seen is None or int(new_last_seen) > int(old_last_seen)):
        return f"Last seen: {_format_timestamp(int(new_last_seen))}"

    old_kind = "" if old_status is None else str(old_status.get("status_kind") or "")
    new_kind = str(getattr(snapshot, "status_kind", None) or "")
    if new_kind and new_kind != old_kind:
        return f"Сигнал активности: <b>{_escape_html(str(getattr(snapshot, 'status_text', None) or 'обновлен'))}</b>"

    return f"Текущий сигнал: <b>{_escape_html(str(getattr(snapshot, 'status_text', None) or 'обновлен'))}</b>"


def _build_activity_notification(snapshot, old_status: dict | None, detected_at: int) -> str:
    display_name = _build_display_name(snapshot)
    username = _normalize_username(getattr(snapshot, "username", None))
    profile_link = str(getattr(snapshot, "profile_link", None) or f"tg://user?id={int(snapshot.telegram_user_id)}").strip()
    lines = [
        f"🟡 <b>{_escape_html(display_name)}</b> — активность / last seen [TG]",
        f"ID: <code>{int(snapshot.telegram_user_id)}</code>",
        f"🕐 Обнаружено: {_format_timestamp(detected_at)}",
        _build_activity_details(old_status, snapshot),
    ]
    if username:
        lines.append(f"Username: <code>@{_escape_html(username)}</code>")
    lines.append(f"🔗 <a href='{_escape_html(profile_link)}'>{_escape_html(profile_link)}</a>")
    return "\n".join(lines)


def _is_activity_signal(old_status: dict | None, snapshot) -> bool:
    if old_status is None:
        return False

    if getattr(snapshot, "is_online", None) is True:
        return False

    if old_status.get("is_online") is True and getattr(snapshot, "is_online", None) is False:
        return False

    new_last_seen = getattr(snapshot, "last_seen_at", None)
    old_last_seen = old_status.get("last_seen_at")
    if new_last_seen is not None and (old_last_seen is None or int(new_last_seen) > int(old_last_seen)):
        return True

    new_kind = str(getattr(snapshot, "status_kind", None) or "unknown")
    if new_kind in {"unknown", "hidden"}:
        return False

    old_kind = str(old_status.get("status_kind") or "unknown")
    new_rank = ACTIVITY_KIND_RANK.get(new_kind, 0)
    old_rank = ACTIVITY_KIND_RANK.get(old_kind, 0)
    return new_rank > old_rank


def _build_profile_change_records(old_known_user: dict | None, snapshot) -> list[dict]:
    if old_known_user is None:
        return []

    changes: list[dict] = []

    old_first_name = _string_or_none(old_known_user.get("first_name"))
    new_first_name = _string_or_none(snapshot.first_name)
    if old_first_name != new_first_name:
        changes.append(
            {
                "change_type": "first_name",
                "old_value": old_first_name,
                "new_value": new_first_name,
            }
        )

    old_last_name = _string_or_none(old_known_user.get("last_name"))
    new_last_name = _string_or_none(snapshot.last_name)
    if old_last_name != new_last_name:
        changes.append(
            {
                "change_type": "last_name",
                "old_value": old_last_name,
                "new_value": new_last_name,
            }
        )

    old_username = _normalize_username(old_known_user.get("username"))
    new_username = _normalize_username(snapshot.username)
    if old_username != new_username:
        changes.append(
            {
                "change_type": "username",
                "old_value": old_username,
                "new_value": new_username,
            }
        )

    old_avatar = _string_or_none(old_known_user.get("avatar_photo_id"))
    new_avatar = _string_or_none(snapshot.avatar_photo_id)
    if old_avatar != new_avatar:
        changes.append(
            {
                "change_type": "avatar",
                "old_value": old_avatar,
                "new_value": new_avatar,
                "metadata": {
                    "old_dc_id": old_known_user.get("avatar_dc_id"),
                    "new_dc_id": snapshot.avatar_dc_id,
                },
            }
        )

    old_gifts_count = old_known_user.get("gifts_count")
    new_gifts_count = snapshot.gifts_count
    if (
        snapshot.gifts_supported is True
        and old_gifts_count is not None
        and new_gifts_count is not None
        and int(old_gifts_count) != int(new_gifts_count)
    ):
        changes.append(
            {
                "change_type": "gifts",
                "old_value": str(old_gifts_count),
                "new_value": str(new_gifts_count),
                "metadata": {
                    "count_only": True,
                    "note": "Клиентский слой дает только счетчик подарков, без списка самих подарков.",
                },
            }
        )

    old_bio = _string_or_none(old_known_user.get("bio"))
    new_bio = _string_or_none(snapshot.bio)
    if old_bio != new_bio:
        changes.append(
            {
                "change_type": "bio",
                "old_value": old_bio,
                "new_value": new_bio,
            }
        )

    return changes


def _build_profile_change_notification(snapshot, changes: list[dict]) -> str:
    display_name = _build_display_name(snapshot)
    username = _normalize_username(getattr(snapshot, "username", None))
    profile_link = str(getattr(snapshot, "profile_link", None) or f"tg://user?id={int(snapshot.telegram_user_id)}").strip()

    lines = [
        f"📝 <b>{_escape_html(display_name)}</b> — изменения профиля [TG]",
        f"ID: <code>{int(snapshot.telegram_user_id)}</code>",
    ]
    if username:
        lines.append(f"Username: <code>@{_escape_html(username)}</code>")
    lines.append(f"🔗 <a href='{_escape_html(profile_link)}'>{_escape_html(profile_link)}</a>")
    lines.append("")
    lines.append("<b>Изменения:</b>")

    for change in changes:
        change_type = str(change.get("change_type") or "")
        label = TG_CHANGE_LABELS.get(change_type, change_type)
        old_value = _format_profile_change_value(change_type, change.get("old_value"))
        new_value = _format_profile_change_value(change_type, change.get("new_value"))
        metadata = change.get("metadata") or {}

        if change_type == "gifts" and bool(metadata.get("count_only")):
            lines.append(
                f"• <b>{_escape_html(label)}</b>: "
                f"<code>{_escape_html(old_value)}</code> → <code>{_escape_html(new_value)}</code> "
                "(доступен только счетчик)"
            )
            continue

        lines.append(
            f"• <b>{_escape_html(label)}</b>: "
            f"<code>{_escape_html(old_value)}</code> → <code>{_escape_html(new_value)}</code>"
        )

    return "\n".join(lines)


def _filter_profile_changes_by_settings(changes: list[dict], settings: dict[str, bool]) -> list[dict]:
    filtered: list[dict] = []
    for change in changes:
        change_type = str(change.get("change_type") or "")
        settings_key = TG_CHANGE_SETTING_KEYS.get(change_type)
        if settings_key is None:
            continue
        if bool(settings.get(settings_key, True)):
            filtered.append(change)
    return filtered


def _build_online_history_record(old_status: dict, snapshot) -> dict | None:
    old_is_online = old_status.get("is_online")
    new_is_online = snapshot.is_online
    if old_is_online is None or new_is_online is None:
        return None
    if bool(old_is_online) == bool(new_is_online):
        return None

    return {
        "change_type": "online",
        "old_value": "online" if bool(old_is_online) else "offline",
        "new_value": "online" if bool(new_is_online) else "offline",
        "metadata": {
            "old_status_text": old_status.get("status_text"),
            "new_status_text": snapshot.status_text,
        },
    }


def _build_activity_history_record(old_status: dict, snapshot) -> dict | None:
    if not _is_activity_signal(old_status, snapshot):
        return None

    old_last_seen = old_status.get("last_seen_at")
    new_last_seen = getattr(snapshot, "last_seen_at", None)
    if new_last_seen is not None and (old_last_seen is None or int(new_last_seen) > int(old_last_seen)):
        return {
            "change_type": "activity",
            "old_value": _format_timestamp(old_last_seen) if old_last_seen is not None else str(old_status.get("status_text") or "неизвестно"),
            "new_value": _format_timestamp(int(new_last_seen)),
            "metadata": {
                "mode": "last_seen",
                "old_kind": old_status.get("status_kind"),
                "new_kind": snapshot.status_kind,
            },
        }

    return {
        "change_type": "activity",
        "old_value": str(old_status.get("status_text") or "неизвестно"),
        "new_value": str(snapshot.status_text or "неизвестно"),
        "metadata": {
            "mode": "activity_signal",
            "old_kind": old_status.get("status_kind"),
            "new_kind": snapshot.status_kind,
        },
    }


async def _reconcile_tg_sessions(chat_id: int, snapshot, now_ts: int) -> None:
    telegram_user_id = int(snapshot.telegram_user_id)
    open_session = await db.get_tg_open_session(chat_id, telegram_user_id)

    if snapshot.is_online is True and open_session is None:
        started_at = int(getattr(snapshot, "activity_at", None) or now_ts)
        await db.start_tg_online_session(chat_id, telegram_user_id, started_at)
        logger.info(
            "Открыта TG онлайн-сессия: chat_id=%s, telegram_user_id=%s, started_at=%s",
            chat_id,
            telegram_user_id,
            started_at,
        )
        return

    if snapshot.is_online is False and open_session is not None:
        ended_at = int(getattr(snapshot, "last_seen_at", None) or getattr(snapshot, "activity_at", None) or now_ts)
        if ended_at < int(open_session["started_at"]):
            ended_at = now_ts
        await db.end_tg_online_session(chat_id, telegram_user_id, ended_at)
        logger.info(
            "Закрыта TG онлайн-сессия: chat_id=%s, telegram_user_id=%s, ended_at=%s",
            chat_id,
            telegram_user_id,
            ended_at,
        )


def _build_watchers_by_tg(pairs: list[tuple[int, int]]) -> tuple[list[int], dict[int, list[int]]]:
    tg_ids = list({telegram_user_id for _, telegram_user_id in pairs})
    watchers_by_tg: dict[int, list[int]] = {}
    for chat_id, telegram_user_id in pairs:
        watchers_by_tg.setdefault(telegram_user_id, []).append(chat_id)
    return tg_ids, watchers_by_tg


async def _check_telegram_and_notify(bot: Bot) -> None:
    pairs = await db.get_all_active_tg_pairs()
    if not pairs:
        return

    tg_ids, watchers_by_tg = _build_watchers_by_tg(pairs)
    now_ts = int(time.time())
    notification_mode_cache: dict[int, str] = {}
    activity_enabled_cache: dict[int, bool] = {}
    change_settings_cache: dict[int, dict[str, bool]] = {}

    async def _get_tg_mode(chat_id: int) -> str:
        if chat_id not in notification_mode_cache:
            notification_mode_cache[chat_id] = await db.get_tg_notification_mode(chat_id)
        return notification_mode_cache[chat_id]

    async def _get_tg_activity_enabled(chat_id: int) -> bool:
        if chat_id not in activity_enabled_cache:
            activity_enabled_cache[chat_id] = await db.get_tg_activity_notification_enabled(chat_id)
        return activity_enabled_cache[chat_id]

    async def _get_tg_change_settings(chat_id: int) -> dict[str, bool]:
        if chat_id not in change_settings_cache:
            change_settings_cache[chat_id] = await db.get_tg_change_notification_settings(chat_id)
        return change_settings_cache[chat_id]

    for telegram_user_id in tg_ids:
        related_chat_ids = watchers_by_tg.get(telegram_user_id, [])
        known_user = await db.get_tg_known_user_by_id(telegram_user_id)

        if known_user is None and related_chat_ids:
            seed_detail = await db.get_tg_tracked_user_detail(related_chat_ids[0], telegram_user_id)
            if seed_detail is not None:
                known_user = {
                    "telegram_user_id": seed_detail["telegram_user_id"],
                    "username": seed_detail.get("username"),
                    "first_name": seed_detail.get("first_name"),
                    "last_name": seed_detail.get("last_name"),
                    "access_hash": seed_detail.get("access_hash"),
                    "profile_link": seed_detail.get("profile_link"),
                    "avatar_photo_id": seed_detail.get("avatar_photo_id"),
                    "avatar_dc_id": seed_detail.get("avatar_dc_id"),
                    "avatar_has_video": seed_detail.get("avatar_has_video"),
                    "gifts_count": seed_detail.get("gifts_count"),
                    "gifts_supported": seed_detail.get("gifts_supported"),
                    "is_bot": False,
                }

        if known_user is None:
            logger.warning("TG user_id=%s отсутствует в локальном кеше, пропускаем мониторинг", telegram_user_id)
            continue

        try:
            snapshot = await fetch_telegram_user_snapshot(
                telegram_user_id=telegram_user_id,
                access_hash=known_user.get("access_hash"),
                username=known_user.get("username"),
            )
        except TelegramResolverNotFoundError:
            logger.warning("Не удалось обновить TG user_id=%s: пользователь не найден", telegram_user_id)
            continue
        except TelegramResolverPeerTypeError:
            logger.warning("Не удалось обновить TG user_id=%s: объект не является обычным пользователем", telegram_user_id)
            continue
        except TelegramResolverUnavailableError as exc:
            logger.warning("TG resolver временно недоступен для user_id=%s: %s", telegram_user_id, exc)
            continue
        except Exception as exc:
            logger.exception("Ошибка при обновлении TG user_id=%s: %s", telegram_user_id, exc)
            continue

        old_status = await db.get_tg_last_status(telegram_user_id)
        profile_changes = _build_profile_change_records(known_user, snapshot)
        
        # Системная дедупликация: не уведомляем и не пишем в историю, если новое значение совпадает с последним записанным
        deduplicated_changes = []
        if profile_changes:
            for change in profile_changes:
                last_recorded = await db.get_last_tg_profile_change(telegram_user_id, change["change_type"])
                if last_recorded and last_recorded.get("new_value") == change.get("new_value"):
                    continue
                deduplicated_changes.append(change)
        
        if deduplicated_changes:
            await db.add_tg_profile_changes(telegram_user_id, deduplicated_changes, now_ts)
        
        # Обновляем состояние в любом случае, чтобы кэш был свежим
        await db.upsert_tg_known_user(
            telegram_user_id=int(snapshot.telegram_user_id),
            username=snapshot.username,
            first_name=snapshot.first_name,
            last_name=snapshot.last_name,
            access_hash=snapshot.access_hash,
            profile_link=snapshot.profile_link,
            avatar_photo_id=snapshot.avatar_photo_id,
            avatar_dc_id=snapshot.avatar_dc_id,
            avatar_has_video=snapshot.avatar_has_video,
            gifts_count=snapshot.gifts_count,
            gifts_supported=snapshot.gifts_supported,
            is_bot=snapshot.is_bot,
        )
        await db.sync_tg_tracked_user_profile(
            int(snapshot.telegram_user_id),
            username=snapshot.username,
            first_name=snapshot.first_name,
            last_name=snapshot.last_name,
        )
        await db.save_tg_last_status(
            telegram_user_id=int(snapshot.telegram_user_id),
            status_text=snapshot.status_text,
            last_seen_at=snapshot.last_seen_at,
            is_online=snapshot.is_online,
            status_kind=snapshot.status_kind,
            activity_at=snapshot.activity_at,
        )

        for chat_id in related_chat_ids:
            try:
                await _reconcile_tg_sessions(chat_id, snapshot, now_ts)
            except Exception as exc:
                logger.error(
                    "Не удалось синхронизировать TG сессию chat_id=%s, telegram_user_id=%s: %s",
                    chat_id,
                    telegram_user_id,
                    exc,
                )

        if profile_changes:
            for chat_id in related_chat_ids:
                try:
                    settings = await _get_tg_change_settings(chat_id)
                    filtered_changes = _filter_profile_changes_by_settings(deduplicated_changes, settings)
                    if not filtered_changes:
                        continue
                    m_hash = hashlib.md5(f"tg_profile|{chat_id}|{telegram_user_id}|{now_ts}".encode()).hexdigest()
                    await db.enqueue_outbox_message(
                        source="tg",
                        chat_id=chat_id,
                        text=_build_profile_change_notification(snapshot, filtered_changes),
                        message_hash=m_hash,
                        parse_mode="HTML",
                        disable_preview=True,
                    )
                except Exception as exc:
                    logger.error(
                        "Не удалось добавить TG уведомление об изменениях профиля в очередь chat_id=%s, telegram_user_id=%s: %s",
                        chat_id,
                        telegram_user_id,
                        exc,
                    )

        if old_status is None:
            continue

        online_history_record = _build_online_history_record(old_status, snapshot)
        if online_history_record is not None:
            # Дедупликация для статуса
            last_online_change = await db.get_last_tg_profile_change(telegram_user_id, "online")
            if last_online_change is None or last_online_change.get("new_value") != online_history_record.get("new_value"):
                await db.add_tg_profile_changes(telegram_user_id, [online_history_record], now_ts)
                notification_text = _build_status_notification(snapshot, bool(snapshot.is_online), now_ts)
                for chat_id in related_chat_ids:
                    try:
                        notification_mode = await _get_tg_mode(chat_id)
                        if not _should_send_status_notification(notification_mode, bool(snapshot.is_online)):
                            continue
                        m_hash = hashlib.md5(f"tg_status|{chat_id}|{telegram_user_id}|{snapshot.is_online}|{now_ts}".encode()).hexdigest()
                        await db.enqueue_outbox_message(
                            source="tg",
                            chat_id=chat_id,
                            text=notification_text,
                            message_hash=m_hash,
                            parse_mode="HTML",
                            disable_preview=True,
                        )
                    except Exception as exc:
                        logger.error(
                            "Не удалось добавить TG статус-уведомление в очередь chat_id=%s, telegram_user_id=%s: %s",
                            chat_id,
                            telegram_user_id,
                            exc,
                        )
            continue

        activity_history_record = _build_activity_history_record(old_status, snapshot)
        if activity_history_record is not None:
            # Дедупликация для активности
            last_activity = await db.get_last_tg_profile_change(telegram_user_id, "activity")
            if last_activity is None or last_activity.get("new_value") != activity_history_record.get("new_value"):
                await db.add_tg_profile_changes(telegram_user_id, [activity_history_record], now_ts)
                activity_text = _build_activity_notification(snapshot, old_status, now_ts)
                for chat_id in related_chat_ids:
                    try:
                        if not await _get_tg_activity_enabled(chat_id):
                            continue
                        m_hash = hashlib.md5(f"tg_activity|{chat_id}|{telegram_user_id}|{snapshot.activity_at}|{now_ts}".encode()).hexdigest()
                        await db.enqueue_outbox_message(
                            source="tg",
                            chat_id=chat_id,
                            text=activity_text,
                            message_hash=m_hash,
                            parse_mode="HTML",
                            disable_preview=True,
                        )
                    except Exception as exc:
                        logger.error(
                            "Не удалось добавить TG уведомление об активности в очередь chat_id=%s, telegram_user_id=%s: %s",
                            chat_id,
                            telegram_user_id,
                            exc,
                        )


async def run_telegram_monitor(bot: Bot) -> None:
    logger.info("Telegram-monitor запущен. Проверка статусов и профиля: раз в %s сек.", ONLINE_CHECK_INTERVAL)
    while True:
        loop_started_at = time.time()
        try:
            await _check_telegram_and_notify(bot)
        except asyncio.CancelledError:
            logger.info("Telegram-monitor остановлен.")
            break
        except Exception as exc:
            logger.exception("Ошибка в цикле Telegram-monitor: %s", exc)

        sleep_for = max(ONLINE_CHECK_INTERVAL - (time.time() - loop_started_at), 0)
        await asyncio.sleep(sleep_for)
