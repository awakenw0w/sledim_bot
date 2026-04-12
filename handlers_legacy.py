"""
Основные обработчики Telegram-бота.
Бот поддерживает кнопочный интерфейс как основной сценарий и команды как резервный путь.
"""

import html
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from aiogram import F, Router
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
    SharedUser,
)

import db
import vk_api
from config import REQUIRED_CHANNEL_ID, REQUIRED_CHANNEL_LINK
from telegram_resolver import (
    TelegramResolverInvalidInputError,
    TelegramResolverNotFoundError,
    TelegramResolverPeerTypeError,
    TelegramResolverUnavailableError,
    normalize_telegram_lookup,
    resolve_telegram_user,
)
from ui_callbacks import (
    DeleteConfirmCallback,
    NavCallback,
    NotifyModeCallback,
    NotifyToggleCallback,
    PeriodSelectCallback,
    ProfileChangePeriodCallback,
    ProfileChangeTypeCallback,
    ProfileChangeUserCallback,
    TgDeleteConfirmCallback,
    TgNotifyModeCallback,
    TgProfileChangePeriodCallback,
    TgProfileChangeTypeCallback,
    TgNotifyToggleCallback,
    TgPeriodSelectCallback,
    TgUserActionCallback,
    UserActionCallback,
)
from ui_keyboards import (
    BTN_ADD_USER_TG,
    BTN_ADD_USER,
    BTN_BACK,
    BTN_GENERAL_REPORT,
    BTN_GENERAL_REPORT_TG,
    BTN_GENERAL_REPORT_VK,
    BTN_HELP,
    BTN_MAIN_MENU,
    BTN_NOTIFY,
    BTN_NOTIFY_TG,
    BTN_NOTIFY_VK,
    BTN_ONLINE_REPORT,
    BTN_PLATFORM_TG,
    BTN_PLATFORM_VK,
    BTN_PROFILE_CHANGES,
    BTN_SEARCH,
    BTN_TRACKED_LIST_TG,
    BTN_TRACKED_LIST,
    CHANGE_NOTIFICATION_OPTIONS,
    back_main_inline_keyboard,
    delete_confirm_keyboard,
    general_report_result_keyboard_with_target,
    main_menu_keyboard,
    notification_settings_keyboard,
    notifications_hub_keyboard,
    platform_section_keyboard,
    profile_change_period_keyboard,
    profile_change_result_keyboard,
    profile_change_type_keyboard,
    profile_change_user_keyboard,
    reports_hub_keyboard,
    report_period_keyboard,
    report_result_keyboard,
    tg_add_user_reply_keyboard,
    tg_delete_confirm_keyboard,
    tg_notification_settings_keyboard,
    tg_profile_change_period_keyboard,
    tg_profile_change_result_keyboard,
    tg_profile_change_type_keyboard,
    tg_report_period_keyboard,
    tg_report_result_keyboard,
    tracked_list_chunk_keyboard,
    tg_tracked_list_chunk_keyboard,
    tg_user_card_keyboard,
    user_card_keyboard,
    user_report_menu_keyboard,
    user_picker_keyboard,
)
from ui_states import AddUserStates, SearchStates

logger = logging.getLogger(__name__)

router = Router()

MSK = timezone(timedelta(hours=3))
UTC = timezone.utc
CHECK_SUBSCRIPTION_CALLBACK = "check_required_subscription"
ALLOWED_MEMBER_STATUSES = {"member", "administrator", "creator"}
SOURCE_LIST = "lst"
SOURCE_SEARCH = "srh"
SOURCE_ONLINE_REPORT = "orp"
SOURCE_PROFILE_CHANGES = "pc"

NOTIFICATION_MODE_LABELS = {
    "online": "только вход в онлайн",
    "offline": "только выход из онлайна",
    "all": "вход и выход",
    "off": "уведомления о статусе отключены",
}
CHANGE_NOTIFICATION_LABELS = dict(CHANGE_NOTIFICATION_OPTIONS)
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


def _build_subscription_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подписаться на канал", url=REQUIRED_CHANNEL_LINK)],
            [InlineKeyboardButton(text="Проверить подписку", callback_data=CHECK_SUBSCRIPTION_CALLBACK)],
        ]
    )


def _subscription_required_text() -> str:
    if REQUIRED_CHANNEL_ID is None:
        return (
            "Проверка подписки включена, но канал пока не настроен в конфиге.\n"
            "Добавьте в <code>.env</code> переменную <code>REQUIRED_CHANNEL_ID</code> "
            "в формате <code>-100...</code>, затем перезапустите бота."
        )

    return (
        "Чтобы пользоваться ботом, сначала подпишитесь на указанный канал.\n"
        "После подписки нажмите кнопку «Проверить подписку»."
    )


async def _has_required_subscription(bot, user_id: int) -> bool:
    if REQUIRED_CHANNEL_ID is None:
        return False

    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL_ID, user_id)
    except TelegramBadRequest as exc:
        logger.warning("Не удалось проверить подписку пользователя %s: %s", user_id, exc)
        return False

    return member.status in ALLOWED_MEMBER_STATUSES


async def _remember_telegram_user(user) -> None:
    if user is None:
        return

    username = getattr(user, "username", None)
    normalized_username = (username or "").strip() or None
    profile_link = f"https://t.me/{normalized_username}" if normalized_username else f"tg://user?id={int(user.id)}"

    await db.upsert_tg_known_user(
        telegram_user_id=int(user.id),
        username=normalized_username,
        first_name=getattr(user, "first_name", None),
        last_name=getattr(user, "last_name", None),
        profile_link=profile_link,
        is_bot=bool(getattr(user, "is_bot", False)),
    )
    await db.sync_tg_tracked_user_profile(
        int(user.id),
        username=normalized_username,
        first_name=getattr(user, "first_name", None),
        last_name=getattr(user, "last_name", None),
    )


async def _send_subscription_required(target: Message | CallbackQuery) -> None:
    text = _subscription_required_text()
    reply_markup = _build_subscription_keyboard()

    if isinstance(target, Message):
        await target.answer(text, reply_markup=reply_markup)
        return

    if target.message:
        await target.message.answer(text, reply_markup=reply_markup)


class SubscriptionRequiredMessageMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        user = event.from_user
        await _remember_telegram_user(user)
        if user and await _has_required_subscription(event.bot, user.id):
            return await handler(event, data)

        await _send_subscription_required(event)
        return None


class SubscriptionRequiredCallbackMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[CallbackQuery, dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        if event.data == CHECK_SUBSCRIPTION_CALLBACK:
            return await handler(event, data)

        user = event.from_user
        await _remember_telegram_user(user)
        if user and await _has_required_subscription(event.bot, user.id):
            return await handler(event, data)

        await event.answer("Сначала подтвердите подписку на канал.", show_alert=True)
        await _send_subscription_required(event)
        return None


router.message.middleware(SubscriptionRequiredMessageMiddleware())
router.callback_query.middleware(SubscriptionRequiredCallbackMiddleware())


def _build_name(first_name: str, last_name: str, vk_id: int) -> str:
    return f"{first_name} {last_name}".strip() or f"ID {vk_id}"


def _escape_html(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _normalize_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _build_status_line(online: int) -> str:
    return "🟢 онлайн" if online else "🔴 офлайн"


def _strip_report_source(source: str) -> str:
    if source.startswith("r"):
        return source[1:]
    return source


def _report_source(source: str) -> str:
    if source.startswith("r"):
        return source
    return f"r{source}"


def _format_duration(total_seconds: int) -> str:
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


def _format_period_label(days: int) -> str:
    if days == 1:
        return "1 день"
    if days == 7:
        return "7 дней"
    if days == 30:
        return "30 дней"
    return "все время"


def _period_to_since_ts(days: int) -> int | None:
    if days <= 0:
        return None
    return int((datetime.now(tz=MSK) - timedelta(days=days)).timestamp())


def _get_profile_change_meta(change_key: str) -> dict[str, Any]:
    return PROFILE_CHANGE_FILTERS.get(change_key, PROFILE_CHANGE_FILTERS["all"])


def _get_profile_change_label(field_name: str) -> str:
    return PROFILE_CHANGE_LABELS.get(field_name, vk_api.PROFILE_FIELD_LABELS.get(field_name, field_name))


def _get_tg_profile_change_meta(change_key: str) -> dict[str, Any]:
    return TG_PROFILE_CHANGE_FILTERS.get(change_key, TG_PROFILE_CHANGE_FILTERS["all"])


def _format_tg_change_value(change_type: str, value: str | None, metadata: dict | None = None) -> str:
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
            suffix = "подарков"
            return f"{normalized} {suffix}"
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


def _build_tg_profile_change_block(change: dict) -> str:
    change_type = str(change.get("change_type") or "")
    changed_at = vk_api.format_timestamp(int(change["changed_at"]))
    meta = change.get("metadata") or {}
    label = TG_PROFILE_CHANGE_FILTERS.get(change_type, {"label": change_type}).get("label", change_type)

    if change_type == "avatar":
        old_value = _format_tg_change_value(change_type, change.get("old_value"), meta)
        new_value = _format_tg_change_value(change_type, change.get("new_value"), meta)
        return (
            f"• {changed_at} — <b>{_escape_html(label)}</b>\n"
            f"Было: <code>{_escape_html(old_value)}</code>\n"
            f"Стало: <code>{_escape_html(new_value)}</code>"
        )

    if change_type == "gifts" and bool(meta.get("count_only", False)):
        old_value = _format_tg_change_value(change_type, change.get("old_value"), meta)
        new_value = _format_tg_change_value(change_type, change.get("new_value"), meta)
        return (
            f"• {changed_at} — <b>{_escape_html(label)}</b>\n"
            f"Счетчик: <code>{_escape_html(old_value)}</code> → <code>{_escape_html(new_value)}</code>\n"
            "Доступен только счетчик подарков, без списка самих подарков."
        )

    old_value = _format_tg_change_value(change_type, change.get("old_value"), meta)
    new_value = _format_tg_change_value(change_type, change.get("new_value"), meta)

    if change_type == "bio":
        return (
            f"• {changed_at} — <b>{_escape_html(label)}</b>\n"
            f"Было: <code>{_escape_html(_truncate_text(old_value, 150))}</code>\n"
            f"Стало: <code>{_escape_html(_truncate_text(new_value, 150))}</code>"
        )

    return (
        f"• {changed_at} — <b>{_escape_html(label)}</b>\n"
        f"Было: <code>{_escape_html(old_value)}</code>\n"
        f"Стало: <code>{_escape_html(new_value)}</code>"
    )


def _parse_wall_post_value(value: str | None) -> tuple[str | None, str | None]:
    normalized = (value or "").strip()
    if not normalized:
        return None, None

    lines = normalized.splitlines()
    first_line = lines[0].strip() if lines else ""
    if first_line.startswith("http://") or first_line.startswith("https://"):
        text = "\n".join(lines[1:]).strip() or None
        return first_line, text
    return None, normalized


def _build_profile_change_block(change: dict) -> str:
    field_name = str(change.get("field_name") or "")
    changed_at = vk_api.format_timestamp(int(change["changed_at"]))
    label = _get_profile_change_label(field_name)

    if field_name == "avatar_url":
        return f"• {changed_at} — <b>{_escape_html(label)}</b>: аватарка изменена"

    if field_name == "wall_post":
        post_link, post_text = _parse_wall_post_value(change.get("new_value"))
        lines = [f"• {changed_at} — <b>{_escape_html(label)}</b>: новый пост"]
        if post_link:
            lines.append(f"🔗 <a href='{_escape_html(post_link)}'>{_escape_html(post_link)}</a>")
        if post_text:
            lines.append(f"Текст: <code>{_escape_html(_truncate_text(post_text, 220))}</code>")
        return "\n".join(lines)

    old_value = _truncate_text(vk_api.format_profile_field_value(field_name, change.get("old_value")), 220)
    new_value = _truncate_text(vk_api.format_profile_field_value(field_name, change.get("new_value")), 220)
    return (
        f"• {changed_at} — <b>{_escape_html(label)}</b>\n"
        f"Было: <code>{_escape_html(old_value)}</code>\n"
        f"Стало: <code>{_escape_html(new_value)}</code>"
    )


def _format_added_at(sqlite_dt: str | None) -> str:
    if not sqlite_dt:
        return "неизвестно"

    try:
        dt = datetime.strptime(sqlite_dt, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return sqlite_dt

    return dt.astimezone(MSK).strftime("%d.%m.%Y %H:%M:%S")


def _truncate_text(value: str, limit: int = 280) -> str:
    normalized = value.strip()
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit - 1]}…"


def _is_privacy_blocked_reason(reason: str | None) -> bool:
    normalized = (reason or "").strip().lower()
    if not normalized:
        return False
    return "скрыт" in normalized or "не отдал список" in normalized or "недоступ" in normalized


async def _build_relation_privacy_lines(vk_id: int) -> list[str]:
    lines: list[str] = []
    for list_type, icon, label in RELATION_PRIVACY_CARD_META:
        meta = await db.get_profile_list_meta(vk_id, list_type)
        if meta is None or int(meta.get("is_complete") or 0) == 1:
            continue

        reason = str(meta.get("last_reason") or "").strip()
        if _is_privacy_blocked_reason(reason):
            lines.append(f"{icon} {label}: скрыты настройками приватности, точное отслеживание невозможно")
        elif reason:
            lines.append(f"{icon} {label}: точное отслеживание недоступно ({_escape_html(_truncate_text(reason, 120))})")
        else:
            lines.append(f"{icon} {label}: точное отслеживание недоступно")
    return lines


def _source_nav_target(source: str) -> str:
    base_source = _strip_report_source(source)
    if base_source in {"srh", "csrh"}:
        return "search_results"
    if base_source in {"orp", "corp"}:
        return "report_users"
    return "list"


def _card_source(source: str) -> str:
    base_source = _strip_report_source(source)
    if base_source.startswith("c"):
        return base_source
    return f"c{base_source}"


def _format_session_block(index: int, started_at: int, ended_at: int | None) -> str:
    start_dt = datetime.fromtimestamp(started_at, tz=MSK)
    start_date = start_dt.strftime("%d.%m.%Y")
    start_time = start_dt.strftime("%H:%M:%S")

    if ended_at is None:
        end_time = "до сих пор онлайн"
        duration_seconds = int(datetime.now(tz=MSK).timestamp()) - started_at
        duration_text = _format_duration(duration_seconds)
    else:
        end_dt = datetime.fromtimestamp(ended_at, tz=MSK)
        end_time = end_dt.strftime("%H:%M:%S")
        duration_seconds = ended_at - started_at
        duration_text = _format_duration(duration_seconds)

    return (
        f"{index}.\n"
        f"Дата: {start_date}\n"
        f"Зашел: {start_time}\n"
        f"Вышел: {end_time}\n"
        f"Был онлайн: {duration_text}"
    )


def _session_duration_for_period(session: dict, since_ts: int | None, now_ts: int) -> int:
    started_at = int(session["started_at"])
    ended_at = int(session["ended_at"]) if session["ended_at"] is not None else now_ts

    effective_start = max(started_at, since_ts) if since_ts is not None else started_at
    effective_end = min(ended_at, now_ts)
    if effective_end <= effective_start:
        return 0
    return effective_end - effective_start


def _build_tg_status_label(detail: dict) -> str:
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


def _build_tg_activity_line(detail: dict) -> str:
    if detail.get("last_seen_at") is not None:
        return f"Last seen: {vk_api.format_timestamp(int(detail['last_seen_at']))}"

    if detail.get("activity_at") is not None:
        return f"Последняя активность: {vk_api.format_timestamp(int(detail['activity_at']))}"

    return "Последняя активность: пока не зафиксирована"


def _format_tg_session_block(index: int, session: dict, since_ts: int | None, now_ts: int) -> str:
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

    duration_text = _format_duration(max(effective_ended_at - effective_started_at, 0))
    return (
        f"{index}.\n"
        f"Дата: {start_date}\n"
        f"Зашел: {start_time}\n"
        f"Вышел: {end_time}\n"
        f"Был онлайн: {duration_text}"
    )


def _snapshot_from_detail(detail: dict, live_user: dict | None = None) -> dict:
    vk_id = int(detail["vk_id"])
    live_profile = vk_api.extract_profile_snapshot(live_user) if live_user else {}

    if live_user:
        first_name = live_profile.get("first_name", "") or detail.get("first_name", "") or ""
        last_name = live_profile.get("last_name", "") or detail.get("last_name", "") or ""
        online = int(live_user.get("online", 0) or 0)
        last_seen = vk_api.extract_last_seen_ts(live_user) or int(detail.get("last_seen", 0) or 0)
    else:
        first_name = detail.get("first_name", "") or ""
        last_name = detail.get("last_name", "") or ""
        online = int(detail.get("online", 0) or 0)
        last_seen = int(detail.get("last_seen", 0) or 0)

    domain = live_profile.get("domain") if "domain" in live_profile else detail.get("domain")
    profile_link = live_profile.get("profile_link") or vk_api.build_profile_link(vk_id, domain)

    snapshot = {
        "vk_id": vk_id,
        "first_name": first_name,
        "last_name": last_name,
        "name": _build_name(first_name, last_name, vk_id),
        "online": online,
        "last_seen": last_seen,
        "added_at": detail.get("added_at"),
        "profile_link": profile_link,
    }

    for field_name in db.PROFILE_CACHE_FIELDS:
        if field_name in live_profile:
            snapshot[field_name] = live_profile.get(field_name)
        else:
            snapshot[field_name] = detail.get(field_name)

    return snapshot


async def _load_current_users_map(vk_ids: list[int]) -> dict[int, dict]:
    users_data = await vk_api.get_users_status(vk_ids)
    if not users_data:
        return {}
    return {user["id"]: user for user in users_data if "id" in user}


async def _load_tracked_snapshots(chat_id: int) -> list[dict]:
    details = await db.get_tracked_users_details(chat_id, active_only=True)
    if not details:
        return []

    live_map = await _load_current_users_map([int(item["vk_id"]) for item in details])
    return [_snapshot_from_detail(detail, live_map.get(int(detail["vk_id"]))) for detail in details]


async def _get_single_snapshot(chat_id: int, vk_id: int) -> dict | None:
    detail = await db.get_tracked_user_detail(chat_id, vk_id)
    if detail is None:
        return None

    live_user = await vk_api.get_single_user_status(vk_id)
    return _snapshot_from_detail(detail, live_user)


async def _send_long_html(message: Message, blocks: list[str]) -> None:
    if not blocks:
        return

    current = ""
    for block in blocks:
        next_part = block if not current else f"{current}\n\n{block}"
        if len(next_part) > 4000:
            if current:
                await message.answer(current, disable_web_page_preview=True)
            current = block
        else:
            current = next_part

    if current:
        await message.answer(current, disable_web_page_preview=True)


def _split_chunks(items: list[dict], chunk_size: int) -> list[list[dict]]:
    return [items[idx:idx + chunk_size] for idx in range(0, len(items), chunk_size)]


def _build_list_chunk_text(title: str, chunk: list[dict], is_first_chunk: bool) -> str:
    lines = [title if is_first_chunk else f"{title}\nПродолжение:"]
    for snapshot in chunk:
        lines.append(
            f"• <b>{snapshot['name']}</b>\n"
            f"ID: <code>{snapshot['vk_id']}</code>\n"
            f"Статус: {_build_status_line(int(snapshot['online']))}\n"
            f"🕐 Последний визит: {vk_api.format_last_seen(snapshot['last_seen'] or None)}\n"
            f"🔗 <a href='{snapshot['profile_link']}'>{snapshot['profile_link']}</a>"
        )
    return "\n\n".join(lines)


async def _send_tracked_list_chunks(message: Message, snapshots: list[dict], source: str, title: str) -> None:
    chunks = _split_chunks(snapshots, 5)
    for index, chunk in enumerate(chunks):
        await message.answer(
            _build_list_chunk_text(title, chunk, is_first_chunk=index == 0),
            reply_markup=tracked_list_chunk_keyboard(
                [(int(item["vk_id"]), str(item["name"])) for item in chunk],
                source,
            ),
            disable_web_page_preview=True,
        )


def _build_help_text(current_mode: str, change_settings: dict[str, bool]) -> str:
    enabled_change_labels = [
        label for key, label in CHANGE_NOTIFICATION_OPTIONS if bool(change_settings.get(key, True))
    ]
    disabled_change_labels = [
        label for key, label in CHANGE_NOTIFICATION_OPTIONS if not bool(change_settings.get(key, True))
    ]
    enabled_changes_text = ", ".join(enabled_change_labels) if enabled_change_labels else "все отключены"
    disabled_changes_text = ", ".join(disabled_change_labels) if disabled_change_labels else "ничего не отключено"

    return (
        "🧭 Бот работает с двумя платформами: ВКонтакте [VK] и Telegram [TG].\n"
        "Интерфейс у разделов одинаковый по структуре, но данные и карточки пользователей разделены по платформам.\n\n"
        "<b>Как пользоваться меню:</b>\n"
        f"• <b>{BTN_PLATFORM_VK}</b> — открыть раздел ВКонтакте со своими действиями и отчетами\n"
        f"• <b>{BTN_PLATFORM_TG}</b> — открыть раздел Telegram с зеркальным интерфейсом\n"
        f"• <b>{BTN_GENERAL_REPORT}</b> — выбрать общий отчет верхнего уровня по платформе\n"
        f"• <b>{BTN_NOTIFY}</b> — открыть верхний уровень настроек уведомлений по платформам\n"
        f"• <b>{BTN_HELP}</b> — открыть эту справку\n\n"
        "<b>Как открыть отчеты:</b>\n"
        f"• для персонального отчета по VK зайдите в <b>{BTN_PLATFORM_VK}</b> → <b>{BTN_TRACKED_LIST}</b>\n"
        f"• для персонального отчета по TG зайдите в <b>{BTN_PLATFORM_TG}</b> → <b>{BTN_TRACKED_LIST_TG}</b>\n"
        "• откройте карточку нужного пользователя и выберите нужный тип отчета\n"
        "• в TG-карточке доступны отчет по онлайну и отчет по изменениям профиля\n"
        f"• для общего отчета используйте <b>{BTN_GENERAL_REPORT}</b> и затем нужную платформу\n"
        "• персональные отчеты VK и TG не смешиваются между собой\n\n"
        "<b>Как работают уведомления:</b>\n"
        f"• в разделе <b>{BTN_NOTIFY_VK}</b> можно настроить уведомления о входе в онлайн, выходе из онлайна и изменениях профиля VK\n"
        f"• в разделе <b>{BTN_NOTIFY_TG}</b> можно настроить уведомления о входе в онлайн, выходе из онлайна, activity / last seen и изменениях профиля Telegram\n"
        "• по подаркам Telegram бот использует только тот объем данных, который реально доступен клиентскому слою\n"
        "• если уведомления не приходят, проверьте, что отслеживание включено и что нужный режим уведомлений не отключен\n\n"
        "<b>Почему время онлайна может иметь погрешность:</b>\n"
        "• бот опрашивает платформу с интервалом, поэтому короткие входы и выходы могут округляться или фиксироваться с небольшой задержкой\n"
        "• на точность также влияют ограничения самой платформы и сетевые задержки\n\n"
        "<b>Если уведомления не приходят:</b>\n"
        "• проверьте настройки уведомлений в боте\n"
        "• убедитесь, что пользователь действительно добавлен в отслеживание в нужной платформе\n"
        "• если проблема в VK сохраняется, попробуйте заново открыть карточку пользователя или повторно добавить его\n"
        "• если проблема в TG, проверьте, что userbot-сессия активна и Telegram-резолвер доступен\n\n"
        "<b>⌨️ Резервные команды:</b>\n"
        "/start — 🏠 открыть главное меню\n"
        "/help — ❓ подробная справка\n"
        "/add <code>ССЫЛКА</code> — ➕ добавить пользователя вручную\n"
        "/remove <code>ССЫЛКА</code> — 🗑️ удалить пользователя вручную\n"
        "/list — 📋 показать список отслеживаемых\n"
        "/status <code>ССЫЛКА</code> — 👤 показать карточку конкретного пользователя\n"
        "/report — 📊 подробный отчет по всем отслеживаемым\n"
        "/find <code>ИМЯ</code> — 🔎 поиск среди отслеживаемых\n"
        "/notify <code>MODE</code> — 🔔 быстро сменить только режим онлайн-уведомлений\n"
        "/stop — ⏸️ остановить отслеживание\n"
        "/resume — ▶️ возобновить отслеживание\n\n"
        f"🔔 Текущий режим VK онлайн-уведомлений: <b>{NOTIFICATION_MODE_LABELS.get(current_mode, current_mode)}</b>\n"
        f"✅ Включены VK-уведомления по изменениям: <b>{_escape_html(enabled_changes_text)}</b>\n"
        f"🚫 Отключены VK-уведомления по изменениям: <b>{_escape_html(disabled_changes_text)}</b>"
    )


async def _show_main_menu(message: Message, text: str | None = None) -> None:
    await message.answer(
        text
        or (
            "🏠 Главное меню.\n"
            "Сначала выберите платформу или общий раздел ниже."
        ),
        reply_markup=main_menu_keyboard(),
    )


async def _show_help(message: Message) -> None:
    current_mode = await db.get_notification_mode(message.chat.id)
    change_settings = await db.get_change_notification_settings(message.chat.id)
    await message.answer(_build_help_text(current_mode, change_settings), reply_markup=main_menu_keyboard())


async def _show_vk_menu(message: Message) -> None:
    await message.answer(
        "🟦 <b>Раздел ВКонтакте [VK]</b>\n"
        "Все действия в этом меню относятся только к VK-данным и VK-отчетам.",
        reply_markup=platform_section_keyboard("vk"),
    )


async def _show_tg_menu(message: Message) -> None:
    await message.answer(
        "🟨 <b>Раздел Telegram [TG]</b>\n"
        "Структура этого меню зеркальна VK-разделу. Здесь уже подключены базовые статусы, online-сессии, отчеты и уведомления без смешивания с VK.",
        reply_markup=platform_section_keyboard("tg"),
    )


async def _show_reports_hub(message: Message) -> None:
    await message.answer(
        "📊 <b>Общий отчет</b>\n"
        "Выберите платформу. Персональные данные VK и TG здесь не смешиваются.",
        reply_markup=reports_hub_keyboard(),
    )


async def _show_notifications_hub(message: Message) -> None:
    await message.answer(
        "🔔 <b>Настройки уведомлений</b>\n"
        "Выберите платформу, для которой хотите открыть настройки.",
        reply_markup=notifications_hub_keyboard(),
    )


async def _show_add_prompt(message: Message, state: FSMContext, back_target: str = "vk_menu") -> None:
    await state.set_state(AddUserStates.waiting_for_vk_link)
    await message.answer(
        "➕ Отправьте данные пользователя ВКонтакте [VK], которого нужно добавить в отслеживание.\n"
        "Поддерживаются форматы:\n"
        "• <code>123456789</code>\n"
        "• <code>durov</code>\n"
        "• <code>@durov</code>\n"
        "• <code>vk.com/durov</code>\n"
        "• <code>https://vk.com/durov</code>\n"
        "• <code>vk.ru/durov</code>\n"
        "• <code>https://vk.ru/durov</code>",
        reply_markup=back_main_inline_keyboard(back_target),
    )


async def _show_tg_add_prompt(message: Message, state: FSMContext) -> None:
    await state.set_state(AddUserStates.waiting_for_tg_link)
    await message.answer(
        "➕ Отправьте данные пользователя Telegram [TG], которого хотите добавить.\n"
        "Для надежного добавления лучше использовать кнопку выбора пользователя ниже: она передает стабильный Telegram user id.\n\n"
        "Можно отправить:\n"
        "• <code>username</code>\n"
        "• <code>@username</code>\n"
        "• <code>t.me/username</code>\n"
        "• <code>https://t.me/username</code>\n"
        "• числовой <code>user id</code>, если он уже известен",
        reply_markup=tg_add_user_reply_keyboard(),
    )


def _tg_display_name(item: dict) -> str:
    first_name = str(item.get("first_name") or "").strip()
    last_name = str(item.get("last_name") or "").strip()
    username = str(item.get("username") or "").strip()
    full_name = f"{first_name} {last_name}".strip()
    if full_name:
        return full_name
    if username:
        return f"@{username}"
    return f"ID {item['telegram_user_id']}"


async def _save_tg_user_from_shared(message: Message, shared_user: SharedUser) -> tuple[bool, dict]:
    telegram_user_id = int(shared_user.user_id)
    username = (shared_user.username or "").strip() or None
    profile_link = f"https://t.me/{username}" if username else f"tg://user?id={telegram_user_id}"
    payload = {
        "telegram_user_id": telegram_user_id,
        "username": username,
        "first_name": (shared_user.first_name or "").strip() or None,
        "last_name": (shared_user.last_name or "").strip() or None,
        "profile_link": profile_link,
    }
    added = await db.add_tg_tracked_user(
        chat_id=message.chat.id,
        telegram_user_id=telegram_user_id,
        username=payload["username"],
        first_name=payload["first_name"],
        last_name=payload["last_name"],
        source_value=payload["username"],
    )
    await db.upsert_tg_known_user(
        telegram_user_id=telegram_user_id,
        username=payload["username"],
        first_name=payload["first_name"],
        last_name=payload["last_name"],
        profile_link=payload["profile_link"],
        is_bot=False,
    )
    await db.sync_tg_tracked_user_profile(
        telegram_user_id,
        username=payload["username"],
        first_name=payload["first_name"],
        last_name=payload["last_name"],
    )
    return added, payload


async def _resolve_tg_user_from_input(message: Message, raw_value: str) -> tuple[dict | None, str | None]:
    try:
        normalized = normalize_telegram_lookup(raw_value)
    except TelegramResolverInvalidInputError:
        return None, "Не удалось распознать пользователя. Отправьте username, @username, ссылку t.me/... или числовой id."

    if normalized.kind == "user_id":
        known_user = await db.get_tg_known_user_by_id(int(normalized.value))
        if known_user is not None:
            return {
                "telegram_user_id": int(known_user["telegram_user_id"]),
                "username": known_user.get("username"),
                "first_name": known_user.get("first_name"),
                "last_name": known_user.get("last_name"),
                "access_hash": known_user.get("access_hash"),
                "profile_link": known_user.get("profile_link"),
                "avatar_photo_id": known_user.get("avatar_photo_id"),
                "avatar_dc_id": known_user.get("avatar_dc_id"),
                "avatar_has_video": bool(known_user.get("avatar_has_video")),
                "gifts_count": known_user.get("gifts_count"),
                "gifts_supported": known_user.get("gifts_supported"),
                "status_text": None,
                "last_seen_at": None,
                "is_online": None,
                "status_kind": None,
                "activity_at": None,
                "lookup_value": str(normalized.value),
            }, None

    try:
        resolved = await resolve_telegram_user(raw_value)
    except TelegramResolverInvalidInputError:
        return None, "Не удалось распознать пользователя. Отправьте username, @username, ссылку t.me/... или числовой id."
    except TelegramResolverNotFoundError:
        if normalized.kind == "user_id":
            return None, "Не удалось найти Telegram-пользователя по указанному id."
        return None, "Не удалось найти Telegram-пользователя по указанному username."
    except TelegramResolverPeerTypeError:
        return None, (
            "Указанный username относится не к обычному пользователю Telegram. "
            "Сейчас бот умеет отслеживать только пользователей."
        )
    except TelegramResolverUnavailableError:
        return None, "Telegram-резолвер сейчас недоступен. Попробуйте позже."

    return {
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
    }, None


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
    display_name = _tg_display_name(tg_user)
    username_line = f"\nUsername: <code>@{_escape_html(username)}</code>" if username else ""
    result_prefix = "Добавлен" if added else "Пользователь уже отслеживается, данные обновлены"
    await message.answer(
        f"🟨 {result_prefix}: <b>{_escape_html(display_name)}</b>\n"
        f"ID: <code>{tg_user['telegram_user_id']}</code>{username_line}",
        reply_markup=main_menu_keyboard(),
    )


async def _show_search_prompt(message: Message, state: FSMContext, back_target: str = "vk_menu") -> None:
    await state.set_state(SearchStates.waiting_for_query)
    await state.update_data(search_query="")
    await message.answer(
        "🔎 Введите имя, фамилию или полное имя пользователя, которого нужно найти среди отслеживаемых.",
        reply_markup=back_main_inline_keyboard(back_target),
    )


async def _show_profile_changes(message: Message) -> None:
    changes = await db.get_recent_profile_changes(message.chat.id, limit=30)
    if not changes:
        await message.answer(
            "📝 История изменений профилей пока пуста.\n"
            "Когда бот заметит смену имени, фамилии, короткой ссылки или других полей профиля, записи появятся здесь.",
            reply_markup=back_main_inline_keyboard("main"),
        )
        return

    blocks = ["<b>📝 Последние изменения профилей</b>"]
    for change in changes:
        vk_id = int(change["vk_id"])
        name = _build_name(change.get("first_name", "") or "", change.get("last_name", "") or "", vk_id)
        profile_link = vk_api.build_profile_link(vk_id, change.get("domain"))
        field_name = str(change["field_name"])
        label = vk_api.PROFILE_FIELD_LABELS.get(field_name, field_name)
        base_lines = [
            f"👤 <b>{_escape_html(name)}</b>",
            f"🕐 {vk_api.format_timestamp(int(change['changed_at']))}",
            f"🔗 <a href='{_escape_html(profile_link)}'>{_escape_html(profile_link)}</a>",
            f"Поле: <b>{_escape_html(label)}</b>",
        ]

        if field_name == "avatar_url":
            base_lines.append("Изменение: <code>аватарка обновлена</code>")
        else:
            old_value = _truncate_text(vk_api.format_profile_field_value(field_name, change.get("old_value")))
            new_value = _truncate_text(vk_api.format_profile_field_value(field_name, change.get("new_value")))
            base_lines.append(f"Было: <code>{_escape_html(old_value)}</code>")
            base_lines.append(f"Стало: <code>{_escape_html(new_value)}</code>")

        blocks.append("\n".join(base_lines))

    await _send_long_html(message, blocks)
    await message.answer("📝 Что дальше?", reply_markup=back_main_inline_keyboard("main"))


async def _show_profile_change_user_picker(message: Message, source: str = SOURCE_PROFILE_CHANGES) -> None:
    snapshots = await _load_tracked_snapshots(message.chat.id)
    if not snapshots:
        await message.answer(
            "📝 Список отслеживаемых пользователей пуст.\nСначала добавьте пользователя, а потом можно будет смотреть историю изменений профиля.",
            reply_markup=main_menu_keyboard(),
        )
        return

    items = [(int(snapshot["vk_id"]), str(snapshot["name"])) for snapshot in snapshots]
    for start in range(0, len(items), 20):
        chunk = items[start:start + 20]
        await message.answer(
            "📝 Выберите пользователя, по которому нужен отчет об изменениях профиля.",
            reply_markup=profile_change_user_keyboard(chunk, source=source),
        )


async def _show_profile_change_type_picker(message: Message, vk_id: int, source: str) -> None:
    snapshot = await _get_single_snapshot(message.chat.id, vk_id)
    if snapshot is None:
        await message.answer(
            "⚠️ Пользователь не найден в отслеживаемых.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer(
        f"🧩 Выберите тип изменений для <b>{_escape_html(snapshot['name'])}</b>.",
        reply_markup=profile_change_type_keyboard(vk_id, PROFILE_CHANGE_TYPE_ITEMS, source),
        disable_web_page_preview=True,
    )


async def _show_profile_change_period_picker(message: Message, vk_id: int, change_key: str, source: str) -> None:
    meta = _get_profile_change_meta(change_key)
    await message.answer(
        f"🗓️ Выберите период для отчета: <b>{_escape_html(str(meta['label']))}</b>.",
        reply_markup=profile_change_period_keyboard(vk_id, change_key, source),
    )


async def _show_profile_change_report(message: Message, vk_id: int, change_key: str, days: int, source: str) -> None:
    snapshot = await _get_single_snapshot(message.chat.id, vk_id)
    if snapshot is None:
        await message.answer(
            "⚠️ Пользователь не найден в отслеживаемых.",
            reply_markup=main_menu_keyboard(),
        )
        return

    meta = _get_profile_change_meta(change_key)
    change_label = str(meta["label"])
    if not bool(meta.get("supported")):
        await message.answer(
            f"⚠️ Тип изменений <b>{_escape_html(change_label)}</b> пока не собирается текущей системой.\n"
            "Сейчас доступны отчеты только по тем изменениям, которые реально сохраняются в историю профиля.",
            reply_markup=profile_change_result_keyboard(vk_id, change_key, source),
        )
        return

    field_names = meta.get("fields")
    changes = await db.get_profile_changes_for_report(
        chat_id=message.chat.id,
        vk_id=vk_id,
        field_names=list(field_names) if isinstance(field_names, list) else None,
        since_ts=_period_to_since_ts(days),
        limit=300,
    )

    header = "\n".join(
        [
            "<b>📝 Отчет по изменениям профиля</b>",
            f"👤 <b>{_escape_html(snapshot['name'])}</b>",
            f"ID: <code>{snapshot['vk_id']}</code>",
            f"🔗 <a href='{_escape_html(snapshot['profile_link'])}'>{_escape_html(snapshot['profile_link'])}</a>",
            f"Тип изменений: <b>{_escape_html(change_label)}</b>",
            f"Период: <b>{_escape_html(_format_period_label(days))}</b>",
        ]
    )

    if not changes:
        empty_text = f"{header}\n\n🔍 Изменения за выбранный период не найдены."
        if change_key == "pst":
            empty_text += "\n📝 История по постам начинает накапливаться с момента обновления бота."
        await message.answer(
            empty_text,
            reply_markup=profile_change_result_keyboard(vk_id, change_key, source),
            disable_web_page_preview=True,
        )
        return

    blocks = [header]
    for change in changes:
        blocks.append(_build_profile_change_block(change))

    await _send_long_html(message, blocks)
    await message.answer(
        "📝 Что дальше?",
        reply_markup=profile_change_result_keyboard(vk_id, change_key, source),
    )


async def _show_notification_settings(
    message: Message,
    text: str | None = None,
    back_target: str = "notification_hub",
) -> None:
    current_mode = await db.get_notification_mode(message.chat.id)
    change_settings = await db.get_change_notification_settings(message.chat.id)
    await message.answer(
        text
        or (
            "🔔 Здесь можно отдельно настроить уведомления ВКонтакте [VK]:\n"
            "• 🟢🔴 уведомления о входе и выходе из онлайна\n"
            "• 📝 уведомления о не-онлайн изменениях профиля\n\n"
            "👇 Нажмите на нужную кнопку, чтобы изменить настройку."
        ),
        reply_markup=notification_settings_keyboard(current_mode, change_settings, back_target=back_target),
    )


async def _show_tg_placeholder(message: Message, title: str, back_target: str = "tg_menu") -> None:
    await message.answer(
        f"{title}\n"
        "Telegram-ветка уже добавлена в интерфейс и навигацию, но глубокая логика мониторинга пока не реализована.\n"
        "Здесь не показываются вымышленные данные: этот экран служит честной заглушкой под будущую TG-логику.",
        reply_markup=back_main_inline_keyboard(back_target),
    )


async def _show_tg_tracked_users_screen(message: Message) -> None:
    tg_users = await db.get_tg_tracked_users_details(message.chat.id)
    if not tg_users:
        await message.answer(
            "📋 Список отслеживаемых пользователей [TG] пуст.\n"
            "Добавьте пользователя через кнопку «Добавить пользователя [TG]».",
            reply_markup=main_menu_keyboard(),
        )
        return

    formatted_items: list[dict] = []
    for item in tg_users:
        display_name = _tg_display_name(item)
        username = str(item.get("username") or "").strip()
        lines = [
            f"👤 <b>{_escape_html(display_name)}</b>",
            f"ID: <code>{item['telegram_user_id']}</code>",
        ]
        if username:
            lines.append(f"Username: <code>@{_escape_html(username)}</code>")
        lines.append(f"Добавлен: {_format_added_at(item.get('added_at'))}")
        formatted_items.append({**item, "display_name": display_name, "text": "\n".join(lines)})

    for start in range(0, len(formatted_items), 5):
        chunk = formatted_items[start:start + 5]
        text = "<b>📋 Список отслеживаемых пользователей [TG]</b>\n\n" + "\n\n".join(
            item["text"] for item in chunk
        )
        await message.answer(
            text,
            reply_markup=tg_tracked_list_chunk_keyboard(chunk),
        )


async def _show_tg_user_card(message: Message, telegram_user_id: int, source: str = "tg_list") -> None:
    detail = await db.get_tg_tracked_user_detail(message.chat.id, telegram_user_id)
    if detail is None:
        await message.answer(
            "⚠️ Telegram-пользователь не найден в списке отслеживаемых.",
            reply_markup=main_menu_keyboard(),
        )
        return

    display_name = _tg_display_name(detail)
    username = str(detail.get("username") or "").strip()
    status_label = _build_tg_status_label(detail)
    lines = [
        f"👤 <b>{_escape_html(display_name)}</b>",
        f"ID: <code>{detail['telegram_user_id']}</code>",
        f"Имя: {_escape_html(str(detail.get('first_name') or 'не указано'))}",
        f"Фамилия: {_escape_html(str(detail.get('last_name') or 'не указано'))}",
        f"Username: <code>{_escape_html('@' + username if username else 'не указан')}</code>",
        f"Добавлен: {_format_added_at(detail.get('added_at'))}",
        f"Текущий статус: {_escape_html(status_label)}",
        _build_tg_activity_line(detail),
    ]
    if detail.get("profile_link"):
        lines.append(f"Ссылка: <a href='{_escape_html(str(detail['profile_link']))}'>{_escape_html(str(detail['profile_link']))}</a>")
    if detail.get("avatar_photo_id"):
        lines.append(f"Аватар: photo_id <code>{_escape_html(str(detail['avatar_photo_id']))}</code>")
    if detail.get("bio"):
        lines.append(f"Bio: <i>{_escape_html(str(detail['bio']))}</i>")
    if detail.get("gifts_supported") is True:
        gifts_count = int(detail.get("gifts_count") or 0)
        lines.append(f"Подарки: <b>{gifts_count}</b> (доступен только счетчик)")
    if detail.get("status_updated_at"):
        lines.append(f"Последнее обновление статуса: {_format_added_at(detail.get('status_updated_at'))}")

    await message.answer(
        "\n".join(lines),
        reply_markup=tg_user_card_keyboard(telegram_user_id, source),
    )


async def _show_tg_delete_confirmation(message: Message, telegram_user_id: int, source: str) -> None:
    detail = await db.get_tg_tracked_user_detail(message.chat.id, telegram_user_id)
    if detail is None:
        await message.answer(
            "Telegram-пользователь уже отсутствует в списке отслеживаемых.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer(
        f"🗑️ Удалить Telegram-пользователя <b>{_escape_html(_tg_display_name(detail))}</b> из отслеживания?",
        reply_markup=tg_delete_confirm_keyboard(telegram_user_id, source),
    )


async def _show_tg_notification_settings(
    message: Message,
    text: str | None = None,
    back_target: str = "notification_hub",
) -> None:
    current_mode = await db.get_tg_notification_mode(message.chat.id)
    activity_enabled = await db.get_tg_activity_notification_enabled(message.chat.id)
    change_settings = await db.get_tg_change_notification_settings(message.chat.id)
    await message.answer(
        text
        or (
            "🔔 Здесь можно отдельно настроить уведомления Telegram [TG]:\n"
            "• 🟢🔴 уведомления о входе и выходе из онлайна\n"
            "• 🟡 уведомления по activity / last seen\n\n"
            "• 👤🔗🖼️📝 уведомления по изменениям имени, фамилии, username, аватарки и bio\n"
            "• 🎁 по подаркам доступен только graceful fallback: если клиентский слой вернет счетчик подарков, бот зафиксирует изменение количества\n\n"
            "👇 Нажмите на нужную кнопку, чтобы изменить настройку."
        ),
        reply_markup=tg_notification_settings_keyboard(
            current_mode,
            activity_enabled,
            change_settings,
            back_target=back_target,
        ),
    )


async def _show_tg_report_period_picker(message: Message, telegram_user_id: int, source: str) -> None:
    detail = await db.get_tg_tracked_user_detail(message.chat.id, telegram_user_id)
    if detail is None:
        await message.answer(
            "⚠️ Telegram-пользователь не найден в списке отслеживаемых.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer(
        f"🗓️ Выберите период для отчета по онлайну [TG] для <b>{_escape_html(_tg_display_name(detail))}</b>.",
        reply_markup=tg_report_period_keyboard(
            scope="one",
            tg_id=telegram_user_id,
            source=source,
            back_target="tg_list",
            back_to_card=True,
        ),
    )


async def _show_tg_general_report_period_picker(message: Message) -> None:
    await message.answer(
        "📊 <b>Общий отчет [TG]</b>\nВыберите период. Данные VK и TG в этом отчете не смешиваются.",
        reply_markup=tg_report_period_keyboard(
            scope="all",
            tg_id=0,
            source="tg_general",
            back_target="general_reports_hub",
            back_to_card=False,
        ),
    )


async def _build_tg_period_user_report(chat_id: int, detail: dict, days: int) -> str:
    now_ts = int(datetime.now(tz=MSK).timestamp())
    since_ts = _period_to_since_ts(days)
    sessions = await db.get_tg_online_sessions_for_period(
        chat_id,
        int(detail["telegram_user_id"]),
        since_ts=since_ts,
    )

    total_duration = sum(_session_duration_for_period(session, since_ts, now_ts) for session in sessions)
    display_name = _tg_display_name(detail)
    username = str(detail.get("username") or "").strip()
    profile_link = str(detail.get("profile_link") or f"tg://user?id={int(detail['telegram_user_id'])}")
    lines = [
        "<b>📈 Отчет по онлайну [TG]</b>",
        f"👤 <b>{_escape_html(display_name)}</b>",
        f"ID: <code>{detail['telegram_user_id']}</code>",
        f"Username: <code>{_escape_html('@' + username if username else 'не указан')}</code>",
        f"Статус: {_escape_html(_build_tg_status_label(detail))}",
        _build_tg_activity_line(detail),
        f"🔗 <a href='{_escape_html(profile_link)}'>{_escape_html(profile_link)}</a>",
        f"📊 Период: <b>{_escape_html(_format_period_label(days))}</b>",
        f"Количество входов: <b>{len(sessions)}</b>",
        f"Суммарное время онлайна: <b>{_format_duration(total_duration)}</b>",
        "",
        "<b>Сессии за период:</b>",
    ]

    if sessions:
        for index, session in enumerate(sessions, start=1):
            lines.append(_format_tg_session_block(index, session, since_ts, now_ts))
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


async def _build_tg_general_report_blocks(chat_id: int, days: int) -> list[str]:
    details = await db.get_tg_tracked_users_details(chat_id)
    now_ts = int(datetime.now(tz=MSK).timestamp())
    since_ts = _period_to_since_ts(days)

    if not details:
        return ["📋 Список отслеживаемых пользователей [TG] пуст."]

    blocks = [f"<b>📊 Общий отчет [TG] за период:</b> {_escape_html(_format_period_label(days))}"]
    for detail in details:
        sessions = await db.get_tg_online_sessions_for_period(
            chat_id,
            int(detail["telegram_user_id"]),
            since_ts=since_ts,
        )
        total_duration = sum(_session_duration_for_period(session, since_ts, now_ts) for session in sessions)
        display_name = _tg_display_name(detail)
        username = str(detail.get("username") or "").strip()
        profile_link = str(detail.get("profile_link") or f"tg://user?id={int(detail['telegram_user_id'])}")
        lines = [
            f"<b>{_escape_html(display_name)}</b>",
            f"ID: <code>{detail['telegram_user_id']}</code>",
            f"Статус: {_escape_html(_build_tg_status_label(detail))}",
            _build_tg_activity_line(detail),
            f"Заходов: <b>{len(sessions)}</b>",
            f"Суммарно онлайн: <b>{_format_duration(total_duration)}</b>",
            f"🔗 <a href='{_escape_html(profile_link)}'>{_escape_html(profile_link)}</a>",
        ]
        if username:
            lines.insert(2, f"Username: <code>@{_escape_html(username)}</code>")
        blocks.append("\n".join(lines))

    return blocks


async def _show_tg_profile_change_type_picker(message: Message, telegram_user_id: int, source: str) -> None:
    detail = await db.get_tg_tracked_user_detail(message.chat.id, telegram_user_id)
    if detail is None:
        await message.answer(
            "⚠️ Telegram-пользователь не найден в отслеживаемых.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer(
        f"🧩 Выберите тип изменений профиля [TG] для <b>{_escape_html(_tg_display_name(detail))}</b>.",
        reply_markup=tg_profile_change_type_keyboard(telegram_user_id, TG_PROFILE_CHANGE_TYPE_ITEMS, source),
    )


async def _show_tg_profile_change_period_picker(
    message: Message,
    telegram_user_id: int,
    change_key: str,
    source: str,
) -> None:
    detail = await db.get_tg_tracked_user_detail(message.chat.id, telegram_user_id)
    if detail is None:
        await message.answer(
            "⚠️ Telegram-пользователь не найден в отслеживаемых.",
            reply_markup=main_menu_keyboard(),
        )
        return

    meta = _get_tg_profile_change_meta(change_key)
    await message.answer(
        f"🗓️ Выберите период для отчета: <b>{_escape_html(str(meta['label']))}</b>.",
        reply_markup=tg_profile_change_period_keyboard(telegram_user_id, change_key, source),
    )


async def _show_tg_profile_change_report(
    message: Message,
    telegram_user_id: int,
    change_key: str,
    days: int,
    source: str,
) -> None:
    detail = await db.get_tg_tracked_user_detail(message.chat.id, telegram_user_id)
    if detail is None:
        await message.answer(
            "⚠️ Telegram-пользователь не найден в отслеживаемых.",
            reply_markup=main_menu_keyboard(),
        )
        return

    meta = _get_tg_profile_change_meta(change_key)
    change_label = str(meta["label"])
    change_types = meta.get("types")
    changes = await db.get_tg_profile_changes_for_report(
        chat_id=message.chat.id,
        telegram_user_id=telegram_user_id,
        change_types=list(change_types) if isinstance(change_types, list) else None,
        since_ts=_period_to_since_ts(days),
        limit=300,
    )

    display_name = _tg_display_name(detail)
    username = str(detail.get("username") or "").strip()
    profile_link = str(detail.get("profile_link") or f"tg://user?id={telegram_user_id}")
    header = "\n".join(
        [
            "<b>📝 Отчет по изменениям профиля [TG]</b>",
            f"👤 <b>{_escape_html(display_name)}</b>",
            f"ID: <code>{telegram_user_id}</code>",
            f"Username: <code>{_escape_html('@' + username if username else 'не указан')}</code>",
            f"🔗 <a href='{_escape_html(profile_link)}'>{_escape_html(profile_link)}</a>",
            f"Тип изменений: <b>{_escape_html(change_label)}</b>",
            f"Период: <b>{_escape_html(_format_period_label(days))}</b>",
        ]
    )

    if not changes:
        empty_text = f"{header}\n\n🔍 Изменения за выбранный период не найдены."
        if change_key == "gifts":
            if detail.get("gifts_supported") is True:
                empty_text += (
                    "\nℹ️ Сейчас клиентский слой дает только счетчик подарков. "
                    "Если количество изменится, бот зафиксирует это как изменение."
                )
            else:
                empty_text += (
                    "\nℹ️ Текущий клиентский слой не дает надежной истории подарков чужого профиля. "
                    "Бот не симулирует эти данные."
                )
        await message.answer(
            empty_text,
            reply_markup=tg_profile_change_result_keyboard(telegram_user_id, change_key, source),
            disable_web_page_preview=True,
        )
        return

    blocks = [header]
    for change in changes:
        blocks.append(_build_tg_profile_change_block(change))

    await _send_long_html(message, blocks)
    await message.answer(
        "📝 Что дальше?",
        reply_markup=tg_profile_change_result_keyboard(telegram_user_id, change_key, source),
    )


async def _show_tracked_users_screen(message: Message) -> None:
    snapshots = await _load_tracked_snapshots(message.chat.id)
    if not snapshots:
        await message.answer(
            "📋 Список отслеживаемых пользователей пуст.\n"
            "Добавьте пользователя через кнопку «Добавить пользователя [VK]» или команду /add.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await _send_tracked_list_chunks(
        message,
        snapshots=snapshots,
        source=SOURCE_LIST,
        title="<b>📋 Список отслеживаемых пользователей [VK]</b>",
    )


async def _show_user_report_menu(message: Message, vk_id: int, source: str) -> None:
    snapshot = await _get_single_snapshot(message.chat.id, vk_id)
    if snapshot is None:
        await message.answer(
            "⚠️ Пользователь не найден в списке отслеживаемых.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer(
        "\n".join(
            [
                "<b>📊 Отчеты по пользователю [VK]</b>",
                f"👤 <b>{_escape_html(snapshot['name'])}</b>",
                f"🪪 ID: <code>{snapshot['vk_id']}</code>",
                "👇 Выберите, какой отчет нужно показать.",
            ]
        ),
        reply_markup=user_report_menu_keyboard(vk_id=snapshot["vk_id"], source=source),
    )


async def _show_online_report_user_picker(message: Message) -> None:
    snapshots = await _load_tracked_snapshots(message.chat.id)
    if not snapshots:
        await message.answer(
            "📈 Список отслеживаемых пользователей пуст.\n"
            "Сначала добавьте пользователей через кнопку «Добавить пользователя».",
            reply_markup=main_menu_keyboard(),
        )
        return

    items = [(int(snapshot["vk_id"]), str(snapshot["name"])) for snapshot in snapshots]
    for start in range(0, len(items), 20):
        chunk = items[start:start + 20]
        await message.answer(
            "📈 Выберите пользователя, по которому нужен отчет по онлайну.",
            reply_markup=user_picker_keyboard(chunk, source=SOURCE_ONLINE_REPORT, back_target="vk_menu"),
        )


async def _show_general_report_period_picker(message: Message) -> None:
    snapshots = await _load_tracked_snapshots(message.chat.id)
    if not snapshots:
        await message.answer(
            "📊 Список отслеживаемых пользователей пуст.\n"
            "Сначала добавьте пользователей через кнопку «Добавить пользователя».",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer(
        "📊 Выберите период для общего отчета [VK].",
        reply_markup=report_period_keyboard(scope="all", vk_id=0, source="all", back_target="general_reports_hub"),
    )


async def _show_search_results(message: Message, state: FSMContext, query: str) -> None:
    snapshots = await _load_tracked_snapshots(message.chat.id)
    if not snapshots:
        await state.set_state(SearchStates.waiting_for_query)
        await message.answer(
            "🔎 Список отслеживаемых пользователей пуст.\n"
            "Сначала добавьте пользователей через кнопку «Добавить пользователя».",
            reply_markup=main_menu_keyboard(),
        )
        return

    normalized_query = _normalize_name(query)
    matches = []
    for snapshot in snapshots:
        first_norm = _normalize_name(str(snapshot["first_name"]))
        last_norm = _normalize_name(str(snapshot["last_name"]))
        full_norm = _normalize_name(f"{snapshot['first_name']} {snapshot['last_name']}")

        if normalized_query in {first_norm, last_norm, full_norm}:
            matches.append(snapshot)
            continue

        if normalized_query and (
            normalized_query in first_norm or normalized_query in last_norm or normalized_query in full_norm
        ):
            matches.append(snapshot)

    await state.update_data(search_query=query)

    if not matches:
        await state.set_state(SearchStates.waiting_for_query)
        await message.answer(
            "🔎 Совпадений не найдено.\n"
            "Попробуйте ввести другое имя или фамилию.",
            reply_markup=back_main_inline_keyboard("main"),
        )
        return

    await state.set_state(SearchStates.viewing_results)
    await _send_tracked_list_chunks(
        message,
        snapshots=matches,
        source=SOURCE_SEARCH,
        title=f"<b>🔎 Результаты поиска:</b> <code>{query}</code>",
    )


async def _show_user_card(message: Message, vk_id: int, source: str) -> None:
    snapshot = await _get_single_snapshot(message.chat.id, vk_id)
    if snapshot is None:
        await message.answer(
            "⚠️ Пользователь не найден в списке отслеживаемых.",
            reply_markup=main_menu_keyboard(),
        )
        return

    lines = [
        f"👤 <b>{_escape_html(snapshot['name'])}</b>",
        f"ID: <code>{snapshot['vk_id']}</code>",
        f"🔗 <a href='{_escape_html(snapshot['profile_link'])}'>{_escape_html(snapshot['profile_link'])}</a>",
        f"Статус: {_build_status_line(int(snapshot['online']))}",
        f"🕐 Последний визит: {vk_api.format_last_seen(snapshot['last_seen'] or None)}",
        f"📅 Добавлен в отслеживание: {_format_added_at(snapshot['added_at'])}",
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

        lines.append(f"{icon} {label}: {_escape_html(_truncate_text(display_value))}")

    lines.extend(await _build_relation_privacy_lines(vk_id))

    await message.answer(
        "\n".join(lines),
        reply_markup=user_card_keyboard(vk_id=snapshot["vk_id"], source=source),
        disable_web_page_preview=True,
    )


async def _show_manual_status(message: Message, vk_id: int) -> None:
    user = await vk_api.get_single_user_status(vk_id)
    cached = await db.get_last_status(vk_id)
    cached_profile = await db.get_profile_cache(vk_id)

    if user is None and cached is None:
        await message.answer(
            f"Не удалось получить статус пользователя <code>{vk_id}</code>.\n"
            "Проверьте ссылку на профиль или попробуйте позже.",
            reply_markup=main_menu_keyboard(),
        )
        return

    profile_snapshot = vk_api.extract_profile_snapshot(user) if user else {}
    if user:
        first_name = profile_snapshot.get("first_name", "") or user.get("first_name", "")
        last_name = profile_snapshot.get("last_name", "") or user.get("last_name", "")
        online = int(user.get("online", 0) or 0)
        last_seen = vk_api.extract_last_seen_ts(user)
    else:
        first_name = cached.get("first_name", "")
        last_name = cached.get("last_name", "")
        online = int(cached.get("online", 0) or 0)
        last_seen = cached.get("last_seen")

    name = _build_name(first_name, last_name, vk_id)
    tracked_detail = await db.get_tracked_user_detail(message.chat.id, vk_id)
    added_line = None
    if tracked_detail is not None:
        added_line = f"📅 Добавлен в отслеживание: {_format_added_at(tracked_detail.get('added_at'))}"

    domain = None
    if "domain" in profile_snapshot:
        domain = profile_snapshot.get("domain")
    elif cached_profile is not None:
        domain = cached_profile.get("domain")
    profile_link = vk_api.build_profile_link(vk_id, domain)

    lines = [
        f"👤 <b>{_escape_html(name)}</b>",
        f"ID: <code>{vk_id}</code>",
        f"🔗 <a href='{_escape_html(profile_link)}'>{_escape_html(profile_link)}</a>",
        f"Статус: {_build_status_line(online)}",
        f"🕐 Последний визит: {vk_api.format_last_seen(last_seen)}",
    ]
    if added_line:
        lines.append(added_line)

    snapshot_for_view = cached_profile or {}
    if profile_snapshot:
        snapshot_for_view = {**snapshot_for_view, **profile_snapshot}

    for field_name, icon, label in PROFILE_CARD_FIELD_META:
        value = snapshot_for_view.get(field_name)
        if field_name not in {"is_closed", "profile_status_text"} and value in (None, ""):
            continue

        display_value = vk_api.format_profile_field_value(field_name, value)
        if field_name not in {"is_closed", "profile_status_text"} and display_value == "не указано":
            continue
        if field_name == "profile_status_text" and display_value == "пусто":
            continue

        lines.append(f"{icon} {label}: {_escape_html(_truncate_text(display_value))}")

    lines.extend(await _build_relation_privacy_lines(vk_id))

    await message.answer(
        "\n".join(lines),
        reply_markup=main_menu_keyboard(),
        disable_web_page_preview=True,
    )


async def _show_delete_confirmation(message: Message, vk_id: int, source: str) -> None:
    snapshot = await _get_single_snapshot(message.chat.id, vk_id)
    if snapshot is None:
        await message.answer("Пользователь уже отсутствует в списке отслеживаемых.", reply_markup=main_menu_keyboard())
        return

    await message.answer(
        f"🗑️ Удалить пользователя <b>{snapshot['name']}</b> из отслеживания?",
        reply_markup=delete_confirm_keyboard(vk_id, source),
    )


async def _build_detailed_report_block(chat_id: int, snapshot: dict, sessions_limit: int = 10) -> str:
    sessions = await db.get_online_sessions(chat_id, int(snapshot["vk_id"]), limit=sessions_limit)
    lines = [
        f"<b>{snapshot['name']}</b>",
        f"ID: <code>{snapshot['vk_id']}</code>",
        f"🔗 <a href='{snapshot['profile_link']}'>{snapshot['profile_link']}</a>",
        f"Статус: {_build_status_line(int(snapshot['online']))}",
        f"🕐 Последний визит: {vk_api.format_last_seen(snapshot['last_seen'] or None)}",
        "",
        "<b>📈 Отчет по онлайну:</b>",
    ]

    if sessions:
        for index, session in enumerate(sessions, start=1):
            lines.append(
                _format_session_block(
                    index=index,
                    started_at=int(session["started_at"]),
                    ended_at=int(session["ended_at"]) if session["ended_at"] is not None else None,
                )
            )
            lines.append("")
    else:
        lines.append("Сессий пока нет.")

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


async def _build_period_user_report(chat_id: int, snapshot: dict, days: int) -> str:
    now_ts = int(datetime.now(tz=MSK).timestamp())
    since_ts = now_ts - days * 86400 if days else None
    sessions = await db.get_online_sessions_for_period(chat_id, int(snapshot["vk_id"]), since_ts=since_ts)

    total_duration = sum(_session_duration_for_period(session, since_ts, now_ts) for session in sessions)
    lines = [
        f"<b>{snapshot['name']}</b>",
        f"ID: <code>{snapshot['vk_id']}</code>",
        f"🔗 <a href='{snapshot['profile_link']}'>{snapshot['profile_link']}</a>",
        f"Статус: {_build_status_line(int(snapshot['online']))}",
        f"🕐 Последний визит: {vk_api.format_last_seen(snapshot['last_seen'] or None)}",
        f"📊 Период: <b>{_format_period_label(days)}</b>",
        f"Количество заходов: <b>{len(sessions)}</b>",
        f"Суммарное время онлайна: <b>{_format_duration(total_duration)}</b>",
        "",
        "<b>Сессии за период:</b>",
    ]

    if sessions:
        for index, session in enumerate(sessions, start=1):
            lines.append(
                _format_session_block(
                    index=index,
                    started_at=int(session["started_at"]),
                    ended_at=int(session["ended_at"]) if session["ended_at"] is not None else None,
                )
            )
            lines.append("")
    else:
        lines.append("🔍 За выбранный период сессий не найдено.")

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


async def _build_general_report_blocks(chat_id: int, days: int) -> list[str]:
    snapshots = await _load_tracked_snapshots(chat_id)
    now_ts = int(datetime.now(tz=MSK).timestamp())
    since_ts = now_ts - days * 86400 if days else None

    if not snapshots:
        return ["📋 Список отслеживаемых пользователей пуст."]

    blocks = [f"<b>📊 Общий отчет за период:</b> {_format_period_label(days)}"]
    for snapshot in snapshots:
        sessions = await db.get_online_sessions_for_period(chat_id, int(snapshot["vk_id"]), since_ts=since_ts)
        total_duration = sum(_session_duration_for_period(session, since_ts, now_ts) for session in sessions)
        blocks.append(
            "\n".join(
                [
                    f"<b>{snapshot['name']}</b>",
                    f"ID: <code>{snapshot['vk_id']}</code>",
                    f"🔗 <a href='{snapshot['profile_link']}'>{snapshot['profile_link']}</a>",
                    f"Заходов: <b>{len(sessions)}</b>",
                    f"Суммарно онлайн: <b>{_format_duration(total_duration)}</b>",
                    f"Последний визит: {vk_api.format_last_seen(snapshot['last_seen'] or None)}",
                ]
            )
        )

    return blocks


async def _perform_add_user(message: Message, user: dict[str, Any]) -> None:
    chat_id = message.chat.id
    vk_id = int(user["id"])

    if user.get("deactivated"):
        reason = user.get("deactivated", "удалён")
        await message.answer(f"Аккаунт <code>{vk_id}</code> {reason} и недоступен для отслеживания.")
        return

    added = await db.add_tracked_user(chat_id, vk_id)
    first_name = user.get("first_name", "")
    last_name = user.get("last_name", "")
    name = _build_name(first_name, last_name, vk_id)
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

    if added:
        profile_snapshot = vk_api.extract_profile_snapshot(user)
        await db.save_profile_cache(vk_id, profile_snapshot)
        await message.answer(
            f"Добавлен: <b>{name}</b>\n"
            f"ID: <code>{vk_id}</code>\n"
            f"Текущий статус: {'онлайн' if user.get('online') else 'офлайн'}",
            reply_markup=main_menu_keyboard(),
        )
    else:
        profile_snapshot = vk_api.extract_profile_snapshot(user)
        await db.save_profile_cache(vk_id, profile_snapshot)
        await message.answer(
            f"Пользователь <b>{name}</b> уже отслеживается.\n"
            f"ID: <code>{vk_id}</code>",
            reply_markup=main_menu_keyboard(),
        )


async def _resolve_vk_user_from_link(raw_link: str) -> dict[str, Any] | None:
    screen_name = vk_api.extract_vk_screen_name(raw_link)
    if screen_name is None:
        return None
    return await vk_api.resolve_user_by_vk_link(raw_link)


def _vk_link_formats_text() -> str:
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


async def _show_screen_by_nav_target(message: Message, target: str, state: FSMContext) -> None:
    if target == "main":
        await state.clear()
        await _show_main_menu(message)
        return
    if target == "vk_menu":
        await state.clear()
        await _show_vk_menu(message)
        return
    if target == "tg_menu":
        await state.clear()
        await _show_tg_menu(message)
        return
    if target == "general_reports_hub":
        await state.clear()
        await _show_reports_hub(message)
        return
    if target == "general_report_vk_period":
        await state.clear()
        await _show_general_report_period_picker(message)
        return
    if target == "notification_hub":
        await state.clear()
        await _show_notifications_hub(message)
        return
    if target == "notify_vk":
        await state.clear()
        await _show_notification_settings(message, back_target="notification_hub")
        return
    if target == "notify_tg":
        await state.clear()
        await _show_tg_notification_settings(message, back_target="notification_hub")
        return
    if target == "vk_add":
        await _show_add_prompt(message, state)
        return
    if target == "vk_list":
        await state.clear()
        await _show_tracked_users_screen(message)
        return
    if target == "tg_add":
        await _show_tg_add_prompt(message, state)
        return
    if target == "tg_list":
        await state.clear()
        await _show_tg_tracked_users_screen(message)
        return
    if target == "tg_general_report":
        await state.clear()
        await _show_tg_general_report_period_picker(message)
        return
    if target == "list":
        await state.clear()
        await _show_tracked_users_screen(message)
        return
    if target == "report_users":
        await state.clear()
        await _show_online_report_user_picker(message)
        return
    if target == "general_report_period":
        await state.clear()
        await _show_general_report_period_picker(message)
        return
    if target == "search_prompt":
        await _show_search_prompt(message, state)
        return
    if target == "search_results":
        data = await state.get_data()
        query = str(data.get("search_query", "")).strip()
        if not query:
            await _show_search_prompt(message, state)
            return
        await _show_search_results(message, state, query)
        return
    if target == "notify":
        await state.clear()
        await _show_notifications_hub(message)
        return
    if target == "help":
        await state.clear()
        await _show_help(message)
        return
    if target == "profile_changes":
        await state.clear()
        await _show_profile_change_user_picker(message)
        return

    await _show_main_menu(message)


@router.callback_query(lambda callback: callback.data == CHECK_SUBSCRIPTION_CALLBACK)
async def cb_check_subscription(callback: CallbackQuery) -> None:
    user = callback.from_user
    if user and await _has_required_subscription(callback.bot, user.id):
        await callback.answer("Подписка подтверждена.", show_alert=True)
        if callback.message:
            await callback.message.answer(
                "✅ Подписка подтверждена. Теперь можно пользоваться ботом.",
                reply_markup=main_menu_keyboard(),
            )
        return

    await callback.answer("❌ Подписка пока не найдена.", show_alert=True)
    await _send_subscription_required(callback)


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_main_menu(
        message,
        text=(
            "👋 Привет. Это бот с раздельным интерфейсом для двух платформ.\n\n"
            "Сначала выберите нужный раздел:\n"
            f"• <b>{BTN_PLATFORM_VK}</b> — все действия только по ВКонтакте\n"
            f"• <b>{BTN_PLATFORM_TG}</b> — все действия только по Telegram с отдельными статусами и отчетами\n"
            f"• <b>{BTN_GENERAL_REPORT}</b> — общие отчеты верхнего уровня по платформам\n"
            f"• <b>{BTN_NOTIFY}</b> — настройки уведомлений по платформам\n"
            f"• <b>{BTN_HELP}</b> — справка по новому интерфейсу\n\n"
            "Карточки пользователей и персональные отчеты VK и TG между собой не смешиваются."
        ),
    )


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_help(message)


@router.message(F.text == BTN_PLATFORM_VK)
async def menu_platform_vk(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_vk_menu(message)


@router.message(F.text == BTN_PLATFORM_TG)
async def menu_platform_tg(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_tg_menu(message)


@router.message(F.text == BTN_ADD_USER)
async def menu_add_user(message: Message, state: FSMContext) -> None:
    await _show_add_prompt(message, state)


@router.message(F.text == BTN_ADD_USER_TG)
async def menu_add_user_tg(message: Message, state: FSMContext) -> None:
    await _show_tg_add_prompt(message, state)


@router.message(F.text == BTN_TRACKED_LIST)
async def menu_tracked_list(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_tracked_users_screen(message)


@router.message(F.text == BTN_TRACKED_LIST_TG)
async def menu_tracked_list_tg(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_tg_tracked_users_screen(message)


@router.message(F.text == BTN_ONLINE_REPORT)
async def menu_online_report(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_online_report_user_picker(message)


@router.message(F.text == BTN_GENERAL_REPORT)
async def menu_general_report(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_reports_hub(message)


@router.message(F.text == BTN_GENERAL_REPORT_VK)
async def menu_general_report_vk(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_general_report_period_picker(message)


@router.message(F.text == BTN_GENERAL_REPORT_TG)
async def menu_general_report_tg(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_tg_general_report_period_picker(message)


@router.message(F.text == BTN_SEARCH)
async def menu_search(message: Message, state: FSMContext) -> None:
    await _show_search_prompt(message, state)


@router.message(F.text == BTN_NOTIFY)
async def menu_notify(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_notifications_hub(message)


@router.message(F.text == BTN_NOTIFY_VK)
async def menu_notify_vk(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_notification_settings(message, back_target="notification_hub")


@router.message(F.text == BTN_NOTIFY_TG)
async def menu_notify_tg(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_tg_notification_settings(message, back_target="notification_hub")


@router.message(F.text == BTN_PROFILE_CHANGES)
async def menu_profile_changes(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_profile_change_user_picker(message)


@router.message(F.text == BTN_HELP)
async def menu_help(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_help(message)


@router.callback_query(NavCallback.filter())
async def cb_nav(callback: CallbackQuery, callback_data: NavCallback, state: FSMContext) -> None:
    await callback.answer()
    if callback.message:
        await _show_screen_by_nav_target(callback.message, callback_data.target, state)


@router.callback_query(NotifyModeCallback.filter())
async def cb_notify_mode(callback: CallbackQuery, callback_data: NotifyModeCallback) -> None:
    await callback.answer("Настройка обновлена.")
    if callback.message is None:
        return

    mode = await db.set_notification_mode(callback.message.chat.id, callback_data.mode)
    await _show_notification_settings(
        callback.message,
        text=f"🔔 Режим онлайн-уведомлений обновлен: <b>{NOTIFICATION_MODE_LABELS[mode]}</b>",
        back_target="notification_hub",
    )


@router.callback_query(NotifyToggleCallback.filter())
async def cb_notify_toggle(callback: CallbackQuery, callback_data: NotifyToggleCallback) -> None:
    await callback.answer("Настройка обновлена.")
    if callback.message is None:
        return

    enabled = await db.toggle_change_notification(callback.message.chat.id, callback_data.key)
    label = CHANGE_NOTIFICATION_LABELS.get(callback_data.key, callback_data.key)
    status_text = "включены" if enabled else "отключены"
    await _show_notification_settings(
        callback.message,
        text=f"🔔 Уведомления по категории <b>{_escape_html(label)}</b> {status_text}.",
        back_target="notification_hub",
    )


@router.callback_query(TgNotifyModeCallback.filter())
async def cb_tg_notify_mode(callback: CallbackQuery, callback_data: TgNotifyModeCallback) -> None:
    await callback.answer("Настройка обновлена.")
    if callback.message is None:
        return

    mode = await db.set_tg_notification_mode(callback.message.chat.id, callback_data.mode)
    await _show_tg_notification_settings(
        callback.message,
        text=f"🔔 Режим TG-уведомлений обновлен: <b>{NOTIFICATION_MODE_LABELS[mode]}</b>",
        back_target="notification_hub",
    )


@router.callback_query(TgNotifyToggleCallback.filter())
async def cb_tg_notify_toggle(callback: CallbackQuery, callback_data: TgNotifyToggleCallback) -> None:
    await callback.answer("Настройка обновлена.")
    if callback.message is None:
        return

    if callback_data.key == "activity":
        enabled = await db.toggle_tg_activity_notification(callback.message.chat.id)
        label = TG_NOTIFICATION_TOGGLE_LABELS["activity"]
    elif callback_data.key in TG_CHANGE_NOTIFICATION_LABELS:
        enabled = await db.toggle_tg_change_notification(callback.message.chat.id, callback_data.key)
        label = TG_CHANGE_NOTIFICATION_LABELS[callback_data.key]
    else:
        await _show_tg_notification_settings(
            callback.message,
            text="⚠️ Неизвестная TG-настройка уведомлений.",
            back_target="notification_hub",
        )
        return

    status_text = "включены" if enabled else "отключены"
    await _show_tg_notification_settings(
        callback.message,
        text=f"🔔 Уведомления по категории <b>{_escape_html(label)}</b> {status_text}.",
        back_target="notification_hub",
    )


@router.callback_query(TgProfileChangeTypeCallback.filter())
async def cb_tg_profile_change_type(callback: CallbackQuery, callback_data: TgProfileChangeTypeCallback) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await _show_tg_profile_change_period_picker(
        callback.message,
        callback_data.tg_id,
        callback_data.key,
        callback_data.src,
    )


@router.callback_query(TgProfileChangePeriodCallback.filter())
async def cb_tg_profile_change_period(callback: CallbackQuery, callback_data: TgProfileChangePeriodCallback) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await _show_tg_profile_change_report(
        callback.message,
        callback_data.tg_id,
        callback_data.key,
        callback_data.days,
        callback_data.src,
    )


@router.callback_query(ProfileChangeUserCallback.filter())
async def cb_profile_change_user(callback: CallbackQuery, callback_data: ProfileChangeUserCallback) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await _show_profile_change_type_picker(callback.message, callback_data.vk_id, callback_data.src)


@router.callback_query(ProfileChangeTypeCallback.filter())
async def cb_profile_change_type(callback: CallbackQuery, callback_data: ProfileChangeTypeCallback) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await _show_profile_change_period_picker(
        callback.message,
        callback_data.vk_id,
        callback_data.key,
        callback_data.src,
    )


@router.callback_query(ProfileChangePeriodCallback.filter())
async def cb_profile_change_period(callback: CallbackQuery, callback_data: ProfileChangePeriodCallback) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await _show_profile_change_report(
        callback.message,
        callback_data.vk_id,
        callback_data.key,
        callback_data.days,
        callback_data.src,
    )


@router.callback_query(UserActionCallback.filter())
async def cb_user_action(callback: CallbackQuery, callback_data: UserActionCallback, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return

    if callback_data.action == "card":
        await _show_user_card(
            callback.message,
            vk_id=callback_data.vk_id,
            source=_card_source(callback_data.src),
        )
        return

    if callback_data.action == "report":
        await _show_user_report_menu(
            callback.message,
            vk_id=callback_data.vk_id,
            source=_report_source(callback_data.src),
        )
        return

    if callback_data.action == "profile_changes":
        await _show_profile_change_type_picker(
            callback.message,
            callback_data.vk_id,
            _report_source(callback_data.src),
        )
        return

    if callback_data.action == "online_report":
        await callback.message.answer(
            "🗓️ Выберите период для отчета по онлайну.",
            reply_markup=report_period_keyboard(
                scope="user",
                vk_id=callback_data.vk_id,
                source=_report_source(callback_data.src),
                back_target=_source_nav_target(callback_data.src),
            ),
        )
        return

    if callback_data.action == "period":
        await callback.message.answer(
            "🗓️ Выберите период для отчета.",
            reply_markup=report_period_keyboard(
                scope="user",
                vk_id=callback_data.vk_id,
                source=callback_data.src,
                back_target=_source_nav_target(callback_data.src),
            ),
        )
        return

    if callback_data.action == "delete":
        await _show_delete_confirmation(callback.message, callback_data.vk_id, callback_data.src)
        return

    await _show_main_menu(callback.message)


@router.callback_query(TgUserActionCallback.filter())
async def cb_tg_user_action(callback: CallbackQuery, callback_data: TgUserActionCallback, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return

    if callback_data.action in {"card", "profile"}:
        await _show_tg_user_card(callback.message, callback_data.tg_id, callback_data.src)
        return

    if callback_data.action == "delete":
        await _show_tg_delete_confirmation(callback.message, callback_data.tg_id, callback_data.src)
        return

    if callback_data.action == "online_report":
        await _show_tg_report_period_picker(callback.message, callback_data.tg_id, callback_data.src)
        return

    if callback_data.action == "profile_changes":
        await _show_tg_profile_change_type_picker(callback.message, callback_data.tg_id, callback_data.src)
        return

    await _show_tg_tracked_users_screen(callback.message)


@router.callback_query(DeleteConfirmCallback.filter())
async def cb_delete_confirm(
    callback: CallbackQuery,
    callback_data: DeleteConfirmCallback,
    state: FSMContext,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    if callback_data.confirm == 0:
        if callback_data.src.startswith("c"):
            await _show_user_card(callback.message, callback_data.vk_id, callback_data.src)
        else:
            await _show_screen_by_nav_target(callback.message, _source_nav_target(callback_data.src), state)
        return

    removed = await db.remove_tracked_user(callback.message.chat.id, callback_data.vk_id)
    if removed:
        await callback.message.answer(
            f"Пользователь с ID <code>{callback_data.vk_id}</code> удалён из отслеживания.",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await callback.message.answer(
            f"Пользователь с ID <code>{callback_data.vk_id}</code> не найден в списке отслеживаемых.",
            reply_markup=main_menu_keyboard(),
        )

    if callback_data.src in {"srh", "csrh"}:
        data = await state.get_data()
        query = str(data.get("search_query", "")).strip()
        if query:
            await _show_search_results(callback.message, state, query)
            return
    if callback_data.src in {"orp", "corp"}:
        await _show_online_report_user_picker(callback.message)
        return
    await _show_tracked_users_screen(callback.message)


@router.callback_query(TgDeleteConfirmCallback.filter())
async def cb_tg_delete_confirm(callback: CallbackQuery, callback_data: TgDeleteConfirmCallback) -> None:
    await callback.answer()
    if callback.message is None:
        return

    if callback_data.confirm == 0:
        await _show_tg_user_card(callback.message, callback_data.tg_id, callback_data.src)
        return

    removed = await db.remove_tg_tracked_user(callback.message.chat.id, callback_data.tg_id)
    if removed:
        await callback.message.answer(
            f"Telegram-пользователь с ID <code>{callback_data.tg_id}</code> удален из отслеживания.",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await callback.message.answer(
            f"Telegram-пользователь с ID <code>{callback_data.tg_id}</code> не найден в списке отслеживаемых.",
            reply_markup=main_menu_keyboard(),
        )

    await _show_tg_tracked_users_screen(callback.message)


@router.callback_query(TgPeriodSelectCallback.filter())
async def cb_tg_period_select(callback: CallbackQuery, callback_data: TgPeriodSelectCallback) -> None:
    await callback.answer()
    if callback.message is None:
        return

    if callback_data.scope == "all":
        blocks = await _build_tg_general_report_blocks(callback.message.chat.id, callback_data.days)
        await _send_long_html(callback.message, blocks)
        await callback.message.answer(
            "📊 Что дальше?",
            reply_markup=general_report_result_keyboard_with_target("tg_general_report"),
        )
        return

    detail = await db.get_tg_tracked_user_detail(callback.message.chat.id, callback_data.tg_id)
    if detail is None:
        await callback.message.answer(
            "⚠️ Telegram-пользователь не найден в отслеживаемых.",
            reply_markup=main_menu_keyboard(),
        )
        return

    report_text = await _build_tg_period_user_report(callback.message.chat.id, detail, callback_data.days)
    await _send_long_html(callback.message, [report_text])
    await callback.message.answer(
        "📈 Что дальше?",
        reply_markup=tg_report_result_keyboard(callback_data.tg_id, callback_data.src),
    )


@router.callback_query(PeriodSelectCallback.filter())
async def cb_period_select(callback: CallbackQuery, callback_data: PeriodSelectCallback) -> None:
    await callback.answer()
    if callback.message is None:
        return

    if callback_data.scope == "all":
        blocks = await _build_general_report_blocks(callback.message.chat.id, callback_data.days)
        await _send_long_html(callback.message, blocks)
        await callback.message.answer(
            "📊 Что дальше?",
            reply_markup=general_report_result_keyboard_with_target("general_report_vk_period"),
        )
        return

    snapshot = await _get_single_snapshot(callback.message.chat.id, callback_data.vk_id)
    if snapshot is None:
        await callback.message.answer(
            "⚠️ Пользователь не найден в отслеживаемых.",
            reply_markup=main_menu_keyboard(),
        )
        return

    report_text = await _build_period_user_report(callback.message.chat.id, snapshot, callback_data.days)
    await _send_long_html(callback.message, [report_text])
    await callback.message.answer(
        "📈 Что дальше?",
        reply_markup=report_result_keyboard(callback_data.vk_id, callback_data.src),
    )


@router.message(Command("notify"))
async def cmd_notify(message: Message, state: FSMContext) -> None:
    await state.clear()
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await _show_notification_settings(message, back_target="notification_hub")
        return

    requested_mode = parts[1].strip().lower()
    if requested_mode not in db.VALID_NOTIFICATION_MODES:
        await message.answer(
            "Неизвестный режим уведомлений.\n"
            "Используйте: <code>/notify online</code>, <code>/notify offline</code>, "
            "<code>/notify all</code> или <code>/notify off</code>.",
            reply_markup=main_menu_keyboard(),
        )
        return

    mode = await db.set_notification_mode(message.chat.id, requested_mode)
    await _show_notification_settings(
        message,
        text=f"🔔 Режим онлайн-уведомлений обновлен: <b>{NOTIFICATION_MODE_LABELS[mode]}</b>",
        back_target="notification_hub",
    )


@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext) -> None:
    await state.clear()
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Укажите ссылку на профиль VK после команды.\n"
            "Пример: <code>/add https://vk.com/durov</code>",
            reply_markup=main_menu_keyboard(),
        )
        return

    raw_link = parts[1].strip()
    user = await _resolve_vk_user_from_link(raw_link)
    if user is None:
        await message.answer(
            "Не удалось распознать ссылку на профиль VK.\n"
            f"{_vk_link_formats_text()}",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer("Проверяю пользователя ВКонтакте...")
    await _perform_add_user(message, user)


@router.message(StateFilter(AddUserStates.waiting_for_vk_link), F.text)
async def state_add_user(message: Message, state: FSMContext) -> None:
    raw_link = (message.text or "").strip()
    user = await _resolve_vk_user_from_link(raw_link)
    if user is None:
        await message.answer(
            "Нужно отправить ссылку на профиль VK.\n"
            f"{_vk_link_formats_text()}",
            reply_markup=back_main_inline_keyboard("main"),
        )
        return

    await state.clear()
    await message.answer("Проверяю пользователя ВКонтакте...")
    await _perform_add_user(message, user)


@router.message(StateFilter(AddUserStates.waiting_for_tg_link), F.text)
async def state_add_user_tg(message: Message, state: FSMContext) -> None:
    raw_value = (message.text or "").strip()
    if raw_value == BTN_BACK:
        await state.clear()
        await _show_tg_menu(message)
        return
    if raw_value == BTN_MAIN_MENU:
        await state.clear()
        await _show_main_menu(message)
        return

    if not raw_value:
        await message.answer(
            "Нужно отправить username, @username или ссылку на Telegram-профиль.",
            reply_markup=tg_add_user_reply_keyboard(),
        )
        return

    tg_user, error_text = await _resolve_tg_user_from_input(message, raw_value)
    if tg_user is None:
        await message.answer(error_text or "Не удалось обработать Telegram-пользователя.", reply_markup=tg_add_user_reply_keyboard())
        return

    await state.clear()
    await message.answer("Проверяю Telegram-пользователя...", reply_markup=ReplyKeyboardRemove())
    await _perform_add_tg_user(message, tg_user)


@router.message(StateFilter(AddUserStates.waiting_for_tg_link), F.users_shared)
async def state_add_user_tg_shared(message: Message, state: FSMContext) -> None:
    users_shared = message.users_shared
    if users_shared is None or not users_shared.users:
        await message.answer(
            "Не удалось получить данные выбранного пользователя Telegram. Попробуйте еще раз.",
            reply_markup=tg_add_user_reply_keyboard(),
        )
        return

    shared_user = users_shared.users[0]
    await state.clear()
    await message.answer("Пользователь Telegram выбран. Сохраняю в отслеживание...", reply_markup=ReplyKeyboardRemove())
    added, detail = await _save_tg_user_from_shared(message, shared_user)
    display_name = _tg_display_name(detail)
    username = str(detail.get("username") or "").strip()
    username_line = f"\nUsername: <code>@{_escape_html(username)}</code>" if username else ""
    result_prefix = "Добавлен" if added else "Пользователь уже отслеживается, данные обновлены"
    await message.answer(
        f"🟨 {result_prefix}: <b>{_escape_html(display_name)}</b>\n"
        f"ID: <code>{detail['telegram_user_id']}</code>{username_line}",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("remove"))
async def cmd_remove(message: Message, state: FSMContext) -> None:
    await state.clear()
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Укажите ссылку на профиль VK после команды.\n"
            "Пример: <code>/remove https://vk.com/durov</code>",
            reply_markup=main_menu_keyboard(),
        )
        return

    raw_link = parts[1].strip()
    user = await _resolve_vk_user_from_link(raw_link)
    if user is None:
        await message.answer(
            "Не удалось распознать ссылку на профиль VK.\n"
            f"{_vk_link_formats_text()}",
            reply_markup=main_menu_keyboard(),
        )
        return

    vk_id = int(user["id"])
    name = _build_name(user.get("first_name", ""), user.get("last_name", ""), vk_id)
    removed = await db.remove_tracked_user(message.chat.id, vk_id)
    if removed:
        await message.answer(
            f"🗑️ Пользователь <b>{name}</b> удалён из списка слежки.\n"
            f"🔗 <a href='https://vk.com/id{vk_id}'>https://vk.com/id{vk_id}</a>",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await message.answer(
            f"⚠️ Пользователь <b>{name}</b> не найден в вашем списке отслеживаемых.",
            reply_markup=main_menu_keyboard(),
        )


@router.message(Command("list"))
async def cmd_list(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_tracked_users_screen(message)


@router.message(Command("status"))
async def cmd_status(message: Message, state: FSMContext) -> None:
    await state.clear()
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Укажите ссылку на профиль VK после команды.\n"
            "Пример: <code>/status https://vk.com/durov</code>",
            reply_markup=main_menu_keyboard(),
        )
        return

    raw_link = parts[1].strip()
    user = await _resolve_vk_user_from_link(raw_link)
    if user is None:
        await message.answer(
            "Не удалось распознать ссылку на профиль VK.\n"
            f"{_vk_link_formats_text()}",
            reply_markup=main_menu_keyboard(),
        )
        return

    vk_id = int(user["id"])
    await _show_manual_status(message, vk_id)


@router.message(Command("report"))
async def cmd_report(message: Message, state: FSMContext) -> None:
    await state.clear()
    snapshots = await _load_tracked_snapshots(message.chat.id)
    if not snapshots:
        await message.answer(
            "Список слежки пуст.\n"
            "Сначала добавьте пользователей через кнопку «Добавить пользователя».",
            reply_markup=main_menu_keyboard(),
        )
        return

    blocks = ["<b>Подробный отчет по всем отслеживаемым пользователям</b>"]
    for snapshot in snapshots:
        blocks.append(await _build_detailed_report_block(message.chat.id, snapshot))
    await _send_long_html(message, blocks)


@router.message(Command("find"))
async def cmd_find(message: Message, state: FSMContext) -> None:
    await state.clear()
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "Укажите имя или фамилию после команды.\n"
            "Примеры:\n"
            "<code>/find Павел</code>\n"
            "<code>/find Дуров</code>\n"
            "<code>/find Павел Дуров</code>",
            reply_markup=main_menu_keyboard(),
        )
        return

    await _show_search_results(message, state, parts[1].strip())


@router.message(StateFilter(SearchStates.waiting_for_query), F.text)
async def state_search_waiting(message: Message, state: FSMContext) -> None:
    query = (message.text or "").strip()
    if not query:
        await message.answer("Введите имя или фамилию для поиска.", reply_markup=back_main_inline_keyboard("main"))
        return

    await _show_search_results(message, state, query)


@router.message(StateFilter(SearchStates.viewing_results), F.text)
async def state_search_results(message: Message, state: FSMContext) -> None:
    query = (message.text or "").strip()
    if not query:
        await message.answer("Введите имя или фамилию для нового поиска.", reply_markup=back_main_inline_keyboard("main"))
        return

    await _show_search_results(message, state, query)


@router.message(Command("stop"))
async def cmd_stop(message: Message, state: FSMContext) -> None:
    await state.clear()
    vk_ids = await db.get_tracked_users(message.chat.id)
    if not vk_ids:
        await message.answer("У вас нет отслеживаемых пользователей.", reply_markup=main_menu_keyboard())
        return

    await db.set_tracking_active(message.chat.id, False)
    await message.answer(
        "Отслеживание приостановлено.\n"
        "Чтобы возобновить, отправьте /resume.",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("resume"))
async def cmd_resume(message: Message, state: FSMContext) -> None:
    await state.clear()
    all_rows = await db.get_all_user_rows(message.chat.id)
    if not all_rows:
        await message.answer(
            "У вас нет отслеживаемых пользователей.\n"
            "Добавьте их через кнопку «Добавить пользователя».",
            reply_markup=main_menu_keyboard(),
        )
        return

    await db.set_tracking_active(message.chat.id, True)
    await message.answer(
        "Отслеживание возобновлено.\n"
        "Вы снова будете получать уведомления по текущим настройкам.",
        reply_markup=main_menu_keyboard(),
    )
