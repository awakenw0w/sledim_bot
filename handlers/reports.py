import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import db
import vk_api
from ui_keyboards import (
    user_picker_keyboard,
    report_period_keyboard,
    report_result_keyboard,
    tg_report_period_keyboard,
    tg_report_result_keyboard,
    general_report_result_keyboard_with_target,
    main_menu_keyboard
)
from ui_callbacks import (
    NavCallback,
    UserActionCallback,
    PeriodSelectCallback,
    TgUserActionCallback,
    TgPeriodSelectCallback,
    ProfileChangeUserCallback,
    ProfileChangeTypeCallback,
    ProfileChangePeriodCallback,
    TgProfileChangeTypeCallback,
    TgProfileChangePeriodCallback
)
from ui_format import (
    MSK,
    escape_html,
    format_vk_period_report,
    format_vk_general_report_header,
    format_vk_general_report_user_block,
    format_tg_period_report,
    format_tg_general_report_header,
    format_tg_general_report_user_block,
    format_added_at,
    build_tg_display_name,
    build_tg_status_label,
    build_tg_activity_line,
    period_to_since_ts,
    PROFILE_CHANGE_FILTERS,
    TG_PROFILE_CHANGE_FILTERS,
    PROFILE_CHANGE_TYPE_ITEMS,
    TG_PROFILE_CHANGE_TYPE_ITEMS,
    build_profile_change_block,
    build_tg_profile_change_block,
    format_period_label
)

logger = logging.getLogger(__name__)

router = Router()

# --- Common Helpers ---

async def _send_long_html(message: Message, blocks: list[str]) -> None:
    if not blocks:
        return

    current = ""
    for block in blocks:
        next_part = block if not current else f"{current}\n\n{block}"
        if len(next_part) > 3800:
            if current:
                await message.answer(current, disable_web_page_preview=True)
            current = block
        else:
            current = next_part

    if current:
        await message.answer(current, disable_web_page_preview=True)


# --- VK Reports ---

async def _show_vk_online_report_user_picker(callback: CallbackQuery) -> None:
    details = await db.get_tracked_users_details(callback.message.chat.id, active_only=True)
    if not details:
        await callback.message.answer("📈 Список отслеживаемых [VK] пуст.", reply_markup=main_menu_keyboard())
        return

    items = [(int(item["vk_id"]), f"{item.get('first_name', '')} {item.get('last_name', '')}".strip() or f"ID {item['vk_id']}") for item in details]
    await callback.message.answer(
        "📈 Выберите пользователя для отчета по онлайну [VK].",
        reply_markup=user_picker_keyboard(items, source="orp", back_target="vk_menu")
    )


async def _show_vk_general_report_period_picker(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "📊 Выберите период для общего отчета [VK].",
        reply_markup=report_period_keyboard(scope="all", vk_id=0, source="all", back_target="general_reports_hub")
    )


# --- TG Reports ---

async def _show_tg_general_report_period_picker(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "📊 <b>Общий отчет [TG]</b>\nВыберите период.",
        reply_markup=tg_report_period_keyboard(
            scope="all",
            tg_id=0,
            source="tg_general",
            back_target="general_reports_hub",
            back_to_card=False
        )
    )


# --- Handlers ---

@router.callback_query(NavCallback.filter(F.target == "general_report_vk_period"))
async def cb_nav_vk_gen_report_period(callback: CallbackQuery) -> None:
    await _show_vk_general_report_period_picker(callback)
    await callback.message.delete()
    await callback.answer()


@router.callback_query(NavCallback.filter(F.target == "tg_general_report"))
async def cb_nav_tg_gen_report_period(callback: CallbackQuery) -> None:
    await _show_tg_general_report_period_picker(callback)
    await callback.message.delete()
    await callback.answer()


@router.callback_query(UserActionCallback.filter(F.action == "report"))
async def cb_vk_report_menu(callback: CallbackQuery, callback_data: UserActionCallback) -> None:
    # Здесь можно добавить меню выбора (сессии vs изменения), 
    # но пока по умолчанию ведем на выбор периода для онлайна
    await callback.message.answer(
        "🗓️ Выберите период для отчета по онлайну [VK].",
        reply_markup=report_period_keyboard(
            scope="user",
            vk_id=callback_data.vk_id,
            source=callback_data.src,
            back_target="vk_list"
        )
    )
    await callback.answer()


