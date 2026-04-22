from typing import Iterable

from asyncpg import Record
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_find_bundle_channel_keyboard(channels: Iterable[Record]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for channel in channels:
        title = channel["title"] or channel["username"] or f"Канал #{channel['id']}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=title,
                    callback_data=f"find_bundle:channel:{channel['id']}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="В меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_find_bundle_no_ready_channels_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Добавить канал", callback_data="add_channel:start")],
            [InlineKeyboardButton(text="Мои каналы", callback_data="channels:list")],
            [InlineKeyboardButton(text="В меню", callback_data="menu:main")],
        ]
    )


def get_find_bundle_results_keyboard(bundle_ids: Iterable[int]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for bundle_id in bundle_ids:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"Открыть подборку #{bundle_id}",
                    callback_data=f"find_bundle:view:{bundle_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="Обновить", callback_data="find_bundle:refresh")])
    rows.append([InlineKeyboardButton(text="Выбрать другой канал", callback_data="find_bundle:choose_channel")])
    rows.append([InlineKeyboardButton(text="В меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_find_bundle_empty_results_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Обновить", callback_data="find_bundle:refresh")],
            [InlineKeyboardButton(text="Выбрать другой канал", callback_data="find_bundle:choose_channel")],
            [InlineKeyboardButton(text="В меню", callback_data="menu:main")],
        ]
    )


def get_find_bundle_card_keyboard(
    bundle_id: int,
    free_allowed: bool,
    paid_allowed: bool,
    back_callback: str = "find_bundle:back_to_results",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if free_allowed:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Вступить бесплатно",
                    callback_data=f"find_bundle:join_free:{bundle_id}",
                )
            ]
        )
    if paid_allowed:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Вступить платно",
                    callback_data=f"find_bundle:join_paid:{bundle_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="Назад к списку", callback_data=back_callback)])
    rows.append([InlineKeyboardButton(text="В меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_pending_participations_keyboard(participant_ids: Iterable[int]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for participant_id in participant_ids:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"Открыть участие #{participant_id}",
                    callback_data=f"participations:open:{participant_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="Обновить", callback_data="participations:refresh")])
    rows.append([InlineKeyboardButton(text="В меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_pending_participations_empty_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Обновить", callback_data="participations:refresh")],
            [InlineKeyboardButton(text="В меню", callback_data="menu:main")],
        ]
    )
