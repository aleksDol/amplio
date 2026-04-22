from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from constants.niches import NICHES


def get_niches_keyboard(channel_id: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for niche in NICHES:
        callback_data = f"niche:set:{channel_id}:{niche}"
        rows.append([InlineKeyboardButton(text=niche, callback_data=callback_data)])
    rows.append([InlineKeyboardButton(text="В меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_subscribers_confirm_keyboard(channel_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"confirm_subscribers:{channel_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Изменить",
                    callback_data=f"edit_subscribers:{channel_id}",
                )
            ],
        ]
    )
