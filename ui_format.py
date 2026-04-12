"""
Слой форматирования (View) — содержит шаблоны сообщений, подписи и вспомогательные функции для построения HTML-ответов.
"""

import html
from datetime import datetime, timedelta, timezone
from typing import Any

from aiogram.types import Message, CallbackQuery

import db
import vk_api

MSK = timezone(timedelta(hours=3))
UTC = timezone.utc

# --- Константы подписей и фильтров ---

NOTIFICATION_MODE_LABELS = {
    "online": "только вход в онлайн",
    "offline": "только выход из онлайна",
    "all": "вход и выход",
    "off": "уведомления о статусе отключены",
}

PROFILE_CARD_FIELD_META = [
    ("profile_status_text", "💭", "Текстовый статус"),
    ("domain", "🔑", "Короткая ссылка"),
    ("is_closed", "🔒", "Профиль"),
    ("friends_count", "👥", "Друзья"),
    ("followers_count", "📣", "Подписчики"),
    ("subscriptions_count", "➕", "Подписки"),
    ("country", "🌍", "Страна"),
    ("city", "🏙️", "Город"),
    ("bdate", "🎂", "Дата рождения"),
    ("relation", "💞", "Семейное положение"),
    ("site", "🌐", "Сайт"),
    ("about", "📝", "О себе"),
    ("interests", "🎯", "Интересы"),
    ("books", "📚", "Книги"),
    ("movies", "🎬", "Фильмы"),
    ("activities", "⚡", "Деятельность"),
    ("games", "🎮", "Игры"),
    ("quotes", "💬", "Цитаты"),
]

RELATION_PRIVACY_CARD_META = [
    (vk_api.RELATION_LIST_FRIENDS, "👥", "Друзья"),
    (vk_api.RELATION_LIST_FOLLOWERS, "📣", "Подписчики"),
    (vk_api.RELATION_LIST_SUBSCRIPTIONS, "➕", "Подписки"),
]

PROFILE_CHANGE_TYPE_ITEMS: list[tuple[str, str]] = [
    ("👤 Имя", "fn"),
    ("👤 Фамилия", "ln"),
    ("🪪 Имя и фамилия", "nm"),
    ("🖼 Аватарка", "av"),
    ("💬 Статус профиля", "st"),
    ("🔗 Ссылка", "dm"),
    ("🔒 Открыт / закрыт профиль", "cl"),
    ("📝 Поля профиля", "fld"),
    ("📢 Посты", "pst"),
    ("📷 Фото", "pht"),
    ("🎬 Видео", "vid"),
    ("🎵 Музыка", "mus"),
    ("🎧 Аудиозаписи", "aud"),
    ("📊 Счетчики", "cnt"),
    ("⚡ Активность", "act"),
    ("🗂 Все изменения", "all"),
]

PROFILE_CHANGE_FILTERS: dict[str, dict[str, Any]] = {
    "fn": {"label": "Имя", "fields": ["first_name"], "supported": True},
    "ln": {"label": "Фамилия", "fields": ["last_name"], "supported": True},
    "nm": {"label": "Имя и фамилия", "fields": ["first_name", "last_name"], "supported": True},
    "av": {"label": "Аватарка", "fields": ["avatar_url"], "supported": True},
    "st": {"label": "Статус профиля", "fields": ["profile_status_text"], "supported": True},
    "dm": {"label": "Ссылка", "fields": ["domain"], "supported": True},
    "cl": {"label": "Открыт / закрыт профиль", "fields": ["is_closed"], "supported": True},
    "fld": {
        "label": "Поля профиля",
        "fields": ["city", "country", "about", "bdate", "relation", "site", "interests", "books", "movies", "activities", "games", "quotes"],
        "supported": True,
    },
    "pst": {"label": "Посты", "fields": ["wall_post"], "supported": True},
    "pht": {"label": "Фото", "fields": [], "supported": False},
    "vid": {"label": "Видео", "fields": [], "supported": False},
    "mus": {"label": "Музыка", "fields": [], "supported": False},
    "aud": {"label": "Аудиозаписи", "fields": [], "supported": False},
    "cnt": {"label": "Счетчики", "fields": ["friends_count", "followers_count", "subscriptions_count"], "supported": True},
    "act": {"label": "Активность", "fields": [], "supported": False},
    "all": {"label": "Все изменения", "fields": None, "supported": True},
}

