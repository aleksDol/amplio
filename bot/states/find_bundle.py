from aiogram.fsm.state import State, StatesGroup


class FindBundleStates(StatesGroup):
    waiting_for_channel_selection = State()
    waiting_for_bundle_selection = State()
    waiting_for_free_ad_text = State()
    waiting_for_paid_ad_text = State()
