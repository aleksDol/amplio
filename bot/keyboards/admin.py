from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Проблемные каналы", callback_data="admin:problem_channels")],
            [InlineKeyboardButton(text="Последние нарушения", callback_data="admin:violations")],
            [InlineKeyboardButton(text="Обновить", callback_data="admin:refresh")],
            [InlineKeyboardButton(text="В меню", callback_data="menu:main")],
        ]
    )
