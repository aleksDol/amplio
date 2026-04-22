import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from database.connection import get_pool
from keyboards.settings import get_notifications_disabled_keyboard, get_settings_keyboard
from repositories.user_settings import (
    get_bundle_notifications_enabled,
    set_bundle_notifications_enabled,
)


logger = logging.getLogger(__name__)
router = Router()


async def _show_settings(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return
    pool = get_pool()
    enabled = await get_bundle_notifications_enabled(pool, callback.from_user.id)
    status_text = "включены ✅" if enabled else "выключены"
    await callback.message.answer(
        f"Уведомления о новых подборках: {status_text}",
        reply_markup=get_settings_keyboard(),
    )


@router.callback_query(F.data == "settings")
@router.callback_query(F.data == "settings:open")
async def open_settings(callback: CallbackQuery) -> None:
    await callback.answer()
    await _show_settings(callback)


@router.callback_query(F.data == "settings:notifications:on")
async def settings_notifications_on(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.from_user:
        return
    pool = get_pool()
    await set_bundle_notifications_enabled(pool, callback.from_user.id, True)
    logger.info("User %s enabled bundle notifications", callback.from_user.id)
    await callback.message.answer("Уведомления о новых подборках включены ✅", reply_markup=get_settings_keyboard())


@router.callback_query(F.data == "settings:notifications:off")
async def settings_notifications_off(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.from_user:
        return
    pool = get_pool()
    await set_bundle_notifications_enabled(pool, callback.from_user.id, False)
    logger.info("User %s disabled bundle notifications", callback.from_user.id)
    await callback.message.answer("Уведомления о новых подборках отключены", reply_markup=get_settings_keyboard())


@router.callback_query(F.data == "notifications:disable")
async def disable_notifications_from_push(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.from_user:
        return
    pool = get_pool()
    await set_bundle_notifications_enabled(pool, callback.from_user.id, False)
    logger.info("User %s disabled notifications from push", callback.from_user.id)
    await callback.message.answer(
        "Уведомления о новых подборках отключены",
        reply_markup=get_notifications_disabled_keyboard(),
    )