@router.callback_query(PeriodSelectCallback.filter())
async def cb_vk_period_perform(callback: CallbackQuery, callback_data: PeriodSelectCallback) -> None:
    chat_id = callback.message.chat.id
    now_ts = int(datetime.now(tz=MSK).timestamp())
    since_ts = period_to_since_ts(callback_data.days)

    if callback_data.scope == "all":
        # Общий отчет
        details = await db.get_tracked_users_details(chat_id, active_only=True)
        if not details:
             await callback.message.answer("Список пуст.")
             return
        
        blocks = [format_vk_general_report_header(callback_data.days)]
        for item in details:
            vk_id = int(item["vk_id"])
            sessions = await db.get_online_sessions_for_period(chat_id, vk_id, since_ts=since_ts)
            # Имитируем snapshot
            snapshot = {
                "vk_id": vk_id,
                "first_name": item.get("first_name"),
                "last_name": item.get("last_name"),
                "profile_link": vk_api.build_profile_link(vk_id, item.get("domain")),
                "online": item.get("online"),
                "last_seen": item.get("last_seen"),
            }
            blocks.append(format_vk_general_report_user_block(snapshot, sessions, callback_data.days, now_ts))
        
        await _send_long_html(callback.message, blocks)
        await callback.message.answer("📊 Отчет завершен.", reply_markup=general_report_result_keyboard_with_target("general_report_vk_period"))

    else:
        # Персональный отчет
        detail = await db.get_tracked_user_detail(chat_id, callback_data.vk_id)
        if not detail:
            await callback.message.answer("Пользователь не найден.")
            return
        
        sessions = await db.get_online_sessions_for_period(chat_id, callback_data.vk_id, since_ts=since_ts)
        snapshot = {
            "vk_id": callback_data.vk_id,
            "first_name": detail.get("first_name"),
            "last_name": detail.get("last_name"),
            "profile_link": vk_api.build_profile_link(callback_data.vk_id, detail.get("domain")),
            "online": detail.get("online"),
            "last_seen": detail.get("last_seen"),
            "added_at": detail.get("added_at"),
        }
        text = format_vk_period_report(snapshot, sessions, callback_data.days, now_ts)
        # Если текст слишком длинный (много сессий), разбиваем? 
        # format_vk_period_report возвращает единую строку.
        # Для безопасности можно обернуть в long_html
        await _send_long_html(callback.message, [text])
        await callback.message.answer("📊 Отчет завершен.", reply_markup=report_result_keyboard(callback_data.vk_id, callback_data.src))

    await callback.answer()


@router.callback_query(TgUserActionCallback.filter(F.action == "online_report"))
async def cb_tg_online_report_period(callback: CallbackQuery, callback_data: TgUserActionCallback) -> None:
    await callback.message.answer(
        "🗓️ Выберите период для отчета по онлайну [TG].",
        reply_markup=tg_report_period_keyboard(
            scope="one",
            tg_id=callback_data.tg_id,
            source=callback_data.src,
            back_target="tg_list",
            back_to_card=True
        )
    )
    await callback.answer()


