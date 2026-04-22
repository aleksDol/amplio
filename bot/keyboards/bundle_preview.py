from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_bundle_preview_keyboard(participant_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подтвердить", callback_data=f"bundle_preview:confirm:{participant_id}")],
            [InlineKeyboardButton(text="Отменить участие", callback_data=f"bundle_preview:cancel:{participant_id}")],
        ]
    )


def get_bundle_preview_confirmed_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Мои каналы", callback_data="channels:list")],
            [InlineKeyboardButton(text="В меню", callback_data="menu:main")],
        ]
    )


def get_bundle_preview_cancelled_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Найти подборку", callback_data="find_bundle")],
            [InlineKeyboardButton(text="В меню", callback_data="menu:main")],
        ]
    )
