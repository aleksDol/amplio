from typing import Iterable

from asyncpg import Record
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_my_channels_keyboard(channels: Iterable[Record]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for channel in channels:
        title = channel["title"] or channel["username"] or f"Канал #{channel['id']}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=title,
                    callback_data=f"channel:view:{channel['id']}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_channel_card_keyboard(channel_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🏷 Тематика", callback_data=f"channel:edit_niche:{channel_id}"),
                InlineKeyboardButton(text="👥 Подписчики", callback_data=f"channel:edit_subscribers:{channel_id}"),
            ],
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data=f"channel:refresh_subscribers:{channel_id}"),
                InlineKeyboardButton(text="📊 Статистика", callback_data=f"channel:stats:{channel_id}"),
            ],
            [
                InlineKeyboardButton(text="↩️ Назад", callback_data="channels:list"),
                InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main"),
            ],
        ]
    )


def get_no_channels_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Добавить канал", callback_data="add_channel:start"),
                InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main"),
            ],
        ]
    )
