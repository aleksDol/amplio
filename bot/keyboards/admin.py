from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⚠️ Проблемные каналы", callback_data="admin:problem_channels"),
                InlineKeyboardButton(text="📛 Нарушения", callback_data="admin:violations"),
            ],
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data="admin:refresh"),
                InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main"),
            ],
        ]
    )


def get_set_paid_price_keyboard(bundle_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"💳 Назначить цену для #{bundle_id}",
                    callback_data=f"admin:set_paid_price:{bundle_id}",
                )
            ],
            [InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="admin:refresh")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")],
        ]
    )
