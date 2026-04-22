import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from database.connection import get_pool
from keyboards.main_menu import get_main_menu_keyboard
from keyboards.stats import get_stats_keyboard
from repositories.channels import get_channel_by_id
from repositories.stats import (
    get_channel_stats,
    get_user_channels_stats,
    get_user_global_stats,
)
from services.stats_service import build_channel_stats_text, build_user_stats_text


logger = logging.getLogger(__name__)
router = Router()


async def _send_user_stats(target: Message | CallbackQuery, user_id: int) -> None:
    pool = get_pool()
    global_stats = await get_user_global_stats(pool, user_id)
    channels_stats = await get_user_channels_stats(pool, user_id)
    text = build_user_stats_text(global_stats, channels_stats)
    message = target.message if isinstance(target, CallbackQuery) else target
    await message.answer(text, reply_markup=get_stats_keyboard())


@router.message(Command("stats"))
async def stats_command(message: Message) -> None:
    if not message.from_user:
        return
    logger.info("Stats requested by user=%s", message.from_user.id)
    await _send_user_stats(message, message.from_user.id)


@router.callback_query(F.data == "stats:open")
@router.callback_query(F.data == "stats:refresh")
async def stats_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.from_user:
        return
    logger.info("Stats callback requested by user=%s data=%s", callback.from_user.id, callback.data)
    await _send_user_stats(callback, callback.from_user.id)


@router.callback_query(F.data.startswith("channel:stats:"))
async def channel_stats_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.data or not callback.from_user:
        return
    suffix = callback.data.replace("channel:stats:", "", 1)
    if not suffix.isdigit():
        await callback.message.answer("Не удалось открыть статистику канала.")
        return
    channel_id = int(suffix)

    pool = get_pool()
    channel = await get_channel_by_id(pool, channel_id)
    if not channel or int(channel["owner_id"]) != int(callback.from_user.id):
        await callback.message.answer("Канал не найден.")
        return

    channel_stats = await get_channel_stats(pool, channel_id)
    if not channel_stats:
        await callback.message.answer("Не удалось получить статистику канала.")
        return

    await callback.message.answer(
        build_channel_stats_text(channel_stats),
        reply_markup=get_stats_keyboard(),
    )


@router.callback_query(F.data == "stats:menu")
async def stats_to_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer("Главное меню:", reply_markup=get_main_menu_keyboard())
