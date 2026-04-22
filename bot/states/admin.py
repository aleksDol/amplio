from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    waiting_for_paid_slot_price = State()

