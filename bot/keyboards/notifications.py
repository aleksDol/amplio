from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_bundle_notification_keyboard(bundle_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Открыть подборку",
                    callback_data=f"notifications:open_bundle:{bundle_id}",
                )
            ],
            [
                InlineKeyboardButton(text="🔕 Отключить уведомления", callback_data="notifications:disable"),
                InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main"),
            ],
        ]
    )


def get_creator_participant_joined_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👀 Посмотреть", callback_data="participations:pending"),
                InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main"),
            ],
        ]
    )
