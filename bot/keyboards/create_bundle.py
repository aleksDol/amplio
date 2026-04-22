from typing import Iterable

from asyncpg import Record
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from constants.niches import NICHES


NICHES_BY_SLUG = {
    "marketing": "Маркетинг",
    "business": "Бизнес",
    "finance": "Финансы",
    "investments": "Инвестиции",
    "crypto": "Крипта",
    "news": "Новости",
    "lifestyle": "Лайфстайл",
    "psychology": "Психология",
    "education": "Образование",
    "technology": "Технологии",
    "design": "Дизайн",
    "career": "Карьера",
    "sales": "Продажи",
    "e_commerce": "E-commerce",
    "telegram_smm": "Telegram / SMM",
    "other": "Другое",
}

SLUG_BY_NICHE = {value: key for key, value in NICHES_BY_SLUG.items()}


def get_bundle_creator_channels_keyboard(channels: Iterable[Record]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for channel in channels:
        title = channel["title"] or channel["username"] or f"Канал #{channel['id']}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=title,
                    callback_data=f"bundle:create:channel:{channel['id']}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="bundle:create:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_no_ready_channels_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Добавить канал", callback_data="add_channel:start"),
                InlineKeyboardButton(text="📺 Мои каналы", callback_data="channels:list"),
            ],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")],
        ]
    )


def get_bundle_niche_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Оставить", callback_data="bundle:create:niche:keep"),
                InlineKeyboardButton(text="✏️ Изменить", callback_data="bundle:create:niche:change"),
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="bundle:create:cancel")],
        ]
    )


def get_bundle_niches_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for niche in NICHES:
        slug = SLUG_BY_NICHE.get(niche)
        if not slug:
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=niche,
                    callback_data=f"bundle:create:niche:set:{slug}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="bundle:create:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_bundle_date_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📅 Сегодня", callback_data="bundle:create:date:today"),
                InlineKeyboardButton(text="📆 Завтра", callback_data="bundle:create:date:tomorrow"),
            ],
            [
                InlineKeyboardButton(
                    text="🗓 Послезавтра",
                    callback_data="bundle:create:date:day_after_tomorrow",
                )
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="bundle:create:cancel")],
        ]
    )


def get_bundle_slots_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="4", callback_data="bundle:create:slots:4"),
                InlineKeyboardButton(text="5", callback_data="bundle:create:slots:5"),
                InlineKeyboardButton(text="6", callback_data="bundle:create:slots:6"),
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="bundle:create:cancel")],
        ]
    )


def get_bundle_post_lifetime_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⏱ 24ч", callback_data="bundle:create:lifetime:24"),
                InlineKeyboardButton(text="⏱ 48ч", callback_data="bundle:create:lifetime:48"),
                InlineKeyboardButton(text="⏱ 72ч", callback_data="bundle:create:lifetime:72"),
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="bundle:create:cancel")],
        ]
    )


def get_bundle_paid_slot_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🆓 Без платного места", callback_data="bundle:create:paid:no")],
            [InlineKeyboardButton(text="💳 Добавить платное место", callback_data="bundle:create:paid:yes")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="bundle:create:cancel")],
        ]
    )


def get_bundle_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Создать подборку", callback_data="bundle:create:confirm"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="bundle:create:cancel"),
            ],
        ]
    )


def get_bundle_created_keyboard(bundle_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Открыть подборку", callback_data=f"bundle:view:{bundle_id}")],
            [
                InlineKeyboardButton(text="🛠 Создать ещё", callback_data="bundle:create:start"),
                InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main"),
            ],
        ]
    )
