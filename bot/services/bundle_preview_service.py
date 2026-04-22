import logging
from datetime import timedelta

from aiogram import Bot
from asyncpg import Pool

from keyboards.bundle_preview import get_bundle_preview_keyboard
from repositories.bundles import (
    get_bundle_by_id,
    update_bundle_preview,
    update_bundle_status,
)
from repositories.participants import (
    confirm_preview,
    count_participants_by_status,
    get_active_participants_with_channels,
    get_participant_with_bundle_channel,
    get_pending_preview_participants,
    mark_preview_sent,
    reset_preview_confirmations,
    set_participant_status,
)
from services.bundle_post_builder import build_bundle_preview_text
from services.datetime_utils import format_datetime_for_preview, get_local_now
from services.scheduler_service import (
    schedule_bundle_auto_confirm,
    schedule_bundle_publish,
)


logger = logging.getLogger(__name__)


async def bundle_ready_for_preview(pool: Pool, bundle_id: int) -> bool:
    bundle = await get_bundle_by_id(pool, bundle_id)
    if not bundle:
        return False
    if bundle["status"] not in {"full", "open"}:
        return False

    active_participants = await get_active_participants_with_channels(pool, bundle_id)
    if len(active_participants) != int(bundle["slots"]):
        return False

    awaiting_payment_count = await count_participants_by_status(pool, bundle_id, "awaiting_payment")
    if awaiting_payment_count > 0:
        return False

    for participant in active_participants:
        if not (participant["ad_text"] or "").strip():
            return False
    return True


async def send_bundle_preview(bot: Bot, pool: Pool, bundle_id: int) -> bool:
    if not await bundle_ready_for_preview(pool, bundle_id):
        return False

    bundle = await get_bundle_by_id(pool, bundle_id)
    if not bundle:
        return False

    now_local = get_local_now()
    now_naive = now_local.replace(tzinfo=None)
    preview_text = await build_bundle_preview_text(pool, bundle_id)
    await update_bundle_preview(
        pool=pool,
        bundle_id=bundle_id,
        preview_text=preview_text,
        preview_generated_at=now_naive,
    )

    participants = await get_active_participants_with_channels(pool, bundle_id)
    logger.info("Sending bundle preview bundle_id=%s participants=%s", bundle_id, len(participants))

    for participant in participants:
        user_id = int(participant["owner_id"])
        participant_id = int(participant["id"])
        message_id: int | None = None
        try:
            sent = await bot.send_message(
                chat_id=user_id,
                text=(
                    "Подборка готова к публикации\n"
                    f"Публикация: {format_datetime_for_preview(bundle['scheduled_at'])}\n"
                    f"Пост будет удалён через {bundle['post_lifetime_hours']} часов\n\n"
                    "Проверь итоговый пост:\n\n"
                    f"{preview_text}"
                ),
                reply_markup=get_bundle_preview_keyboard(participant_id),
            )
            message_id = sent.message_id
        except Exception as exc:
            logger.info(
                "Failed to send preview to user=%s participant_id=%s bundle_id=%s error=%s",
                user_id,
                participant_id,
                bundle_id,
                str(exc),
            )
        await mark_preview_sent(
            pool=pool,
            participant_id=participant_id,
            preview_message_id=message_id,
            preview_sent_at=now_naive,
        )

    auto_confirm_at = now_local + timedelta(hours=2)
    schedule_bundle_auto_confirm(bundle_id=bundle_id, run_at=auto_confirm_at)
    logger.info("Preview sent bundle_id=%s auto_confirm_at=%s", bundle_id, auto_confirm_at)
    return True


async def confirm_participant_preview(pool: Pool, participant_id: int) -> bool:
    participant = await get_participant_with_bundle_channel(pool, participant_id)
    if not participant or participant["bundle_status"] != "full":
        return False
    now_naive = get_local_now().replace(tzinfo=None)
    updated = await confirm_preview(pool, participant_id, now_naive)
    return updated is not None


async def cancel_participant_preview(pool: Pool, participant_id: int) -> int | None:
    participant = await get_participant_with_bundle_channel(pool, participant_id)
    if not participant or participant["status"] != "active" or participant["bundle_status"] != "full":
        return None

    bundle_id = int(participant["bundle_id"])
    await set_participant_status(pool, participant_id, status="cancelled", confirmed=False)
    await update_bundle_status(pool, bundle_id, "open")
    await reset_preview_confirmations(pool, bundle_id)
    logger.info("Participant cancelled preview participant_id=%s bundle_id=%s", participant_id, bundle_id)
    return bundle_id


async def auto_confirm_pending_previews(pool: Pool, bundle_id: int) -> int:
    threshold = (get_local_now() - timedelta(hours=2)).replace(tzinfo=None)
    pending = await get_pending_preview_participants(pool, bundle_id, older_than=threshold)
    now_naive = get_local_now().replace(tzinfo=None)
    confirmed_count = 0
    for participant in pending:
        updated = await confirm_preview(pool, int(participant["id"]), now_naive)
        if updated:
            confirmed_count += 1
    if confirmed_count:
        logger.info("Auto-confirmed previews bundle_id=%s count=%s", bundle_id, confirmed_count)
    return confirmed_count


async def bundle_all_previews_confirmed(pool: Pool, bundle_id: int) -> bool:
    bundle = await get_bundle_by_id(pool, bundle_id)
    if not bundle:
        return False
    participants = await get_active_participants_with_channels(pool, bundle_id)
    if len(participants) != int(bundle["slots"]):
        return False
    return all(bool(participant["preview_confirmed"]) for participant in participants)


async def try_move_bundle_to_scheduled(pool: Pool, bundle_id: int) -> bool:
    if not await bundle_ready_for_preview(pool, bundle_id):
        return False
    if not await bundle_all_previews_confirmed(pool, bundle_id):
        return False

    bundle = await update_bundle_status(pool, bundle_id, "scheduled")
    if not bundle:
        return False

    run_at = bundle["scheduled_at"]
    schedule_bundle_publish(bundle_id=bundle_id, run_at=run_at)
    logger.info("Bundle moved to scheduled bundle_id=%s run_at=%s", bundle_id, run_at)
    return True


async def try_start_preview_for_bundle(bot: Bot, pool: Pool, bundle_id: int) -> bool:
    bundle = await get_bundle_by_id(pool, bundle_id)
    if not bundle:
        return False

    if bundle["status"] == "open":
        if await bundle_ready_for_preview(pool, bundle_id):
            await update_bundle_status(pool, bundle_id, "full")
            logger.info("Bundle became full bundle_id=%s", bundle_id)

    bundle = await get_bundle_by_id(pool, bundle_id)
    if not bundle or bundle["status"] != "full":
        return False

    active_participants = await get_active_participants_with_channels(pool, bundle_id)
    if active_participants and all(participant["preview_sent_at"] is not None for participant in active_participants):
        return False
    return await send_bundle_preview(bot, pool, bundle_id)
