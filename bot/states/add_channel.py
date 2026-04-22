from aiogram.fsm.state import State, StatesGroup


class AddChannelStates(StatesGroup):
    waiting_for_channel_username = State()
    waiting_for_admin_check = State()
