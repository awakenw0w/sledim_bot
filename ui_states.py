"""
FSM-состояния для кнопочного интерфейса бота.
"""

from aiogram.fsm.state import State, StatesGroup


class AddUserStates(StatesGroup):
    waiting_for_vk_link = State()
    waiting_for_tg_link = State()


class SearchStates(StatesGroup):
    waiting_for_query = State()
    viewing_results = State()
