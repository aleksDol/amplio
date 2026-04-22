from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Добавить канал", callback_data="add_channel:start")],
            [InlineKeyboardButton(text="Найти подборку", callback_data="find_bundle")],
            [InlineKeyboardButton(text="Мои участия", callback_data="participations:pending")],
            [InlineKeyboardButton(text="Создать подборку", callback_data="bundle:create:start")],
            [InlineKeyboardButton(text="Мои каналы", callback_data="channels:list")],
            [InlineKeyboardButton(text="Статистика", callback_data="stats:open")],
            [InlineKeyboardButton(text="Настройки", callback_data="settings")],
        ]
    )
