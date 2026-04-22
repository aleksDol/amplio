from aiogram.fsm.state import State, StatesGroup


class ChannelSetup(StatesGroup):
    waiting_for_niche = State()
    waiting_for_subscribers_input = State()
    waiting_for_subscribers_confirm = State()
    waiting_for_subscribers_edit = State()