@router.callback_query(TgPeriodSelectCallback.filter())
async def cb_tg_period_perform(callback: CallbackQuery, callback_data: TgPeriodSelectCallback) -> None:
    chat_id = callback.message.chat.id
    now_ts = int(datetime.now(tz=MSK).timestamp())
    since_ts = period_to_since_ts(callback_data.days)

    if callback_data.scope == "all":
        # Общий отчет TG
        details = await db.get_tg_tracked_users_details(chat_id)
        if not details:
            await callback.message.answer("Список TG пуст.")
            return

        blocks = [format_tg_general_report_header(callback_data.days)]
        for detail in details:
            sessions = await db.get_tg_online_sessions_for_period(chat_id, int(detail["telegram_user_id"]), since_ts=since_ts)
            blocks.append(format_tg_general_report_user_block(detail, sessions, callback_data.days, now_ts))
        
        await _send_long_html(callback.message, blocks)
        await callback.message.answer("📊 Общий отчет [TG] завершен.", reply_markup=general_report_result_keyboard_with_target("tg_general_report"))

    else:
        # Персональный отчет TG
        detail = await db.get_tg_tracked_user_detail(chat_id, callback_data.tg_id)
        if not detail:
            await callback.message.answer("TG пользователь не найден.")
            return
        
        sessions = await db.get_tg_online_sessions_for_period(chat_id, callback_data.tg_id, since_ts=since_ts)
        text = format_tg_period_report(detail, sessions, callback_data.days, now_ts)
        await _send_long_html(callback.message, [text])
        await callback.message.answer("📊 Отчет [TG] завершен.", reply_markup=tg_report_result_keyboard(callback_data.tg_id, callback_data.src))

    await callback.answer()


# --- Profile Changes Reports VK ---

@router.callback_query(UserActionCallback.filter(F.action == "profile_changes"))
async def cb_vk_profile_changes_picker(callback: CallbackQuery, callback_data: UserActionCallback) -> None:
    from ui_keyboards import profile_change_type_keyboard
    detail = await db.get_tracked_user_detail(callback.message.chat.id, callback_data.vk_id)
    name = f"{detail.get('first_name', '')} {detail.get('last_name', '')}".strip() or f"ID {callback_data.vk_id}"
    
    await callback.message.answer(
        f"🧩 Выберите тип изменений для <b>{escape_html(name)}</b>.",
        reply_markup=profile_change_type_keyboard(callback_data.vk_id, PROFILE_CHANGE_TYPE_ITEMS, callback_data.src),
    )
    await callback.answer()


@router.callback_query(ProfileChangeUserCallback.filter())
async def cb_vk_profile_change_user(callback: CallbackQuery, callback_data: ProfileChangeUserCallback) -> None:
    from ui_keyboards import profile_change_type_keyboard
    await callback.message.answer(
        f"🧩 Выберите тип изменений.",
        reply_markup=profile_change_type_keyboard(callback_data.vk_id, PROFILE_CHANGE_TYPE_ITEMS, callback_data.src),
    )
    await callback.answer()


@router.callback_query(ProfileChangeTypeCallback.filter())
async def cb_vk_profile_change_type(callback: CallbackQuery, callback_data: ProfileChangeTypeCallback) -> None:
    from ui_keyboards import profile_change_period_keyboard
    meta = PROFILE_CHANGE_FILTERS.get(callback_data.key, PROFILE_CHANGE_FILTERS["all"])
    await callback.message.answer(
        f"🗓️ Выберите период для отчета: <b>{escape_html(str(meta['label']))}</b>.",
        reply_markup=profile_change_period_keyboard(callback_data.vk_id, callback_data.key, callback_data.src),
    )
    await callback.answer()


@router.callback_query(ProfileChangePeriodCallback.filter())
async def cb_vk_profile_change_perform(callback: CallbackQuery, callback_data: ProfileChangePeriodCallback) -> None:
    meta = PROFILE_CHANGE_FILTERS.get(callback_data.key, PROFILE_CHANGE_FILTERS["all"])
    change_label = str(meta["label"])
    
    since_ts = period_to_since_ts(callback_data.days)
    field_names = meta.get("fields")
    
    changes = await db.get_profile_changes_for_report(
        chat_id=callback.message.chat.id,
        vk_id=callback_data.vk_id,
        field_names=list(field_names) if isinstance(field_names, list) else None,
        since_ts=since_ts,
        limit=300,
    )

    detail = await db.get_tracked_user_detail(callback.message.chat.id, callback_data.vk_id)
    name = f"{detail.get('first_name', '')} {detail.get('last_name', '')}".strip() or f"ID {callback_data.vk_id}"
    
    header = "\n".join([
        "<b>📝 Отчет по изменениям профиля [VK]</b>",
        f"👤 <b>{escape_html(name)}</b>",
        f"Тип: <b>{escape_html(change_label)}</b>",
        f"Период: <b>{escape_html(format_period_label(callback_data.days))}</b>",
    ])

    from ui_keyboards import profile_change_result_keyboard
    if not changes:
        await callback.message.answer(
            f"{header}\n\n🔍 Изменения за выбранный период не найдены.",
            reply_markup=profile_change_result_keyboard(callback_data.vk_id, callback_data.key, callback_data.src)
        )
    else:
        blocks = [header]
        for c in changes:
            blocks.append(build_profile_change_block(c))
        await _send_long_html(callback.message, blocks)
        await callback.message.answer("📝 Отчет завершен.", reply_markup=profile_change_result_keyboard(callback_data.vk_id, callback_data.key, callback_data.src))
    
    await callback.answer()


