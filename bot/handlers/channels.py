import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from database.connection import get_pool
from keyboards.channel_setup import get_niches_keyboard
from keyboards.channels import (
    get_channel_card_keyboard,
    get_my_channels_keyboard,
    get_no_channels_keyboard,
)
from repositories.channels import (
    get_channel_by_id,
    get_user_channels,
    update_channel_subscribers,
)
from services.matching import calculate_range
from services.telegram_channels import get_subscribers_count
from states.channel_setup import ChannelSetup


logger = logging.getLogger(__name__)
router = Router()


def _format_number(value: int | None) -> str:
    if value is None:
        return "не задано"
    return f"{value:,}".replace(",", " ")


def _is_channel_ready(channel) -> bool:
    return (
        channel["niche"] is not None
        and channel["subscribers"] is not None
        and bool(channel["bot_is_admin"])
    )


def _build_channel_card_text(channel) -> str:
    status = "Готов ✅" if _is_channel_ready(channel) else "Нужно заполнить профиль"
    return (
        f"Канал: {channel['title'] or channel['username']}\n"
        f"Username: {channel['username'] or 'не задан'}\n"
        f"Тематика: {channel['niche'] or 'не выбрана'}\n"
        f"Подписчики: {_format_number(channel['subscribers'])}\n"
        f"Диапазон матчинга: {_format_number(channel['min_free_match_subscribers'])} - "
        f"{_format_number(channel['max_free_match_subscribers'])}\n"
        f"Статус: {status}"
    )


def _parse_channel_id(data: str, prefix: str) -> int | None:
    if not data.startswith(prefix):
        return None
    value = data[len(prefix) :]
    if not value.isdigit():
        return None
    return int(value)


@router.callback_query(F.data == "channels:list")
async def show_user_channels(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.from_user:
        return

    pool = get_pool()
    channels = await get_user_channels(pool, callback.from_user.id)
    if not channels:
        await callback.message.answer(
            "У тебя пока нет добавленных каналов",
            reply_markup=get_no_channels_keyboard(),
        )
        return

    await callback.message.answer(
        "Твои каналы:",
        reply_markup=get_my_channels_keyboard(channels),
    )


@router.callback_query(F.data.startswith("channel:view:"))
async def show_channel_card(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.data or not callback.from_user:
        return

    channel_id = _parse_channel_id(callback.data, "channel:view:")
    if channel_id is None:
        await callback.message.answer("Не удалось открыть канал. Попробуй снова.")
        return

    pool = get_pool()
    channel = await get_channel_by_id(pool, channel_id)
    if not channel or channel["owner_id"] != callback.from_user.id:
        await callback.message.answer("Канал не найден.")
        return

    await callback.message.answer(
        _build_channel_card_text(channel),
        reply_markup=get_channel_card_keyboard(channel_id),
    )


@router.callback_query(F.data.startswith("channel:edit_niche:"))
async def edit_channel_niche(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.data or not callback.from_user:
        return

    channel_id = _parse_channel_id(callback.data, "channel:edit_niche:")
    if channel_id is None:
        await callback.message.answer("Не удалось открыть редактирование тематики.")
        return

    pool = get_pool()
    channel = await get_channel_by_id(pool, channel_id)
    if not channel or channel["owner_id"] != callback.from_user.id:
        await callback.message.answer("Канал не найден.")
        return

    await state.set_state(ChannelSetup.waiting_for_niche)
    await state.set_data(
        {
            "channel_id": channel_id,
            "chat_id": channel["telegram_chat_id"],
            "auto_subscribers": None,
            "setup_mode": "edit_niche",
        }
    )
    await callback.message.answer(
        "Выбери тематику канала",
        reply_markup=get_niches_keyboard(channel_id),
    )


@router.callback_query(F.data.startswith("channel:edit_subscribers:"))
async def edit_channel_subscribers(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.data or not callback.from_user:
        return

    channel_id = _parse_channel_id(callback.data, "channel:edit_subscribers:")
    if channel_id is None:
        await callback.message.answer("Не удалось открыть редактирование подписчиков.")
        return

    pool = get_pool()
    channel = await get_channel_by_id(pool, channel_id)
    if not channel or channel["owner_id"] != callback.from_user.id:
        await callback.message.answer("Канал не найден.")
        return

    await state.set_state(ChannelSetup.waiting_for_subscribers_edit)
    await state.set_data(
        {
            "channel_id": channel_id,
            "chat_id": channel["telegram_chat_id"],
            "auto_subscribers": None,
            "setup_mode": "edit_subscribers",
        }
    )
    await callback.message.answer("Отправь число, например: 12500")


@router.callback_query(F.data.startswith("channel:refresh_subscribers:"))
async def refresh_channel_subscribers(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.data or not callback.from_user:
        return

    channel_id = _parse_channel_id(callback.data, "channel:refresh_subscribers:")
    if channel_id is None:
        await callback.message.answer("Не удалось обновить подписчиков.")
        return

    pool = get_pool()
    channel = await get_channel_by_id(pool, channel_id)
    if not channel or channel["owner_id"] != callback.from_user.id:
        await callback.message.answer("Канал не найден.")
        return

    chat_id = channel["telegram_chat_id"]
    logger.info("User %s requested subscribers refresh for channel_id=%s", callback.from_user.id, channel_id)
    subscribers = await get_subscribers_count(callback.bot, chat_id)
    if subscribers is None:
        logger.info("Auto refresh failed for channel_id=%s; fallback to manual input", channel_id)
        await state.set_state(ChannelSetup.waiting_for_subscribers_input)
        await state.set_data(
            {
                "channel_id": channel_id,
                "chat_id": chat_id,
                "auto_subscribers": None,
                "setup_mode": "refresh_fallback",
            }
        )
        await callback.message.answer("Не удалось обновить автоматически. Введи число вручную")
        return

    min_subscribers, max_subscribers = calculate_range(subscribers)
    await update_channel_subscribers(
        pool=pool,
        channel_id=channel_id,
        subscribers=subscribers,
        min_subscribers=min_subscribers,
        max_subscribers=max_subscribers,
    )
    logger.info(
        "Subscribers refreshed for channel_id=%s value=%s",
        channel_id,
        subscribers,
    )
    await callback.message.answer(
        f"Подписчики обновлены: {_format_number(subscribers)}",
        reply_markup=get_channel_card_keyboard(channel_id),
    )
