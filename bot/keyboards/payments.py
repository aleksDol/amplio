from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_payment_actions_keyboard(payment_id: int, payment_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=payment_url)],
            [
                InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"payments:check:{payment_id}"),
                InlineKeyboardButton(text="❌ Отменить заявку", callback_data=f"payments:cancel:{payment_id}"),
            ],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")],
        ]
    )


def get_payment_success_keyboard(bundle_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 Открыть подборку", callback_data=f"find_bundle:view:{bundle_id}"),
                InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main"),
            ],
        ]
    )
