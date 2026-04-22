from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_stats_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data="stats:refresh"),
                InlineKeyboardButton(text="📺 Мои каналы", callback_data="channels:list"),
            ],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")],
        ]
    )
