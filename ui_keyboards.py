"""
Клавиатуры для основного кнопочного интерфейса.
"""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestUsers,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ui_callbacks import (
    DeleteConfirmCallback,
    NavCallback,
    NotifyModeCallback,
    NotifyToggleCallback,
    PageCallback,
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

BTN_PLATFORM_VK = "ВКонтакте"
BTN_PLATFORM_TG = "Telegram"
BTN_ADD_USER = "➕ Добавить"
BTN_ADD_USER_TG = "➕ Добавить"
BTN_TRACKED_LIST = "👥 Список"
BTN_TRACKED_LIST_TG = "👥 Список"
BTN_ONLINE_REPORT = "📈 Онлайн"
BTN_GENERAL_REPORT = "📊 Отчеты"
BTN_GENERAL_REPORT_VK = "ВКонтакте"
BTN_GENERAL_REPORT_TG = "Telegram"
BTN_PLATFORM_MENU_ADD_USER = "➕Добавить пользователя"
BTN_PLATFORM_MENU_TRACKED_LIST = "👁 Список отслеживаемых пользователей"
BTN_PLATFORM_MENU_REPORT = "📈Общий отчёт"
BTN_SEARCH = "🔎 Поиск"
BTN_NOTIFY = "🔔 Уведомления"
BTN_NOTIFY_VK = "ВКонтакте"
BTN_NOTIFY_TG = "Telegram"
BTN_PROFILE_CHANGES = "📝 Изменения профиля"
BTN_HELP = "Помощь"
BTN_TG_PICK_USER = "👤 Выбрать в Telegram"
BTN_BACK = "⬅️ Назад"
BTN_MAIN_MENU = "🏠Главное меню"

PERIOD_OPTIONS: list[tuple[str, int]] = [
    ("1 день", 1),
    ("7 дней", 7),
    ("30 дней", 30),
    ("Все время", 0),
]

NOTIFICATION_OPTIONS: list[tuple[str, str]] = [
    ("🟢 Только вход", "online"),
    ("🔴 Только выход", "offline"),
    ("🔄 Вход и выход", "all"),
    ("🔕 Выключить", "off"),
]

CHANGE_NOTIFICATION_OPTIONS: list[tuple[str, str]] = [
    ("name", "Имя и фамилия"),
    ("avatar", "Аватар"),
    ("status", "Статус"),
    ("link", "Ссылка"),
    ("privacy", "Приватность"),
    ("fields", "Данные профиля"),
    ("posts", "Посты"),
    ("counts", "Счетчики"),
    ("relations", "Друзья и подписки"),
]

TG_NOTIFICATION_TOGGLE_OPTIONS: list[tuple[str, str]] = [("activity", "Последняя активность")]

TG_CHANGE_NOTIFICATION_OPTIONS: list[tuple[str, str]] = [
    ("first_name", "Имя"),
    ("last_name", "Фамилия"),
    ("username", "Ник"),
    ("avatar", "Аватар"),
    ("gifts", "Подарки"),
    ("bio", "О себе"),
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
        input_field_placeholder="Выберите раздел",
    )


def _strip_report_source(source: str) -> str:
    if source.startswith("r"):
        return source[1:]
    return source


def _normalize_nav_source(source: str) -> str:
    normalized = _strip_report_source(source)
    if normalized.startswith("c"):
        return normalized[1:]
    return normalized


def _source_back_nav_target(source: str) -> str:
    base_source = _normalize_nav_source(source)
    if base_source == "srh":
        return "search_results"
    if base_source == "orp":
        return "report_users"
    if base_source == "vk_list":
        return "vk_list"
    if base_source == "tg_list":
        return "tg_list"
    if base_source == "cmd":
        return "vk_menu"
    return "main"


def _list_back_nav_target(source: str) -> str:
    base_source = _normalize_nav_source(source)
    if base_source == "srh":
        return "search_prompt"
    if base_source == "tg_list":
        return "tg_menu"
    return "vk_menu"


def back_main_inline_keyboard(back_target: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад", callback_data=NavCallback(target=back_target).pack())
    builder.button(text=BTN_MAIN_MENU, callback_data=NavCallback(target="main").pack())
    builder.adjust(2)
    return builder.as_markup()


def platform_section_keyboard(platform: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if platform == "vk":
        builder.button(text=BTN_PLATFORM_MENU_ADD_USER, callback_data=NavCallback(target="vk_add").pack())
        builder.button(text=BTN_PLATFORM_MENU_TRACKED_LIST, callback_data=NavCallback(target="vk_list").pack())
        builder.button(text=BTN_PLATFORM_MENU_REPORT, callback_data=NavCallback(target="general_report_vk_period").pack())
    else:
        builder.button(text=BTN_PLATFORM_MENU_ADD_USER, callback_data=NavCallback(target="tg_add").pack())
        builder.button(text=BTN_PLATFORM_MENU_TRACKED_LIST, callback_data=NavCallback(target="tg_list").pack())
        builder.button(text=BTN_PLATFORM_MENU_REPORT, callback_data=NavCallback(target="tg_general_report").pack())

    builder.adjust(1)
    builder.row(
        *[
            InlineKeyboardButton(text="⬅️ Назад", callback_data=NavCallback(target="main").pack()),
            InlineKeyboardButton(text=BTN_MAIN_MENU, callback_data=NavCallback(target="main").pack()),
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
            InlineKeyboardButton(text=BTN_MAIN_MENU, callback_data=NavCallback(target="main").pack()),
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
            InlineKeyboardButton(text=BTN_MAIN_MENU, callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def tg_add_user_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_BACK), KeyboardButton(text=BTN_MAIN_MENU)],
        ],
        resize_keyboard=True,
        is_persistent=False,
        input_field_placeholder="Введите @username, ссылку или ID",
    )


def _add_pagination_row(builder: InlineKeyboardBuilder, page: int, total_pages: int, source: str) -> None:
    if total_pages <= 1:
        return
    
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(
            text="⬅️", 
            callback_data=PageCallback(page=page - 1, source=source).pack()
        ))

    nav_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(
            text="➡️", 
            callback_data=PageCallback(page=page + 1, source=source).pack()
        ))
    
    builder.row(*nav_row)


