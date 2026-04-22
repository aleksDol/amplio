from aiogram.fsm.state import State, StatesGroup


class BundleCreateStates(StatesGroup):
    waiting_for_creator_channel = State()
    waiting_for_niche_choice = State()
    waiting_for_time = State()
    waiting_for_slots = State()
    waiting_for_post_lifetime = State()
    waiting_for_ad_text = State()
    waiting_for_confirmation = State()
