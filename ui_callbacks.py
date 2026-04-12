"""
Структуры callback_data для inline-кнопок.
"""

from aiogram.filters.callback_data import CallbackData


class NavCallback(CallbackData, prefix="nav"):
    target: str


class UserActionCallback(CallbackData, prefix="usr"):
    action: str
    vk_id: int
    src: str


class DeleteConfirmCallback(CallbackData, prefix="del"):
    vk_id: int
    confirm: int
    src: str


class PeriodSelectCallback(CallbackData, prefix="prd"):
    scope: str
    vk_id: int
    days: int
    src: str


class NotifyModeCallback(CallbackData, prefix="ntf"):
    mode: str


class NotifyToggleCallback(CallbackData, prefix="ntc"):
    key: str


class ProfileChangeUserCallback(CallbackData, prefix="pcu"):
    vk_id: int
    src: str


class ProfileChangeTypeCallback(CallbackData, prefix="pct"):
    vk_id: int
    key: str
    src: str


class ProfileChangePeriodCallback(CallbackData, prefix="pcp"):
    vk_id: int
    key: str
    days: int
    src: str
