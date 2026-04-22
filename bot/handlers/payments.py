import logging
from typing import Any

from aiogram import F, Router
from aiogram.types import CallbackQuery

from database.connection import get_pool
from keyboards.main_menu import get_main_menu_keyboard
from keyboards.payments import get_payment_success_keyboard
from repositories.channels import get_channel_by_id
from repositories.participants import get_participant_by_id
from repositories.payments import get_payment_by_id
from services.payment_service import (
    PaymentServiceError,
    cancel_paid_participation,
    check_and_activate_payment,
    expire_stale_payments,
    process_yookassa_webhook,
)
from services.bundle_preview_service import try_start_preview_for_bundle
from services.notifications import notify_creator_about_new_participant


logger = logging.getLogger(__name__)
router = Router()


def _parse_payment_id(data: str, prefix: str) -> int | None:
    if not data.startswith(prefix):
        return None
    value = data[len(prefix) :]
    if not value.isdigit():
        return None
    return int(value)


async def _is_payment_owner(payment_id: int, user_id: int) -> bool:
    pool = get_pool()
    payment = await get_payment_by_id(pool, payment_id)
    if not payment:
        return False
    participant = await get_participant_by_id(pool, payment["participant_id"])
    if not participant:
        return False
    channel = await get_channel_by_id(pool, participant["channel_id"])
    if not channel:
        return False
    return int(channel["owner_id"]) == int(user_id)


@router.callback_query(F.data.startswith("payments:check:"))
async def check_payment_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.data:
        return
    payment_id = _parse_payment_id(callback.data, "payments:check:")
    if payment_id is None:
        await callback.message.answer("Не удалось проверить оплату.")
        return
    if not callback.from_user or not await _is_payment_owner(payment_id, callback.from_user.id):
        await callback.message.answer("Этот платёж тебе недоступен.")
        return

    pool = get_pool()
    await expire_stale_payments(pool)
    try:
        status, bundle_id, participant_id, activated_now = await check_and_activate_payment(pool, payment_id)
    except PaymentServiceError:
        await callback.message.answer("Не удалось проверить оплату. Попробуй ещё раз.")
        return

    if status == "succeeded":
        if participant_id is not None and activated_now:
            await notify_creator_about_new_participant(callback.bot, pool, participant_id)
        if bundle_id:
            await try_start_preview_for_bundle(callback.bot, pool, bundle_id)
        if bundle_id:
            await callback.message.answer(
                "Оплата получена ✅\nТы стал участником подборки",
                reply_markup=get_payment_success_keyboard(bundle_id),
            )
        else:
            await callback.message.answer("Оплата получена ✅\nТы стал участником подборки")
        return
    if status == "expired":
        await callback.message.answer("Время на оплату истекло\nЕсли хочешь, создай заявку заново")
        return
    if status == "cancelled":
        await callback.message.answer("Заявка отменена")
        return

    await callback.message.answer("Оплата пока не подтверждена")


@router.callback_query(F.data.startswith("payments:cancel:"))
async def cancel_payment_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.data:
        return
    payment_id = _parse_payment_id(callback.data, "payments:cancel:")
    if payment_id is None:
        await callback.message.answer("Не удалось отменить заявку.")
        return
    if not callback.from_user or not await _is_payment_owner(payment_id, callback.from_user.id):
        await callback.message.answer("Эта заявка тебе недоступна.")
        return

    pool = get_pool()
    success = await cancel_paid_participation(pool, payment_id)
    if not success:
        await callback.message.answer("Эту заявку уже нельзя отменить")
        return
    await callback.message.answer("Заявка отменена", reply_markup=get_main_menu_keyboard())


async def handle_yookassa_webhook_payload(payload: dict[str, Any], bot=None) -> dict[str, Any]:
    """
    Эту функцию можно подключить к FastAPI/aiohttp маршруту webhook.
    Она идемпотентна: повторный webhook не ломает состояние.
    """
    pool = get_pool()
    result, payment_id = await process_yookassa_webhook(pool, payload)
    if result == "succeeded" and payment_id and bot is not None:
        payment = await get_payment_by_id(pool, payment_id)
        if payment:
            participant = await get_participant_by_id(pool, payment["participant_id"])
            if participant:
                await notify_creator_about_new_participant(bot, pool, int(participant["id"]))
                await try_start_preview_for_bundle(bot, pool, int(participant["bundle_id"]))
    logger.info("YooKassa webhook processed result=%s payment_id=%s", result, payment_id)
    return {"result": result, "payment_id": payment_id}
