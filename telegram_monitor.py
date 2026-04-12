"""
Фоновый Telegram-monitor.
Получает статусы пользователей через MTProto userbot, ведет историю сессий,
обновляет last seen / activity и отправляет TG-уведомления по отдельным настройкам.
"""

from __future__ import annotations

import asyncio
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


def _escape_html(value: object) -> str:
    return html.escape(str(value), quote=True)


def _format_timestamp(ts: int | None) -> str:
    if ts is None:
        return "неизвестно"
    return datetime.fromtimestamp(int(ts), tz=MSK).strftime("%d.%m.%Y %H:%M:%S")


def _build_display_name(snapshot) -> str:
    first_name = str(getattr(snapshot, "first_name", None) or "").strip()
    last_name = str(getattr(snapshot, "last_name", None) or "").strip()
    username = str(getattr(snapshot, "username", None) or "").strip()
    full_name = f"{first_name} {last_name}".strip()
    if full_name:
        return full_name
    if username:
        return f"@{username}"
    return f"ID {int(snapshot.telegram_user_id)}"


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


def _build_status_notification(snapshot, became_online: bool, detected_at: int) -> str:
    display_name = _build_display_name(snapshot)
    username = str(getattr(snapshot, "username", None) or "").strip()
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
    username = str(getattr(snapshot, "username", None) or "").strip()
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

    async def _get_tg_mode(chat_id: int) -> str:
        if chat_id not in notification_mode_cache:
            notification_mode_cache[chat_id] = await db.get_tg_notification_mode(chat_id)
        return notification_mode_cache[chat_id]

    async def _get_tg_activity_enabled(chat_id: int) -> bool:
        if chat_id not in activity_enabled_cache:
            activity_enabled_cache[chat_id] = await db.get_tg_activity_notification_enabled(chat_id)
        return activity_enabled_cache[chat_id]

    for telegram_user_id in tg_ids:
        known_user = await db.get_tg_known_user_by_id(telegram_user_id)
        if known_user is None:
            logger.warning("TG user_id=%s отсутствует в tg_known_users, пропускаем мониторинг", telegram_user_id)
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
            is_bot=snapshot.is_bot,
        )
        await db.save_tg_last_status(
            telegram_user_id=int(snapshot.telegram_user_id),
            status_text=snapshot.status_text,
            last_seen_at=snapshot.last_seen_at,
            is_online=snapshot.is_online,
            status_kind=snapshot.status_kind,
            activity_at=snapshot.activity_at,
        )

        related_chat_ids = watchers_by_tg.get(telegram_user_id, [])
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

        if old_status is None:
            continue

        old_is_online = old_status.get("is_online")
        new_is_online = snapshot.is_online
        if old_is_online is not None and new_is_online is not None and bool(old_is_online) != bool(new_is_online):
            notification_text = _build_status_notification(snapshot, bool(new_is_online), now_ts)
            for chat_id in related_chat_ids:
                try:
                    notification_mode = await _get_tg_mode(chat_id)
                    if not _should_send_status_notification(notification_mode, bool(new_is_online)):
                        continue
                    await bot.send_message(
                        chat_id,
                        notification_text,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                except Exception as exc:
                    logger.error(
                        "Не удалось отправить TG статус-уведомление chat_id=%s, telegram_user_id=%s: %s",
                        chat_id,
                        telegram_user_id,
                        exc,
                    )
            continue

        if not _is_activity_signal(old_status, snapshot):
            continue

        activity_text = _build_activity_notification(snapshot, old_status, now_ts)
        for chat_id in related_chat_ids:
            try:
                if not await _get_tg_activity_enabled(chat_id):
                    continue
                await bot.send_message(
                    chat_id,
                    activity_text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            except Exception as exc:
                logger.error(
                    "Не удалось отправить TG activity-уведомление chat_id=%s, telegram_user_id=%s: %s",
                    chat_id,
                    telegram_user_id,
                    exc,
                )


async def run_telegram_monitor(bot: Bot) -> None:
    logger.info("Telegram-monitor запущен. Проверка статусов: раз в %s сек.", ONLINE_CHECK_INTERVAL)
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