def tracked_list_paginated_keyboard(
    vk_items: list[tuple[int, str]], 
    page: int, 
    total_pages: int, 
    source: str
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for vk_id, name in vk_items:
        builder.row(
            *[
                InlineKeyboardButton(
                    text=f"👤 {name[:25]}",
                    callback_data=UserActionCallback(action="card", vk_id=vk_id, src=source).pack(),
                ),
                InlineKeyboardButton(
                    text="📊 Отчет",
                    callback_data=UserActionCallback(action="report", vk_id=vk_id, src=source).pack(),
                ),
                InlineKeyboardButton(
                    text="🗑️",
                    callback_data=UserActionCallback(action="delete", vk_id=vk_id, src=source).pack(),
                ),
            ]
        )

    _add_pagination_row(builder, page, total_pages, source)

    builder.row(
        *[
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=NavCallback(target=_list_back_nav_target(source)).pack(),
            ),
            InlineKeyboardButton(
                text=BTN_MAIN_MENU,
                callback_data=NavCallback(target="main").pack(),
            ),
        ]
    )
    return builder.as_markup()


def tracked_list_chunk_keyboard(vk_items: list[tuple[int, str]], source: str) -> InlineKeyboardMarkup:
    # Оставляем для обратной совместимости во время рефакторинга
    return tracked_list_paginated_keyboard(vk_items, 1, 1, source)


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
            InlineKeyboardButton(text=BTN_MAIN_MENU, callback_data=NavCallback(target="main").pack()),
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
            InlineKeyboardButton(text=BTN_MAIN_MENU, callback_data=NavCallback(target="main").pack()),
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
            InlineKeyboardButton(text=BTN_MAIN_MENU, callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def user_report_menu_keyboard(vk_id: int, source: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📝 Изменения",
        callback_data=UserActionCallback(action="profile_changes", vk_id=vk_id, src=source).pack(),
    )
    builder.button(
        text="📈 Онлайн",
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
            InlineKeyboardButton(text=BTN_MAIN_MENU, callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def delete_confirm_keyboard(vk_id: int, source: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Да, удалить",
        callback_data=DeleteConfirmCallback(vk_id=vk_id, confirm=1, src=source).pack(),
    )
    builder.button(
        text="Отмена",
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
        text="👤 Карточка",
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
            InlineKeyboardButton(text=BTN_MAIN_MENU, callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def general_report_result_keyboard() -> InlineKeyboardMarkup:
    return general_report_result_keyboard_with_target("general_report_vk_period")


def general_report_result_keyboard_with_target(back_target: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Другой период", callback_data=NavCallback(target=back_target).pack())
    builder.button(text=BTN_MAIN_MENU, callback_data=NavCallback(target="main").pack())
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
            InlineKeyboardButton(text=BTN_MAIN_MENU, callback_data=NavCallback(target="main").pack()),
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
            InlineKeyboardButton(text=BTN_MAIN_MENU, callback_data=NavCallback(target="main").pack()),
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
    back_source = source[1:] if source.startswith("r") else source
    back_button = InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data=UserActionCallback(action="report", vk_id=vk_id, src=back_source).pack(),
    )
    builder.row(
        *[
            back_button,
            InlineKeyboardButton(text=BTN_MAIN_MENU, callback_data=NavCallback(target="main").pack()),
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
            InlineKeyboardButton(text=BTN_MAIN_MENU, callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def profile_change_result_keyboard(vk_id: int, change_key: str, source: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Другой период",
        callback_data=ProfileChangeTypeCallback(vk_id=vk_id, key=change_key, src=source).pack(),
    )
    builder.button(
        text="Другой тип",
        callback_data=ProfileChangeUserCallback(vk_id=vk_id, src=source).pack(),
    )
    builder.adjust(2)
    if source.startswith("r"):
        back_button = InlineKeyboardButton(
            text="К отчетам",
            callback_data=UserActionCallback(action="report", vk_id=vk_id, src=source[1:]).pack(),
        )
    else:
        back_button = InlineKeyboardButton(
            text="К отчетам",
            callback_data=UserActionCallback(action="report", vk_id=vk_id, src=source).pack(),
        )
    builder.row(
        *[
            back_button,
            InlineKeyboardButton(text=BTN_MAIN_MENU, callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def tg_tracked_list_paginated_keyboard(
    items: list[dict], 
    page: int, 
    total_pages: int, 
    source: str = "tg_list"
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in items:
        tg_id = int(item["telegram_user_id"])
        display_name = str(item.get("button_label") or item.get("display_name") or f"ID {tg_id}")
        builder.row(
            *[
                InlineKeyboardButton(
                    text=f"👤 {display_name[:25]}",
                    callback_data=TgUserActionCallback(action="card", tg_id=tg_id, src=source).pack(),
                ),
                InlineKeyboardButton(
                    text="📊 Отчет",
                    callback_data=TgUserActionCallback(action="report", tg_id=tg_id, src=source).pack(),
                ),
                InlineKeyboardButton(
                    text="🗑️",
                    callback_data=TgUserActionCallback(action="delete", tg_id=tg_id, src=source).pack(),
                ),
            ]
        )

    _add_pagination_row(builder, page, total_pages, source)

    builder.row(
        *[
            InlineKeyboardButton(text="⬅️ Назад", callback_data=NavCallback(target="tg_menu").pack()),
            InlineKeyboardButton(text=BTN_MAIN_MENU, callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def tg_tracked_list_chunk_keyboard(items: list[dict], source: str = "tg_list") -> InlineKeyboardMarkup:
    # Оставляем для обратной совместимости
    return tg_tracked_list_paginated_keyboard(items, 1, 1, source)


def tg_user_card_keyboard(tg_id: int, source: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📊 Отчет",
        callback_data=TgUserActionCallback(action="report", tg_id=tg_id, src=source).pack(),
    )
    builder.button(
        text="🗑️ Удалить",
        callback_data=TgUserActionCallback(action="delete", tg_id=tg_id, src=source).pack(),
    )
    builder.adjust(2)
    builder.row(
        *[
            InlineKeyboardButton(text="⬅️ Назад", callback_data=NavCallback(target="tg_list").pack()),
            InlineKeyboardButton(text=BTN_MAIN_MENU, callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def tg_user_report_menu_keyboard(tg_id: int, source: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📈 Онлайн",
        callback_data=TgUserActionCallback(action="online_report", tg_id=tg_id, src=source).pack(),
    )
    builder.button(
        text="📝 Изменения",
        callback_data=TgUserActionCallback(action="profile_changes", tg_id=tg_id, src=source).pack(),
    )
    builder.adjust(1)

    base_source = _strip_report_source(source)
    if base_source.startswith("c"):
        back_button = InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=TgUserActionCallback(action="card", tg_id=tg_id, src=base_source).pack(),
        )
    else:
        back_button = InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=NavCallback(target="tg_list").pack(),
        )

    builder.row(
        *[
            back_button,
            InlineKeyboardButton(text=BTN_MAIN_MENU, callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def tg_delete_confirm_keyboard(tg_id: int, source: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Да, удалить",
        callback_data=TgDeleteConfirmCallback(tg_id=tg_id, confirm=1, src=source).pack(),
    )
    builder.button(
        text="Отмена",
        callback_data=TgDeleteConfirmCallback(tg_id=tg_id, confirm=0, src=source).pack(),
    )
    builder.adjust(1)
    return builder.as_markup()


def tg_report_period_keyboard(
    scope: str,
    tg_id: int,
    source: str,
    back_target: str,
    *,
    back_to_card: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, days in PERIOD_OPTIONS:
        builder.button(
            text=label,
            callback_data=TgPeriodSelectCallback(scope=scope, tg_id=tg_id, days=days, src=source).pack(),
        )
    builder.adjust(2)

    if source.startswith("r"):
        back_button = InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=TgUserActionCallback(action="report", tg_id=tg_id, src=source[1:]).pack(),
        )
    elif back_to_card or source.startswith("c"):
        back_button = InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=TgUserActionCallback(action="card", tg_id=tg_id, src=source).pack(),
        )
    else:
        back_button = InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=NavCallback(target=back_target).pack(),
        )

    builder.row(
        *[
            back_button,
            InlineKeyboardButton(text=BTN_MAIN_MENU, callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def tg_report_result_keyboard(tg_id: int, source: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Другой период",
        callback_data=TgUserActionCallback(action="online_report", tg_id=tg_id, src=source).pack(),
    )
    builder.button(
        text="👤 Карточка",
        callback_data=TgUserActionCallback(action="card", tg_id=tg_id, src=source).pack(),
    )
    builder.adjust(1)
    if source.startswith("r"):
        back_button = InlineKeyboardButton(
            text="К отчетам",
            callback_data=TgUserActionCallback(action="report", tg_id=tg_id, src=source[1:]).pack(),
        )
    elif source.startswith("c"):
        back_button = InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=TgUserActionCallback(action="card", tg_id=tg_id, src=source).pack(),
        )
    else:
        back_button = InlineKeyboardButton(
            text="К отчетам",
            callback_data=TgUserActionCallback(action="report", tg_id=tg_id, src=source).pack(),
        )
    builder.row(
        *[
            back_button,
            InlineKeyboardButton(text=BTN_MAIN_MENU, callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def tg_notification_settings_keyboard(
    current_mode: str,
    activity_enabled: bool,
    change_settings: dict[str, bool],
    back_target: str = "notification_hub",
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, mode in NOTIFICATION_OPTIONS:
        prefix = "• " if mode == current_mode else ""
        builder.button(
            text=f"{prefix}{label}",
            callback_data=TgNotifyModeCallback(mode=mode).pack(),
        )
    builder.adjust(1)

    for key, label in TG_NOTIFICATION_TOGGLE_OPTIONS:
        icon = "✅" if activity_enabled else "🚫"
        status = "ВКЛ" if activity_enabled else "ВЫКЛ"
        builder.button(
            text=f"{icon} {label}: {status}",
            callback_data=TgNotifyToggleCallback(key=key).pack(),
        )
    builder.adjust(1)
    for key, label in TG_CHANGE_NOTIFICATION_OPTIONS:
        enabled = bool(change_settings.get(key, True))
        status = "ВКЛ" if enabled else "ВЫКЛ"
        icon = "✅" if enabled else "🚫"
        builder.button(
            text=f"{icon} {label}: {status}",
            callback_data=TgNotifyToggleCallback(key=key).pack(),
        )
    builder.adjust(1)
    builder.row(
        *[
            InlineKeyboardButton(text="⬅️ Назад", callback_data=NavCallback(target=back_target).pack()),
            InlineKeyboardButton(text=BTN_MAIN_MENU, callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def tg_profile_change_type_keyboard(
    tg_id: int,
    items: list[tuple[str, str]],
    source: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, key in items:
        builder.button(
            text=label,
            callback_data=TgProfileChangeTypeCallback(tg_id=tg_id, key=key, src=source).pack(),
        )
    builder.adjust(2)
    if source.startswith("r"):
        back_button = InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=TgUserActionCallback(action="report", tg_id=tg_id, src=source[1:]).pack(),
        )
    elif source.startswith("c"):
        back_button = InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=TgUserActionCallback(action="card", tg_id=tg_id, src=source).pack(),
        )
    else:
        back_button = InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=TgUserActionCallback(action="report", tg_id=tg_id, src=source).pack(),
        )
    builder.row(
        *[
            back_button,
            InlineKeyboardButton(text=BTN_MAIN_MENU, callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def tg_profile_change_period_keyboard(tg_id: int, change_key: str, source: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, days in PERIOD_OPTIONS:
        builder.button(
            text=label,
            callback_data=TgProfileChangePeriodCallback(tg_id=tg_id, key=change_key, days=days, src=source).pack(),
        )
    builder.adjust(2)
    builder.row(
        *[
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=TgUserActionCallback(action="profile_changes", tg_id=tg_id, src=source).pack(),
            ),
            InlineKeyboardButton(text=BTN_MAIN_MENU, callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()


def tg_profile_change_result_keyboard(tg_id: int, change_key: str, source: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="К периоду",
        callback_data=TgProfileChangeTypeCallback(tg_id=tg_id, key=change_key, src=source).pack(),
    )
    builder.button(
        text="Другой тип",
        callback_data=TgUserActionCallback(action="profile_changes", tg_id=tg_id, src=source).pack(),
    )
    builder.adjust(1)
    if source.startswith("r"):
        back_button = InlineKeyboardButton(
            text="К отчетам",
            callback_data=TgUserActionCallback(action="report", tg_id=tg_id, src=source[1:]).pack(),
        )
    elif source.startswith("c"):
        back_button = InlineKeyboardButton(
            text="👤 Карточка",
            callback_data=TgUserActionCallback(action="card", tg_id=tg_id, src=source).pack(),
        )
    else:
        back_button = InlineKeyboardButton(
            text="К отчетам",
            callback_data=TgUserActionCallback(action="report", tg_id=tg_id, src=source).pack(),
        )
    builder.row(
        *[
            back_button,
            InlineKeyboardButton(text=BTN_MAIN_MENU, callback_data=NavCallback(target="main").pack()),
        ]
    )
    return builder.as_markup()
