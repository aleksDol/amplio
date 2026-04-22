from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_add_channel_check_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Проверить", callback_data="add_channel:check")],
            [InlineKeyboardButton(text="Отмена", callback_data="add_channel:cancel")],
        ]
    )


def get_add_channel_success_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Добавить ещё канал",
                    callback_data="add_channel:add_more",
                )
            ],
            [InlineKeyboardButton(text="Мои каналы", callback_data="channels:list")],
            [InlineKeyboardButton(text="В меню", callback_data="menu:main")],
        ]
    )


def get_add_channel_retry_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Добавить ещё канал", callback_data="add_channel:add_more")],
            [InlineKeyboardButton(text="В меню", callback_data="menu:main")],
        ]
    )