PROFILE_CHANGE_LABELS = {"wall_post": "Пост"}

CHANGE_NOTIFICATION_LABELS = {
    "name": "Имя и фамилия",
    "avatar": "Аватарка",
    "status": "Статус профиля",
    "link": "Ссылка на профиль",
    "privacy": "Открыт / закрыт профиль",
    "fields": "Поля профиля",
    "posts": "Посты",
    "counts": "Счетчики",
    "relations": "Друзья / подписчики / подписки",
}

TG_NOTIFICATION_TOGGLE_LABELS = {"activity": "Активность / last seen [TG]"}

TG_CHANGE_NOTIFICATION_LABELS = {
    "first_name": "Имя [TG]",
    "last_name": "Фамилия [TG]",
    "username": "Username [TG]",
    "avatar": "Аватарка [TG]",
    "gifts": "Подарки [TG]",
    "bio": "Bio [TG]",
}

TG_PROFILE_CHANGE_TYPE_ITEMS: list[tuple[str, str]] = [
    ("🗂️ Все изменения [TG]", "all"),
    ("👤 Имя [TG]", "first_name"),
    ("👤 Фамилия [TG]", "last_name"),
    ("🔗 Username [TG]", "username"),
    ("🖼️ Аватарка [TG]", "avatar"),
    ("🎁 Подарки [TG]", "gifts"),
    ("📝 Bio [TG]", "bio"),
    ("🟡 Активность / last seen [TG]", "activity"),
    ("🟢🔴 Онлайн изменения [TG]", "online"),
]

TG_PROFILE_CHANGE_FILTERS: dict[str, dict[str, Any]] = {
    "all": {"label": "Все изменения [TG]", "types": None, "supported": True},
    "first_name": {"label": "Имя [TG]", "types": ["first_name"], "supported": True},
    "last_name": {"label": "Фамилия [TG]", "types": ["last_name"], "supported": True},
    "username": {"label": "Username [TG]", "types": ["username"], "supported": True},
    "avatar": {"label": "Аватарка [TG]", "types": ["avatar"], "supported": True},
    "gifts": {"label": "Подарки [TG]", "types": ["gifts"], "supported": True},
    "bio": {"label": "Bio [TG]", "types": ["bio"], "supported": True},
    "activity": {"label": "Активность / last seen [TG]", "types": ["activity"], "supported": True},
    "online": {"label": "Онлайн изменения [TG]", "types": ["online"], "supported": True},
}


# --- Базовые утилиты форматирования ---

def escape_html(value: Any) -> str:
    return html.escape(str(value), quote=True)


def truncate_text(value: str, limit: int = 280) -> str:
    normalized = value.strip()
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit - 1]}…"


def format_duration(total_seconds: int) -> str:
    if total_seconds < 0:
        total_seconds = 0

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    parts = []
    if hours:
        parts.append(f"{hours} ч")
    if minutes:
        parts.append(f"{minutes} мин")
    if seconds or not parts:
        parts.append(f"{seconds} сек")
    return " ".join(parts)


def format_period_label(days: int) -> str:
    if days == 1:
        return "1 день"
    if days == 7:
        return "7 дней"
    if days == 30:
        return "30 дней"
    return "все время"


