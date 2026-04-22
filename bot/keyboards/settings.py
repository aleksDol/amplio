from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔔 Включить", callback_data="settings:notifications:on"),
                InlineKeyboardButton(text="🔕 Выключить", callback_data="settings:notifications:off"),
            ],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")],
        ]
    )


def get_notifications_disabled_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔔 Включить уведомления", callback_data="settings:notifications:on"),
                InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings:open"),
            ],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")],
        ]
    )
