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
        "<b>Помощь</b>\n"
        "Бот помогает следить за активностью и изменениями профиля во ВКонтакте и Telegram.\n\n"
        "<b>Как начать</b>\n"
        f"• Откройте <b>{BTN_PLATFORM_VK}</b> или <b>{BTN_PLATFORM_TG}</b>\n"
        "• Добавьте пользователя\n"
        "• Откройте список и выберите нужного человека\n"
        "• В карточке можно открыть отчет или удалить пользователя\n\n"
        "<b>Отчеты и уведомления</b>\n"
        f"• <b>{BTN_GENERAL_REPORT}</b> — общие отчеты по платформе\n"
        f"• <b>{BTN_NOTIFY}</b> — настройки уведомлений\n"
        "• Данные ВКонтакте и Telegram не смешиваются\n\n"
        "<b>Команды</b>\n"
        "/start — открыть главное меню\n"
        "/help — показать помощь\n"
        "/add <code>ссылка</code> — добавить пользователя VK\n"
        "/status <code>ссылка</code> — открыть карточку VK\n"
        "/find <code>имя</code> — поиск по VK\n\n"
        f"Уведомления VK: <b>{NOTIFICATION_MODE_LABELS.get(current_mode, current_mode)}</b>\n"
        f"Включено по изменениям: <b>{escape_html(enabled_changes_text)}</b>\n"
        f"Выключено по изменениям: <b>{escape_html(disabled_changes_text)}</b>"
    )


async def _show_main_menu(message: Message, text: str | None = None) -> None:
    await message.answer(
        text
        or (
            "<b>Главное меню</b>\n"
            "Выберите раздел."
        ),
        reply_markup=main_menu_keyboard(),
    )


async def _show_vk_menu(message: Message) -> None:
    await message.answer(
        "<b>ВКонтакте</b>\n"
        "Выберите действие.",
        reply_markup=platform_section_keyboard("vk"),
    )


async def _show_tg_menu(message: Message) -> None:
    await message.answer(
        "<b>Telegram</b>\n"
        "Выберите действие.",
        reply_markup=platform_section_keyboard("tg"),
    )


async def _show_help(message: Message) -> None:
    current_mode = await db.get_notification_mode(message.chat.id)
    change_settings = await db.get_change_notification_settings(message.chat.id)
    await message.answer(_build_help_text(current_mode, change_settings), reply_markup=main_menu_keyboard())


async def _show_reports_hub(message: Message) -> None:
    await message.answer(
        "<b>Отчеты</b>\n"
        "Выберите платформу.",
        reply_markup=reports_hub_keyboard(),
    )


async def _show_notifications_hub(message: Message) -> None:
    await message.answer(
        "<b>Уведомления</b>\n"
        "Выберите платформу.",
        reply_markup=notifications_hub_keyboard(),
    )


# --- Handlers ---

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_main_menu(message, text="Привет! Я помогаю следить за активностью и изменениями профиля во ВКонтакте и Telegram.")


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