def format_added_at(sqlite_dt: str | None) -> str:
    if not sqlite_dt:
        return "неизвестно"

    try:
        dt = datetime.strptime(sqlite_dt, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return sqlite_dt

    return dt.astimezone(MSK).strftime("%d.%m.%Y %H:%M:%S")


# --- VK Специфичное форматирование ---

def build_vk_name(first_name: str, last_name: str, vk_id: int) -> str:
    return f"{first_name} {last_name}".strip() or f"ID {vk_id}"


def build_vk_status_line(online: int) -> str:
    return "🟢 онлайн" if online else "🔴 офлайн"


def parse_wall_post_value(value: str | None) -> tuple[str | None, str | None]:
    normalized = (value or "").strip()
    if not normalized:
        return None, None

    lines = normalized.splitlines()
    first_line = lines[0].strip() if lines else ""
    if first_line.startswith("http://") or first_line.startswith("https://"):
        text = "\n".join(lines[1:]).strip() or None
        return first_line, text
    return None, normalized


def build_profile_change_block(change: dict) -> str:
    field_name = str(change.get("field_name") or "")
    changed_at = vk_api.format_timestamp(int(change["changed_at"]))
    label = PROFILE_CHANGE_LABELS.get(field_name, vk_api.PROFILE_FIELD_LABELS.get(field_name, field_name))

    if field_name == "avatar_url":
        return f"• {changed_at} — <b>{escape_html(label)}</b>: аватарка изменена"

    if field_name == "wall_post":
        post_link, post_text = parse_wall_post_value(change.get("new_value"))
        lines = [f"• {changed_at} — <b>{escape_html(label)}</b>: новый пост"]
        if post_link:
            lines.append(f"🔗 <a href='{escape_html(post_link)}'>{escape_html(post_link)}</a>")
        if post_text:
            lines.append(f"Текст: <code>{escape_html(truncate_text(post_text, 220))}</code>")
        return "\n".join(lines)

    old_value = truncate_text(vk_api.format_profile_field_value(field_name, change.get("old_value")), 220)
    new_value = truncate_text(vk_api.format_profile_field_value(field_name, change.get("new_value")), 220)
    return (
        f"• {changed_at} — <b>{escape_html(label)}</b>\n"
        f"Было: <code>{escape_html(old_value)}</code>\n"
        f"Стало: <code>{escape_html(new_value)}</code>"
    )


async def build_relation_privacy_lines(vk_id: int) -> list[str]:
    lines: list[str] = []
    for list_type, icon, label in RELATION_PRIVACY_CARD_META:
        meta = await db.get_profile_list_meta(vk_id, list_type)
        if meta is None or int(meta.get("is_complete") or 0) == 1:
            continue

        reason = str(meta.get("last_reason") or "").strip()
        is_blocked = "скрыт" in reason.lower() or "не отдал список" in reason.lower() or "недоступ" in reason.lower()
        
        if is_blocked:
            lines.append(f"{icon} {label}: скрыты настройками приватности, точное отслеживание невозможно")
        elif reason:
            lines.append(f"{icon} {label}: точное отслеживание недоступно ({escape_html(truncate_text(reason, 120))})")
        else:
            lines.append(f"{icon} {label}: точное отслеживание недоступно")
    return lines


# --- TG Специфичное форматирование ---

def build_tg_display_name(item: dict) -> str:
    first_name = str(item.get("first_name") or "").strip()
    last_name = str(item.get("last_name") or "").strip()
    username = str(item.get("username") or "").strip()
    full_name = f"{first_name} {last_name}".strip()
    if full_name:
        return full_name
    if username:
        return f"@{username}"
    return f"ID {item['telegram_user_id']}"


def build_tg_status_label(detail: dict) -> str:
    if detail.get("is_online") is True:
        return "🟢 онлайн"

    status_text = str(detail.get("status_text") or "").strip()
    if not status_text:
        return "статус еще не зафиксирован"

    if detail.get("last_seen_at") is not None:
        return f"🔴 {status_text}"

    if detail.get("status_kind") in {"recently", "last_week", "last_month", "hidden"}:
        return f"🟡 {status_text}"

    return status_text


def build_tg_activity_line(detail: dict) -> str:
    if detail.get("last_seen_at") is not None:
        return f"Last seen: {vk_api.format_timestamp(int(detail['last_seen_at']))}"

    if detail.get("activity_at") is not None:
        return f"Последняя активность: {vk_api.format_timestamp(int(detail['activity_at']))}"

    return "Последняя активность: пока не зафиксирована"


def format_tg_change_value(change_type: str, value: str | None, metadata: dict | None = None) -> str:
    normalized = (value or "").strip()
    metadata = metadata or {}

    if change_type in {"first_name", "last_name"}:
        return normalized or "не указано"

    if change_type == "username":
        return f"@{normalized}" if normalized else "не указан"

    if change_type == "avatar":
        return f"photo_id {normalized}" if normalized else "аватарка отсутствует"

    if change_type == "gifts":
        if normalized.isdigit():
            return f"{normalized} подарков"
        return normalized or "нет данных"

    if change_type == "online":
        if normalized == "online":
            return "онлайн"
        if normalized == "offline":
            return "офлайн"
        return normalized or "неизвестно"

    if change_type == "activity":
        return normalized or "неизвестно"

    if change_type == "bio":
        return normalized or "описание удалено"

    return normalized or "не указано"


def build_tg_profile_change_block(change: dict) -> str:
    change_type = str(change.get("change_type") or "")
    changed_at = vk_api.format_timestamp(int(change["changed_at"]))
    meta = change.get("metadata") or {}
    label = TG_PROFILE_CHANGE_FILTERS.get(change_type, {"label": change_type}).get("label", change_type)

    if change_type == "avatar":
        old_value = format_tg_change_value(change_type, change.get("old_value"), meta)
        new_value = format_tg_change_value(change_type, change.get("new_value"), meta)
        return (
            f"• {changed_at} — <b>{escape_html(label)}</b>\n"
            f"Было: <code>{escape_html(old_value)}</code>\n"
            f"Стало: <code>{escape_html(new_value)}</code>"
        )

    if change_type == "gifts" and bool(meta.get("count_only", False)):
        old_value = format_tg_change_value(change_type, change.get("old_value"), meta)
        new_value = format_tg_change_value(change_type, change.get("new_value"), meta)
        return (
            f"• {changed_at} — <b>{escape_html(label)}</b>\n"
            f"Счетчик: <code>{escape_html(old_value)}</code> → <code>{escape_html(new_value)}</code>\n"
            "Доступен только счетчик подарков, без списка самих подарков."
        )

    old_value = format_tg_change_value(change_type, change.get("old_value"), meta)
    new_value = format_tg_change_value(change_type, change.get("new_value"), meta)

    if change_type == "bio":
        return (
            f"• {changed_at} — <b>{escape_html(label)}</b>\n"
            f"Было: <code>{escape_html(truncate_text(old_value, 150))}</code>\n"
            f"Стало: <code>{escape_html(truncate_text(new_value, 150))}</code>"
        )

    return (
        f"• {changed_at} — <b>{escape_html(label)}</b>\n"
        f"Было: <code>{escape_html(old_value)}</code>\n"
        f"Стало: <code>{escape_html(new_value)}</code>"
    )

# --- Сессии ---

def format_session_block(index: int, started_at: int, ended_at: int | None) -> str:
    start_dt = datetime.fromtimestamp(started_at, tz=MSK)
    start_date = start_dt.strftime("%d.%m.%Y")
    start_time = start_dt.strftime("%H:%M:%S")

    if ended_at is None:
        end_time = "до сих пор онлайн"
        duration_seconds = int(datetime.now(tz=MSK).timestamp()) - started_at
        duration_text = format_duration(duration_seconds)
    else:
        end_dt = datetime.fromtimestamp(ended_at, tz=MSK)
        end_time = end_dt.strftime("%H:%M:%S")
        duration_seconds = ended_at - started_at
        duration_text = format_duration(duration_seconds)

    return (
        f"{index}.\n"
        f"Дата: {start_date}\n"
        f"Зашел: {start_time}\n"
        f"Вышел: {end_time}\n"
        f"Был онлайн: {duration_text}"
    )


def format_tg_session_block(index: int, session: dict, since_ts: int | None, now_ts: int) -> str:
    started_at = int(session["started_at"])
    ended_at = int(session["ended_at"]) if session["ended_at"] is not None else None
    effective_started_at = max(started_at, since_ts) if since_ts is not None else started_at
    effective_ended_at = min(ended_at if ended_at is not None else now_ts, now_ts)

    start_dt = datetime.fromtimestamp(started_at, tz=MSK)
    start_date = start_dt.strftime("%d.%m.%Y")
    start_time = start_dt.strftime("%H:%M:%S")
    if since_ts is not None and started_at < since_ts:
        start_time = f"{start_time} (до начала периода)"

    if ended_at is None:
        end_time = "до сих пор онлайн"
    else:
        end_dt = datetime.fromtimestamp(ended_at, tz=MSK)
        end_time = end_dt.strftime("%H:%M:%S")

    duration_text = format_duration(max(effective_ended_at - effective_started_at, 0))
    return (
        f"{index}.\n"
        f"Дата: {start_date}\n"
        f"Зашел: {start_time}\n"
        f"Вышел: {end_time}\n"
        f"Был онлайн: {duration_text}"
    )


def period_to_since_ts(days: int) -> int | None:
    if days <= 0:
        return None
    return int((datetime.now(tz=MSK) - timedelta(days=days)).timestamp())


def session_duration_for_period(session: dict, since_ts: int | None, now_ts: int) -> int:
    started_at = int(session["started_at"])
    ended_at = int(session["ended_at"]) if session.get("ended_at") is not None else now_ts

    effective_start = max(started_at, since_ts) if since_ts is not None else started_at
    effective_end = min(ended_at, now_ts)
    if effective_end <= effective_start:
        return 0
    return effective_end - effective_start


# --- VK Форматирование ---

def format_vk_profile_card(snapshot: dict, privacy_lines: list[str]) -> str:
    name = build_vk_name(snapshot.get("first_name", ""), snapshot.get("last_name", ""), snapshot["vk_id"])
    lines = [
        f"👤 <b>{escape_html(name)}</b>",
        f"ID: <code>{snapshot['vk_id']}</code>",
        f"🔗 <a href='{escape_html(snapshot['profile_link'])}'>{escape_html(snapshot['profile_link'])}</a>",
        f"Статус: {build_vk_status_line(int(snapshot['online']))}",
        f"🕐 Последний визит: {vk_api.format_last_seen(snapshot.get('last_seen'))}",
        f"📅 Добавлен в отслеживание: {format_added_at(snapshot.get('added_at'))}",
    ]

    for field_name, icon, label in PROFILE_CARD_FIELD_META:
        value = snapshot.get(field_name)
        if field_name not in {"is_closed", "profile_status_text"} and value in (None, ""):
            continue

        display_value = vk_api.format_profile_field_value(field_name, value)
        if field_name not in {"is_closed", "profile_status_text"} and display_value == "не указано":
            continue
        if field_name == "profile_status_text" and display_value == "пусто":
            continue

        lines.append(f"{icon} {label}: {escape_html(truncate_text(display_value))}")

    lines.extend(privacy_lines)
    return "\n".join(lines)


def format_vk_period_report(snapshot: dict, sessions: list[dict], days: int, now_ts: int) -> str:
    since_ts = period_to_since_ts(days)
    total_duration = sum(session_duration_for_period(session, since_ts, now_ts) for session in sessions)
    
    name = build_vk_name(snapshot.get("first_name", ""), snapshot.get("last_name", ""), snapshot["vk_id"])
    lines = [
        "<b>📈 Отчет по онлайну [VK]</b>",
        f"👤 <b>{escape_html(name)}</b>",
        f"ID: <code>{snapshot['vk_id']}</code>",
        f"🔗 <a href='{escape_html(snapshot['profile_link'])}'>{escape_html(snapshot['profile_link'])}</a>",
        f"Статус: {build_vk_status_line(int(snapshot['online']))}",
        f"🕐 Последний визит: {vk_api.format_last_seen(snapshot.get('last_seen'))}",
        f"📊 Период: <b>{escape_html(format_period_label(days))}</b>",
        f"Количество заходов: <b>{len(sessions)}</b>",
        f"Суммарное время онлайна: <b>{format_duration(total_duration)}</b>",
        "",
        "<b>Сессии за период:</b>",
    ]

    if sessions:
        for index, session in enumerate(sessions, start=1):
            lines.append(format_session_block(index, int(session["started_at"]), session.get("ended_at")))
            lines.append("")
    else:
        lines.append("🔍 За выбранный период сессий не найдено.")

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def format_vk_general_report_header(days: int) -> str:
    return f"<b>📊 Общий отчет [VK] за период:</b> {escape_html(format_period_label(days))}"


def format_vk_general_report_user_block(snapshot: dict, sessions: list[dict], days: int, now_ts: int) -> str:
    since_ts = period_to_since_ts(days)
    total_duration = sum(session_duration_for_period(session, since_ts, now_ts) for session in sessions)
    name = build_vk_name(snapshot.get("first_name", ""), snapshot.get("last_name", ""), snapshot["vk_id"])
    
    return "\n".join([
        f"<b>{escape_html(name)}</b>",
        f"ID: <code>{snapshot['vk_id']}</code>",
        f"🔗 <a href='{snapshot['profile_link']}'>{snapshot['profile_link']}</a>",
        f"Заходов: <b>{len(sessions)}</b>",
        f"Суммарно онлайн: <b>{format_duration(total_duration)}</b>",
        f"Последний визит: {vk_api.format_last_seen(snapshot.get('last_seen'))}",
    ])


# --- TG Форматирование ---

def format_tg_profile_card(detail: dict) -> str:
    display_name = build_tg_display_name(detail)
    username = str(detail.get("username") or "").strip()
    status_label = build_tg_status_label(detail)
    
    lines = [
        f"👤 <b>{escape_html(display_name)}</b>",
        f"ID: <code>{detail['telegram_user_id']}</code>",
        f"Имя: {escape_html(str(detail.get('first_name') or 'не указано'))}",
        f"Фамилия: {escape_html(str(detail.get('last_name') or 'не указано'))}",
        f"Username: <code>{escape_html('@' + username if username else 'не указан')}</code>",
        f"Добавлен: {format_added_at(detail.get('added_at'))}",
        f"Текущий статус: {escape_html(status_label)}",
        build_tg_activity_line(detail),
    ]
    if detail.get("profile_link"):
        lines.append(f"Ссылка: <a href='{escape_html(str(detail['profile_link']))}'>{escape_html(str(detail['profile_link']))}</a>")
    if detail.get("avatar_photo_id"):
        lines.append(f"Аватар: photo_id <code>{escape_html(str(detail['avatar_photo_id']))}</code>")
    if detail.get("bio"):
        lines.append(f"Bio: <i>{escape_html(str(detail['bio']))}</i>")
    if detail.get("gifts_supported") is True:
        gifts_count = int(detail.get("gifts_count") or 0)
        lines.append(f"Подарки: <b>{gifts_count}</b> (доступен только счетчик)")
    if detail.get("status_updated_at"):
        lines.append(f"Последнее обновление статуса: {format_added_at(detail.get('status_updated_at'))}")
    
    return "\n".join(lines)


def format_tg_period_report(detail: dict, sessions: list[dict], days: int, now_ts: int) -> str:
    since_ts = period_to_since_ts(days)
    total_duration = sum(session_duration_for_period(session, since_ts, now_ts) for session in sessions)
    
    display_name = build_tg_display_name(detail)
    username = str(detail.get("username") or "").strip()
    profile_link = str(detail.get("profile_link") or f"tg://user?id={int(detail['telegram_user_id'])}")
    
    lines = [
        "<b>📈 Отчет по онлайну [TG]</b>",
        f"👤 <b>{escape_html(display_name)}</b>",
        f"ID: <code>{detail['telegram_user_id']}</code>",
        f"Username: <code>{escape_html('@' + username if username else 'не указан')}</code>",
        f"Статус: {escape_html(build_tg_status_label(detail))}",
        build_tg_activity_line(detail),
        f"🔗 <a href='{escape_html(profile_link)}'>{escape_html(profile_link)}</a>",
        f"📊 Период: <b>{escape_html(format_period_label(days))}</b>",
        f"Количество входов: <b>{len(sessions)}</b>",
        f"Суммарное время онлайна: <b>{format_duration(total_duration)}</b>",
        "",
        "<b>Сессии за период:</b>",
    ]

    if sessions:
        for index, session in enumerate(sessions, start=1):
            lines.append(format_tg_session_block(index, session, since_ts, now_ts))
            lines.append("")
    else:
        lines.append("🔍 За выбранный период сессий не найдено.")

    if detail.get("status_kind") in {"recently", "last_week", "last_month", "hidden", "unknown"}:
        lines.append("")
        lines.append(
            "ℹ️ Telegram может отдавать ограниченный last seen. В таких случаях бот показывает activity / last seen как отдельный сигнал."
        )

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def format_tg_general_report_header(days: int) -> str:
    return f"<b>📊 Общий отчет [TG] за период:</b> {escape_html(format_period_label(days))}"


def format_tg_general_report_user_block(detail: dict, sessions: list[dict], days: int, now_ts: int) -> str:
    since_ts = period_to_since_ts(days)
    total_duration = sum(session_duration_for_period(session, since_ts, now_ts) for session in sessions)
    display_name = build_tg_display_name(detail)
    username = str(detail.get("username") or "").strip()
    profile_link = str(detail.get("profile_link") or f"tg://user?id={int(detail['telegram_user_id'])}")
    
    lines = [
        f"<b>{escape_html(display_name)}</b>",
        f"ID: <code>{detail['telegram_user_id']}</code>",
        f"Статус: {escape_html(build_tg_status_label(detail))}",
        build_tg_activity_line(detail),
        f"Заходов: <b>{len(sessions)}</b>",
        f"Суммарно онлайн: <b>{format_duration(total_duration)}</b>",
        f"🔗 <a href='{escape_html(profile_link)}'>{escape_html(profile_link)}</a>",
    ]
    if username:
        lines.insert(2, f"Username: <code>@{escape_html(username)}</code>")
    return "\n".join(lines)


# --- Вспомогательные тексты и кнопки системных экранов ---

def build_subscription_keyboard(channel_link: str) -> list[list[dict]]:
    # Возвращаем структуру для InlineKeyboardMarkup.inline_keyboard
    return [
        [{"text": "Подписаться на канал", "url": channel_link}],
        [{"text": "Проверить подписку", "callback_data": "check_required_subscription"}],
    ]


def get_subscription_required_text(channel_id: str | None) -> str:
    if channel_id is None:
        return (
            "Проверка подписки включена, но канал пока не настроен в конфиге.\n"
            "Добавьте в <code>.env</code> переменную <code>REQUIRED_CHANNEL_ID</code> "
            "в формате <code>-100...</code>, затем перезапустите бота."
        )

    return (
        "Чтобы пользоваться ботом, сначала подпишитесь на указанный канал.\n"
        "После подписки нажмите кнопку «Проверить подписку»."
    )


def get_vk_link_formats_text() -> str:
    return (
        "Поддерживаются форматы:\n"
        "• <code>123456789</code>\n"
        "• <code>durov</code>\n"
        "• <code>@durov</code>\n"
        "• <code>vk.com/durov</code>\n"
        "• <code>https://vk.com/durov</code>\n"
        "• <code>vk.ru/durov</code>\n"
        "• <code>https://vk.ru/durov</code>"
    )