# --- Profile Changes Reports TG ---

@router.callback_query(TgUserActionCallback.filter(F.action == "profile_changes"))
async def cb_tg_profile_changes_picker(callback: CallbackQuery, callback_data: TgUserActionCallback) -> None:
    detail = await db.get_tg_tracked_user_detail(callback.message.chat.id, callback_data.tg_id)
    name = build_tg_display_name(detail)
    
    from ui_keyboards import tg_profile_change_type_keyboard
    await callback.message.answer(
        f"🧩 Выберите тип изменений профиля [TG] для <b>{escape_html(name)}</b>.",
        reply_markup=tg_profile_change_type_keyboard(callback_data.tg_id, TG_PROFILE_CHANGE_TYPE_ITEMS, callback_data.src),
    )
    await callback.answer()


@router.callback_query(TgProfileChangeTypeCallback.filter())
async def cb_tg_profile_change_type(callback: CallbackQuery, callback_data: TgProfileChangeTypeCallback) -> None:
    from ui_keyboards import tg_profile_change_period_keyboard
    meta = TG_PROFILE_CHANGE_FILTERS.get(callback_data.key, TG_PROFILE_CHANGE_FILTERS["all"])
    await callback.message.answer(
        f"🗓️ Выберите период для отчета [TG]: <b>{escape_html(str(meta['label']))}</b>.",
        reply_markup=tg_profile_change_period_keyboard(callback_data.tg_id, callback_data.key, callback_data.src),
    )
    await callback.answer()


@router.callback_query(TgProfileChangePeriodCallback.filter())
async def cb_tg_profile_change_perform(callback: CallbackQuery, callback_data: TgProfileChangePeriodCallback) -> None:
    meta = TG_PROFILE_CHANGE_FILTERS.get(callback_data.key, TG_PROFILE_CHANGE_FILTERS["all"])
    change_label = str(meta["label"])
    
    since_ts = period_to_since_ts(callback_data.days)
    change_types = meta.get("types")
    
    changes = await db.get_tg_profile_changes_for_report(
        chat_id=callback.message.chat.id,
        telegram_user_id=callback_data.tg_id,
        change_types=list(change_types) if isinstance(change_types, list) else None,
        since_ts=since_ts,
        limit=300,
    )

    detail = await db.get_tg_tracked_user_detail(callback.message.chat.id, callback_data.tg_id)
    name = build_tg_display_name(detail)
    
    header = "\n".join([
        "<b>📝 Отчет по изменениям профиля [TG]</b>",
        f"👤 <b>{escape_html(name)}</b>",
        f"Тип: <b>{escape_html(change_label)}</b>",
        f"Период: <b>{escape_html(format_period_label(callback_data.days))}</b>",
    ])

    from ui_keyboards import tg_profile_change_result_keyboard
    if not changes:
        await callback.message.answer(
            f"{header}\n\n🔍 Изменения за выбранный период не найдены.",
            reply_markup=tg_profile_change_result_keyboard(callback_data.tg_id, callback_data.key, callback_data.src)
        )
    else:
        blocks = [header]
        for c in changes:
            blocks.append(build_tg_profile_change_block(c))
        await _send_long_html(callback.message, blocks)
        await callback.message.answer("📝 Отчет завершен.", reply_markup=tg_profile_change_result_keyboard(callback_data.tg_id, callback_data.key, callback_data.src))
    
    await callback.answer()
