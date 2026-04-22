import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database.connection import get_pool
from handlers.channel_setup import start_channel_setup_flow
from keyboards.add_channel import get_add_channel_check_keyboard, get_add_channel_retry_keyboard
from keyboards.main_menu import get_main_menu_keyboard
from repositories.channels import (
    create_channel,
    get_channel_by_chat_id,
    get_channel_by_username,
    upsert_user,
)
from services.telegram_channels import (
    check_bot_admin_rights,
    get_channel_info,
    is_channel_chat,
    validate_channel_username,
)
from states.add_channel import AddChannelStates


logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "add_channel:start")
@router.callback_query(F.data == "add_channel:add_more")
async def start_add_channel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(AddChannelStates.waiting_for_channel_username)
    await state.set_data({})
    user_id = callback.from_user.id if callback.from_user else 0
    logger.info("Add channel flow started by user %s", user_id)
    await callback.message.answer("Отправь @username своего канала")


@router.message(AddChannelStates.waiting_for_channel_username)
async def receive_channel_username(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Отправь корректный @username канала")
        return

    username = message.text.strip()
    if not validate_channel_username(username):
        await message.answer("Отправь корректный @username канала")
        return

    user_id = message.from_user.id if message.from_user else 0
    logger.info("User %s tries to add channel %s", user_id, username)

    channel = await get_channel_info(message.bot, username)
    if channel is None:
        await message.answer(
            "Не удалось найти канал. Проверь username и убедись, что канал публичный"
        )
        return

    logger.info("Channel info loaded: chat_id=%s username=%s", channel.chat_id, channel.username)

    if not is_channel_chat(channel.chat_type):
        await message.answer("Нужен именно Telegram-канал, а не группа или личный чат")
        return

    pool = get_pool()
    existing_by_username = await get_channel_by_username(pool, channel.username)
    existing_by_chat_id = await get_channel_by_chat_id(pool, channel.chat_id)
    if existing_by_username or existing_by_chat_id:
        await message.answer(
            "Этот канал уже добавлен",
            reply_markup=get_add_channel_retry_keyboard(),
        )
        return

    await state.update_data(
        channel_chat_id=channel.chat_id,
        channel_username=channel.username,
        channel_title=channel.title,
    )
    await state.set_state(AddChannelStates.waiting_for_admin_check)

    await message.answer(
        "Теперь добавь меня администратором канала с правом публикации постов, "
        "а потом нажми Проверить",
        reply_markup=get_add_channel_check_keyboard(),
    )


@router.callback_query(F.data == "add_channel:check", AddChannelStates.waiting_for_admin_check)
async def check_added_channel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()

    chat_id = data.get("channel_chat_id")
    channel_username = data.get("channel_username")
    channel_title = data.get("channel_title")

    if not chat_id or not channel_username:
        await state.set_state(AddChannelStates.waiting_for_channel_username)
        await callback.message.answer("Отправь @username своего канала")
        return

    bot_user = await callback.bot.get_me()
    has_rights = await check_bot_admin_rights(callback.bot, chat_id=chat_id, bot_id=bot_user.id)
    if not has_rights:
        logger.info(
            "Bot admin check failed for chat_id=%s requested by user=%s",
            chat_id,
            callback.from_user.id if callback.from_user else 0,
        )
        await callback.message.answer(
            "Я пока не вижу нужных прав в канале. Проверь настройки и нажми Проверить ещё раз",
            reply_markup=get_add_channel_check_keyboard(),
        )
        return

    pool = get_pool()
    existing_by_username = await get_channel_by_username(pool, channel_username)
    existing_by_chat_id = await get_channel_by_chat_id(pool, chat_id)
    if existing_by_username or existing_by_chat_id:
        await state.clear()
        await callback.message.answer(
            "Этот канал уже добавлен",
            reply_markup=get_add_channel_retry_keyboard(),
        )
        return

    if not callback.from_user:
        await state.clear()
        await callback.message.answer("Не удалось определить пользователя. Попробуй снова.")
        return

    await upsert_user(
        pool=pool,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
    )
    created_channel = await create_channel(
        pool=pool,
        owner_id=callback.from_user.id,
        telegram_chat_id=chat_id,
        username=channel_username,
        title=channel_title or channel_username,
    )
    if not created_channel:
        await state.clear()
        await callback.message.answer(
            "Этот канал уже добавлен",
            reply_markup=get_add_channel_retry_keyboard(),
        )
        return
    logger.info(
        "Channel saved to DB: chat_id=%s username=%s owner_id=%s",
        chat_id,
        channel_username,
        callback.from_user.id,
    )

    await state.clear()
    await callback.message.answer("Канал успешно добавлен ✅")
    await start_channel_setup_flow(
        message=callback.message,
        state=state,
        channel_id=created_channel["id"],
        chat_id=chat_id,
    )


@router.callback_query(
    F.data == "add_channel:cancel",
    StateFilter(
        AddChannelStates.waiting_for_channel_username,
        AddChannelStates.waiting_for_admin_check,
    ),
)
async def cancel_add_channel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.answer(
        "Действие отменено. Возвращаю в главное меню.",
        reply_markup=get_main_menu_keyboard(),
    )


@router.callback_query(F.data == "menu:main")
async def show_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.answer("Главное меню:", reply_markup=get_main_menu_keyboard())
