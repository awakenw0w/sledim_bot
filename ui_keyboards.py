"""
Клавиатуры для основного кнопочного интерфейса.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ui_callbacks import (
    DeleteConfirmCallback,
    NavCallback,
    NotifyModeCallback,
    NotifyToggleCallback,
    PeriodSelectCallback,
    ProfileChangePeriodCallback,
    ProfileChangeTypeCallback,
    ProfileChangeUserCallback,
    UserActionCallback,
)

BTN_PLATFORM_VK = "ВКонтакте [VK]"
BTN_PLATFORM_TG = "Telegram [TG]"
BTN_ADD_USER = "➕ Добавить пользователя [VK]"
BTN_ADD_USER_TG = "➕ Добавить пользователя [TG]"
BTN_TRACKED_LIST = "📋 Список отслеживаемых [VK]"
BTN_TRACKED_LIST_TG = "📋 Список отслеживаемых [TG]"
BTN_ONLINE_REPORT = "📈 Отчет по онлайну"
BTN_GENERAL_REPORT = "📊 Общий отчет"
BTN_GENERAL_REPORT_VK = "📊 Общий отчет [VK]"
BTN_GENERAL_REPORT_TG = "📊 Общий отчет [TG]"
BTN_SEARCH = "🔎 Поиск по имени"
BTN_NOTIFY = "🔔 Настройки уведомлений"
BTN_NOTIFY_VK = "🔔 Настройки уведомлений [VK]"
BTN_NOTIFY_TG = "🔔 Настройки уведомлений [TG]"
BTN_PROFILE_CHANGES = "📝 Изменения профиля"
BTN_HELP = "❓ Помощь"

PERIOD_OPTIONS: list[tuple[str, int]] = [
    ("🗓️ 1 день", 1),
    ("🗓️ 7 дней", 7),
    ("🗓️ 30 дней", 30),
    ("🗂️ Все время", 0),
]

NOTIFICATION_OPTIONS: list[tuple[str, str]] = [
    ("🟢 Только вход в онлайн", "online"),
    ("🔴 Только выход из онлайна", "offline"),
    ("🔄 Вход и выход", "all"),
    ("🔕 Выключить уведомления", "off"),
]

CHANGE_NOTIFICATION_OPTIONS: list[tuple[str, str]] = [
    ("name", "Имя и фамилия"),
    ("avatar", "Аватарка"),
    ("status", "Статус профиля"),
    ("link", "Ссылка на профиль"),
    ("privacy", "Открыт / закрыт профиль"),
    ("fields", "Поля профиля"),
    ("posts", "Посты"),
    ("counts", "Счетчики"),
    ("relations", "Друзья / подписчики / подписки"),
]


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_PLATFORM_VK), KeyboardButton(text=BTN_PLATFORM_TG)],
            [KeyboardButton(text=BTN_GENERAL_REPORT), KeyboardButton(text=BTN_NOTIFY)],
            [KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="👇 Выберите раздел",
    )


def _strip_report_source(source: str) -> str:
    if source.startswith("r"):
        return source[1:]
    return source


def _source_back_nav_target(source: str) -> str:
    base_source = _strip_report_source(source)
    if base_source in {"srh", "csrh"}:
        return "search_results"
    if base_source in {"orp", "corp"}:
        return "report_users"
    return "list"


def _list_back_nav_target(source: str) -> str:
    if source == "srh":
        return "search_prompt"
    return "vk_menu"


def back_main_inline_keyboard(back_target: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад", callback_data=NavCallback(target=back_target).pack())
    builder.button(text="🏠 В главное меню", callback_data=NavCallback(target="main").pack())
    builder.adjust(2)
    return builder.as_markup()


def platform_section_keyboard(platform: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if platform == "vk":
        builder.button(text=BTN_ADD_USER, callback_data=NavCallback(target="vk_add").pack())
        builder.button(text=BTN_TRACKED_LIST, callback_data=NavCallback(target="vk_list").pack())
        builder.button(text=BTN_GENERAL_REPORT_VK, callback_data=NavCallback(target="general_report_vk_period").pack())
    else:
        builder.button(text=BTN_ADD_USER_TG, callback_data=NavCallback(target="tg_add").pack())
        builder.button(text=BTN_TRACKED_LIST_TG, callback_data=NavCallback(target="tg_list").pack())
        builder.button(text=BTN_GENERAL_REPORT_TG, callback_data=NavCallback(target="tg_general_report").pack())

    builder.adjust(1)
    builder.row(
        *[
            InlineKeyboardButton(text="⬅️ Назад", callback_data=NavCallback(target="main").pack()),
            InlineKeyboardButton(text="🏠 В главное меню", callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def reports_hub_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=BTN_GENERAL_REPORT_VK, callback_data=NavCallback(target="general_report_vk_period").pack())
    builder.button(text=BTN_GENERAL_REPORT_TG, callback_data=NavCallback(target="tg_general_report").pack())
    builder.adjust(1)
    builder.row(
        *[
            InlineKeyboardButton(text="⬅️ Назад", callback_data=NavCallback(target="main").pack()),
            InlineKeyboardButton(text="🏠 В главное меню", callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def notifications_hub_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=BTN_NOTIFY_VK, callback_data=NavCallback(target="notify_vk").pack())
    builder.button(text=BTN_NOTIFY_TG, callback_data=NavCallback(target="notify_tg").pack())
    builder.adjust(1)
    builder.row(
        *[
            InlineKeyboardButton(text="⬅️ Назад", callback_data=NavCallback(target="main").pack()),
            InlineKeyboardButton(text="🏠 В главное меню", callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def tracked_list_chunk_keyboard(vk_items: list[tuple[int, str]], source: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for vk_id, name in vk_items:
        builder.row(
            *[
                InlineKeyboardButton(
                    text=f"👤 {name[:30]}",
                    callback_data=UserActionCallback(action="card", vk_id=vk_id, src=source).pack(),
                ),
                InlineKeyboardButton(
                    text="📊 Отчет",
                    callback_data=UserActionCallback(action="report", vk_id=vk_id, src=source).pack(),
                ),
                InlineKeyboardButton(
                    text="🗑️ Удалить",
                    callback_data=UserActionCallback(action="delete", vk_id=vk_id, src=source).pack(),
                ),
            ]
        )

    builder.row(
        *[
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=NavCallback(target=_list_back_nav_target(source)).pack(),
            ),
            InlineKeyboardButton(
                text="🏠 В главное меню",
                callback_data=NavCallback(target="main").pack(),
            ),
        ]
    )
    return builder.as_markup()


def user_picker_keyboard(vk_items: list[tuple[int, str]], source: str, back_target: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for vk_id, name in vk_items:
        builder.button(
            text=f"👤 {name[:30]}",
            callback_data=UserActionCallback(action="period", vk_id=vk_id, src=source).pack(),
        )
    builder.adjust(2)
    builder.row(
        *[
            InlineKeyboardButton(text="⬅️ Назад", callback_data=NavCallback(target=back_target).pack()),
            InlineKeyboardButton(text="🏠 В главное меню", callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def report_period_keyboard(scope: str, vk_id: int, source: str, back_target: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, days in PERIOD_OPTIONS:
        builder.button(
            text=label,
            callback_data=PeriodSelectCallback(scope=scope, vk_id=vk_id, days=days, src=source).pack(),
        )
    builder.adjust(2)
    if source.startswith("r"):
        back_button = InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=UserActionCallback(action="report", vk_id=vk_id, src=source[1:]).pack(),
        )
    elif source.startswith("c"):
        back_button = InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=UserActionCallback(action="card", vk_id=vk_id, src=source).pack(),
        )
    else:
        back_button = InlineKeyboardButton(text="⬅️ Назад", callback_data=NavCallback(target=back_target).pack())
    builder.row(
        *[
            back_button,
            InlineKeyboardButton(text="🏠 В главное меню", callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def user_card_keyboard(vk_id: int, source: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📊 Отчет",
        callback_data=UserActionCallback(action="report", vk_id=vk_id, src=source).pack(),
    )
    builder.button(
        text="🗑️ Удалить",
        callback_data=UserActionCallback(action="delete", vk_id=vk_id, src=source).pack(),
    )
    builder.adjust(2)
    back_target = _source_back_nav_target(source)
    builder.row(
        *[
            InlineKeyboardButton(text="⬅️ Назад", callback_data=NavCallback(target=back_target).pack()),
            InlineKeyboardButton(text="🏠 В главное меню", callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def user_report_menu_keyboard(vk_id: int, source: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📝 Изменения профиля",
        callback_data=UserActionCallback(action="profile_changes", vk_id=vk_id, src=source).pack(),
    )
    builder.button(
        text="📈 Отчет по онлайну",
        callback_data=UserActionCallback(action="online_report", vk_id=vk_id, src=source).pack(),
    )
    builder.adjust(1)

    base_source = _strip_report_source(source)
    if base_source.startswith("c"):
        back_button = InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=UserActionCallback(action="card", vk_id=vk_id, src=base_source).pack(),
        )
    else:
        back_button = InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=NavCallback(target=_source_back_nav_target(base_source)).pack(),
        )

    builder.row(
        *[
            back_button,
            InlineKeyboardButton(text="🏠 В главное меню", callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def delete_confirm_keyboard(vk_id: int, source: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Да, удалить",
        callback_data=DeleteConfirmCallback(vk_id=vk_id, confirm=1, src=source).pack(),
    )
    builder.button(
        text="❌ Нет, отмена",
        callback_data=DeleteConfirmCallback(vk_id=vk_id, confirm=0, src=source).pack(),
    )
    builder.adjust(2)
    return builder.as_markup()


def report_result_keyboard(vk_id: int, source: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🗓️ Другой период",
        callback_data=UserActionCallback(action="period", vk_id=vk_id, src=source).pack(),
    )
    builder.button(
        text="👤 Карточка пользователя",
        callback_data=UserActionCallback(
            action="card",
            vk_id=vk_id,
            src=_strip_report_source(source) if _strip_report_source(source).startswith("c") else f"c{_strip_report_source(source)}",
        ).pack(),
    )
    builder.adjust(2)
    if source.startswith("r"):
        back_button = InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=UserActionCallback(action="report", vk_id=vk_id, src=source[1:]).pack(),
        )
    elif source.startswith("c"):
        back_button = InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=UserActionCallback(action="card", vk_id=vk_id, src=source).pack(),
        )
    else:
        back_button = InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=NavCallback(target=_source_back_nav_target(source)).pack(),
        )
    builder.row(
        *[
            back_button,
            InlineKeyboardButton(text="🏠 В главное меню", callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def general_report_result_keyboard() -> InlineKeyboardMarkup:
    return general_report_result_keyboard_with_target("general_report_vk_period")


def general_report_result_keyboard_with_target(back_target: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🗓️ Выбрать другой период", callback_data=NavCallback(target=back_target).pack())
    builder.button(text="🏠 В главное меню", callback_data=NavCallback(target="main").pack())
    builder.adjust(1)
    return builder.as_markup()


def notification_settings_keyboard(
    current_mode: str,
    change_settings: dict[str, bool],
    back_target: str = "main",
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, mode in NOTIFICATION_OPTIONS:
        prefix = "• " if mode == current_mode else ""
        builder.button(
            text=f"{prefix}{label}",
            callback_data=NotifyModeCallback(mode=mode).pack(),
        )
    builder.adjust(1)
    for key, label in CHANGE_NOTIFICATION_OPTIONS:
        enabled = bool(change_settings.get(key, True))
        status = "ВКЛ" if enabled else "ВЫКЛ"
        icon = "✅" if enabled else "🚫"
        builder.button(
            text=f"{icon} {label}: {status}",
            callback_data=NotifyToggleCallback(key=key).pack(),
        )
    builder.adjust(1)
    builder.row(
        *[
            InlineKeyboardButton(text="⬅️ Назад", callback_data=NavCallback(target=back_target).pack()),
            InlineKeyboardButton(text="🏠 В главное меню", callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def profile_change_user_keyboard(vk_items: list[tuple[int, str]], source: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for vk_id, name in vk_items:
        builder.button(
            text=f"👤 {name[:30]}",
            callback_data=ProfileChangeUserCallback(vk_id=vk_id, src=source).pack(),
        )
    builder.adjust(2)
    builder.row(
        *[
            InlineKeyboardButton(text="⬅️ Назад", callback_data=NavCallback(target="main").pack()),
            InlineKeyboardButton(text="🏠 В главное меню", callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def profile_change_type_keyboard(vk_id: int, items: list[tuple[str, str]], source: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, key in items:
        builder.button(
            text=label,
            callback_data=ProfileChangeTypeCallback(vk_id=vk_id, key=key, src=source).pack(),
        )
    builder.adjust(2)
    if source.startswith("r"):
        back_button = InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=UserActionCallback(action="report", vk_id=vk_id, src=source[1:]).pack(),
        )
    else:
        back_button = InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=NavCallback(target="profile_changes").pack(),
        )
    builder.row(
        *[
            back_button,
            InlineKeyboardButton(text="🏠 В главное меню", callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def profile_change_period_keyboard(vk_id: int, change_key: str, source: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, days in PERIOD_OPTIONS:
        builder.button(
            text=label,
            callback_data=ProfileChangePeriodCallback(vk_id=vk_id, key=change_key, days=days, src=source).pack(),
        )
    builder.adjust(2)
    builder.row(
        *[
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=ProfileChangeUserCallback(vk_id=vk_id, src=source).pack(),
            ),
            InlineKeyboardButton(text="🏠 В главное меню", callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def profile_change_result_keyboard(vk_id: int, change_key: str, source: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🗓️ Другой период",
        callback_data=ProfileChangeTypeCallback(vk_id=vk_id, key=change_key, src=source).pack(),
    )
    builder.button(
        text="🧩 Другой тип",
        callback_data=ProfileChangeUserCallback(vk_id=vk_id, src=source).pack(),
    )
    builder.adjust(2)
    if source.startswith("r"):
        back_button = InlineKeyboardButton(
            text="📊 К отчетам пользователя",
            callback_data=UserActionCallback(action="report", vk_id=vk_id, src=source[1:]).pack(),
        )
    else:
        back_button = InlineKeyboardButton(
            text="👥 Другой пользователь",
            callback_data=NavCallback(target="profile_changes").pack(),
        )
    builder.row(
        *[
            back_button,
            InlineKeyboardButton(text="🏠 В главное меню", callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()
