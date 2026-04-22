import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from database.connection import get_pool
from keyboards.bundle_preview import (
    get_bundle_preview_cancelled_keyboard,
    get_bundle_preview_confirmed_keyboard,
)
from repositories.participants import (
    get_active_participants_with_channels,
    get_participant_with_bundle_channel,
)
from services.bundle_preview_service import (
    cancel_participant_preview,
    confirm_participant_preview,
    try_move_bundle_to_scheduled,
)
from services.rating_service import apply_preview_cancel_penalty


logger = logging.getLogger(__name__)
router = Router()


def _parse_participant_id(data: str, prefix: str) -> int | None:
    if not data.startswith(prefix):
        return None
    suffix = data[len(prefix) :]
    if not suffix.isdigit():
        return None
    return int(suffix)


@router.callback_query(F.data.startswith("bundle_preview:confirm:"))
async def confirm_bundle_preview_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.data or not callback.from_user:
        return

    participant_id = _parse_participant_id(callback.data, "bundle_preview:confirm:")
    if participant_id is None:
        await callback.message.answer("Не удалось подтвердить участие.")
        return

    pool = get_pool()
    participant = await get_participant_with_bundle_channel(pool, participant_id)
    if not participant:
        await callback.message.answer("Участник не найден.")
        return
    if int(participant["owner_id"]) != int(callback.from_user.id):
        await callback.message.answer("Это подтверждение тебе недоступно.")
        return

    confirmed = await confirm_participant_preview(pool, participant_id)
    if not confirmed:
        await callback.message.answer("Не удалось подтвердить участие.")
        return

    await try_move_bundle_to_scheduled(pool, int(participant["bundle_id"]))
    logger.info("Preview confirmed participant_id=%s bundle_id=%s", participant_id, participant["bundle_id"])
    await callback.message.answer(
        "Участие подтверждено ✅",
        reply_markup=get_bundle_preview_confirmed_keyboard(),
    )


@router.callback_query(F.data.startswith("bundle_preview:cancel:"))
async def cancel_bundle_preview_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.data or not callback.from_user:
        return

    participant_id = _parse_participant_id(callback.data, "bundle_preview:cancel:")
    if participant_id is None:
        await callback.message.answer("Не удалось отменить участие.")
        return

    pool = get_pool()
    participant = await get_participant_with_bundle_channel(pool, participant_id)
    if not participant:
        await callback.message.answer("Участник не найден.")
        return
    if int(participant["owner_id"]) != int(callback.from_user.id):
        await callback.message.answer("Это действие тебе недоступно.")
        return

    bundle_id = await cancel_participant_preview(pool, participant_id)
    if bundle_id is None:
        await callback.message.answer("Не удалось отменить участие.")
        return

    await apply_preview_cancel_penalty(
        pool=pool,
        channel_id=int(participant["channel_id"]),
        bundle_id=int(participant["bundle_id"]),
    )

    remaining = await get_active_participants_with_channels(pool, bundle_id)
    for item in remaining:
        owner_id = int(item["owner_id"])
        if owner_id == callback.from_user.id:
            continue
        try:
            await callback.bot.send_message(
                chat_id=owner_id,
                text="Состав подборки изменился: один из участников отменил участие. Подборка снова открыта для добора.",
            )
        except Exception:
            continue

    logger.info("Preview cancelled participant_id=%s bundle_id=%s", participant_id, bundle_id)
    await callback.message.answer(
        "Ты исключён из подборки\nПодборка снова открыта для добора участников",
        reply_markup=get_bundle_preview_cancelled_keyboard(),
    )
