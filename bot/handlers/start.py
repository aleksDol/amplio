from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from keyboards.main_menu import get_main_menu_keyboard


router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    username = message.from_user.full_name if message.from_user else "друг"
    welcome_text = (
        f"Привет, {username}!\n\n"
        "Добро пожаловать в VP Bot.\n"
        "Выбери действие в главном меню:"
    )
    await message.answer(welcome_text, reply_markup=get_main_menu_keyboard())
