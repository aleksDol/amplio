import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database.connection import get_pool
from keyboards.add_channel import get_add_channel_success_keyboard
from keyboards.channel_setup import get_niches_keyboard, get_subscribers_confirm_keyboard
from keyboards.channels import get_channel_card_keyboard
from repositories.channels import (
    get_channel_by_id,
    update_channel_niche,
    update_channel_subscribers,
)
from services.matching import calculate_range
from services.telegram_channels import get_subscribers_count
from states.channel_setup import ChannelSetup


logger = logging.getLogger(__name__)
router = Router()

MAX_SUBSCRIBERS = 100_000_000


def _format_number(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def _parse_subscribers(text: str) -> int | None:
    cleaned = text.strip().replace(" ", "")
    if not cleaned.isdigit():
        return None
    value = int(cleaned)
    if value <= 0 or value >= MAX_SUBSCRIBERS:
        return None
    return value


def _parse_channel_id_from_callback(data: str, expected_prefix: str) -> int | None:
    if not data.startswith(expected_prefix):
        return None
    suffix = data[len(expected_prefix) :]
    if not suffix.isdigit():
        return None
    return int(suffix)


async def _save_subscribers(channel_id: int, subscribers: int) -> bool:
    pool = get_pool()
    min_subscribers, max_subscribers = calculate_range(subscribers)
    updated = await update_channel_subscribers(
        pool=pool,
        channel_id=channel_id,
        subscribers=subscribers,
        min_subscribers=min_subscribers,
        max_subscribers=max_subscribers,
    )
    return updated is not None


@router.callback_query(F.data.startswith("niche:set:"), ChannelSetup.waiting_for_niche)
async def set_channel_niche(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.data or not callback.from_user:
        return

    parts = callback.data.split(":", maxsplit=3)
    if len(parts) != 4 or not parts[2].isdigit():
        await callback.message.answer("Не удалось обработать выбор тематики. Попробуй ещё раз.")
        return

    channel_id = int(parts[2])
    niche = parts[3]
    fsm_data = await state.get_data()
    setup_mode = fsm_data.get("setup_mode", "initial_setup")

    pool = get_pool()
    channel = await get_channel_by_id(pool, channel_id)
    if not channel or channel["owner_id"] != callback.from_user.id:
        await state.clear()
        await callback.message.answer("Канал не найден. Открой список каналов и попробуй снова.")
        return

    await update_channel_niche(pool, channel_id, niche)

    if setup_mode == "edit_niche":
        await state.clear()
        await callback.message.answer(
            "Тематика обновлена ✅",
            reply_markup=get_channel_card_keyboard(channel_id),
        )
        return

    chat_id = channel["telegram_chat_id"]
    logger.info("Trying auto subscribers fetch for chat_id=%s channel_id=%s", chat_id, channel_id)
    auto_subscribers = await get_subscribers_count(callback.bot, chat_id)
    if auto_subscribers is None:
        logger.info("Auto subscribers fetch failed for channel_id=%s, fallback to manual", channel_id)
        await state.set_state(ChannelSetup.waiting_for_subscribers_input)
        await state.update_data(
            channel_id=channel_id,
            chat_id=chat_id,
            auto_subscribers=None,
            setup_mode="initial_setup",
        )
        await callback.message.answer(
            "Не удалось определить количество подписчиков автоматически. Отправь число вручную"
        )
        return

    logger.info(
        "Auto subscribers fetched for channel_id=%s value=%s",
        channel_id,
        auto_subscribers,
    )
    await state.set_state(ChannelSetup.waiting_for_subscribers_confirm)
    await state.update_data(
        channel_id=channel_id,
        chat_id=chat_id,
        auto_subscribers=auto_subscribers,
        setup_mode="initial_setup",
    )
    await callback.message.answer(
        f"Нашёл: {_format_number(auto_subscribers)} подписчиков.\nПодтвердить или изменить?",
        reply_markup=get_subscribers_confirm_keyboard(channel_id),
    )


@router.callback_query(
    F.data.startswith("confirm_subscribers:"),
    ChannelSetup.waiting_for_subscribers_confirm,
)
async def confirm_subscribers(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.data:
        return

    channel_id = _parse_channel_id_from_callback(callback.data, "confirm_subscribers:")
    if channel_id is None:
        await callback.message.answer("Не удалось обработать подтверждение. Попробуй ещё раз.")
        return

    fsm_data = await state.get_data()
    auto_subscribers = fsm_data.get("auto_subscribers")
    if not isinstance(auto_subscribers, int):
        await state.set_state(ChannelSetup.waiting_for_subscribers_input)
        await callback.message.answer("Отправь число подписчиков, например: 12500")
        return

    if auto_subscribers <= 0 or auto_subscribers >= MAX_SUBSCRIBERS:
        await state.set_state(ChannelSetup.waiting_for_subscribers_input)
        await callback.message.answer("Отправь число, например: 12500")
        return

    saved = await _save_subscribers(channel_id, auto_subscribers)
    if not saved:
        await state.clear()
        await callback.message.answer("Не удалось обновить данные канала. Попробуй снова.")
        return

    await state.clear()
    await callback.message.answer(
        "Канал полностью настроен ✅\nТеперь он может участвовать в подборках",
        reply_markup=get_add_channel_success_keyboard(),
    )


@router.callback_query(
    F.data.startswith("edit_subscribers:"),
    ChannelSetup.waiting_for_subscribers_confirm,
)
async def edit_subscribers(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.data:
        return

    channel_id = _parse_channel_id_from_callback(callback.data, "edit_subscribers:")
    if channel_id is None:
        await callback.message.answer("Не удалось открыть редактирование. Попробуй ещё раз.")
        return

    fsm_data = await state.get_data()
    await state.set_state(ChannelSetup.waiting_for_subscribers_edit)
    await state.update_data(
        channel_id=channel_id,
        chat_id=fsm_data.get("chat_id"),
        auto_subscribers=fsm_data.get("auto_subscribers"),
        setup_mode=fsm_data.get("setup_mode", "initial_setup"),
    )
    await callback.message.answer("Отправь число, например: 12500")


@router.message(ChannelSetup.waiting_for_subscribers_input)
@router.message(ChannelSetup.waiting_for_subscribers_edit)
async def handle_subscribers_input(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Отправь число, например: 12500")
        return

    subscribers = _parse_subscribers(message.text)
    if subscribers is None:
        await message.answer("Отправь число, например: 12500")
        return

    fsm_data = await state.get_data()
    channel_id = fsm_data.get("channel_id")
    setup_mode = fsm_data.get("setup_mode", "initial_setup")
    if not isinstance(channel_id, int):
        await state.clear()
        await message.answer("Не удалось определить канал. Открой список каналов и попробуй снова.")
        return

    saved = await _save_subscribers(channel_id, subscribers)
    if not saved:
        await state.clear()
        await message.answer("Не удалось обновить данные канала. Попробуй снова.")
        return

    await state.clear()
    if setup_mode == "initial_setup":
        await message.answer(
            "Канал полностью настроен ✅\nТеперь он может участвовать в подборках",
            reply_markup=get_add_channel_success_keyboard(),
        )
        return

    await message.answer(
        f"Подписчики обновлены: {_format_number(subscribers)}",
        reply_markup=get_channel_card_keyboard(channel_id),
    )


async def start_channel_setup_flow(
    message: Message,
    state: FSMContext,
    channel_id: int,
    chat_id: int,
) -> None:
    await state.set_state(ChannelSetup.waiting_for_niche)
    await state.set_data(
        {
            "channel_id": channel_id,
            "chat_id": chat_id,
            "auto_subscribers": None,
            "setup_mode": "initial_setup",
        }
    )
    await message.answer(
        "Теперь выбери тематику канала",
        reply_markup=get_niches_keyboard(channel_id),
    )
