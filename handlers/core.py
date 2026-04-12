import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import db
from ui_keyboards import (
    main_menu_keyboard,
    platform_section_keyboard,
    reports_hub_keyboard,
    notifications_hub_keyboard,
    BTN_PLATFORM_VK,
    BTN_PLATFORM_TG,
    BTN_GENERAL_REPORT,
    BTN_NOTIFY,
    BTN_HELP,
    BTN_GENERAL_REPORT_VK,
    BTN_GENERAL_REPORT_TG,
    BTN_NOTIFY_VK,
    BTN_NOTIFY_TG,
    CHANGE_NOTIFICATION_OPTIONS
)
from ui_callbacks import NavCallback
from ui_format import NOTIFICATION_MODE_LABELS, escape_html

logger = logging.getLogger(__name__)

router = Router()

# --- Helpers ---

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
        "• персональные отчеты VK и TG не смешиваются между собой\n\n"
        "<b>Как работают уведомления:</b>\n"
        f"• в разделе <b>{BTN_NOTIFY_VK}</b> можно настроить уведомления о входе в онлайн, выходе из онлайна и изменениях профиля VK\n"
        f"• в разделе <b>{BTN_NOTIFY_TG}</b> можно настроить уведомления о входе в онлайн, выходе из онлайна, activity / last seen и изменениях профиля Telegram\n\n"
        "<b>⌨️ Резервные команды:</b>\n"
        "/start — 🏠 открыть главное меню\n"
        "/help — ❓ подробная справка\n"
        "/add <code>ССЫЛКА</code> — ➕ добавить пользователя вручную\n"
        "/status <code>ССЫЛКА</code> — 👤 показать карточку конкретного пользователя\n"
        "/find <code>ИМЯ</code> — 🔎 поиск среди отслеживаемых\n\n"
        f"🔔 Текущий режим VK онлайн-уведомлений: <b>{NOTIFICATION_MODE_LABELS.get(current_mode, current_mode)}</b>\n"
        f"✅ Включены VK-уведомления по изменениям: <b>{escape_html(enabled_changes_text)}</b>\n"
        f"🚫 Отключены VK-уведомления по изменениям: <b>{escape_html(disabled_changes_text)}</b>"
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


async def _show_vk_menu(message: Message) -> None:
    await message.answer(
        "🟦 <b>Раздел ВКонтакте [VK]</b>\n"
        "Все действия в этом меню относятся только к VK-данным и VK-отчетам.",
        reply_markup=platform_section_keyboard("vk"),
    )


async def _show_tg_menu(message: Message) -> None:
    await message.answer(
        "⬜ <b>Раздел Telegram [TG]</b>\n"
        "Структура этого меню зеркальна VK-разделу. Здесь уже подключены базовые статусы, online-сессии, отчеты и уведомления без смешивания с VK.",
        reply_markup=platform_section_keyboard("tg"),
    )


async def _show_help(message: Message) -> None:
    current_mode = await db.get_notification_mode(message.chat.id)
    change_settings = await db.get_change_notification_settings(message.chat.id)
    await message.answer(_build_help_text(current_mode, change_settings), reply_markup=main_menu_keyboard())


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


# --- Handlers ---

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_main_menu(message, text="👋 Добро пожаловать! Я бот для отслеживания онлайна и изменений профиля [VK] и [TG].")


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext) -> None:
    await _show_help(message)


@router.message(F.text == BTN_PLATFORM_VK)
async def menu_vk(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_vk_menu(message)


@router.message(F.text == BTN_PLATFORM_TG)
async def menu_tg(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_tg_menu(message)


@router.message(F.text == BTN_GENERAL_REPORT)
async def menu_reports(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_reports_hub(message)


@router.message(F.text == BTN_NOTIFY)
async def menu_notify(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_notifications_hub(message)


@router.message(F.text == BTN_HELP)
async def menu_help(message: Message) -> None:
    await _show_help(message)


# Navigation Callback Router - Narrowed to core targets only
@router.callback_query(NavCallback.filter(F.target.in_({"main", "vk_menu", "tg_menu", "general_reports_hub", "notification_hub", "help"})))
async def cb_nav(callback: CallbackQuery, callback_data: NavCallback, state: FSMContext) -> None:
    target = callback_data.target
    if target == "main":
        await state.clear()
        await _show_main_menu(callback.message)
    elif target == "vk_menu":
        await state.clear()
        await _show_vk_menu(callback.message)
    elif target == "tg_menu":
        await state.clear()
        await _show_tg_menu(callback.message)
    elif target == "general_reports_hub":
        await state.clear()
        await _show_reports_hub(callback.message)
    elif target == "notification_hub":
        await state.clear()
        await _show_notifications_hub(callback.message)
    elif target == "help":
        await state.clear()
        await _show_help(callback.message)
    # Остальные цели (vk_add, vk_list, и т.д.) будут перехвачены в своих модулях
    else:
        # should not happen with the narrowed filter, but for safety:
        return

    await callback.answer()
