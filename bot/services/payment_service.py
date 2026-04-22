import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from asyncpg import Pool

from config import settings
from repositories.bundles import (
    bundle_has_free_slots,
    bundle_paid_slot_taken,
    count_active_bundle_participants,
    get_bundle_with_creator,
    update_bundle_status,
)
from repositories.participants import (
    activate_paid_participant,
    cancel_participant,
    channel_already_in_bundle,
    channel_has_bundle_at_time,
    count_paid_participants_for_bundle,
    create_participant,
    get_participant_by_id,
    get_user_participant_for_bundle,
)
from repositories.payments import (
    create_payment_record,
    get_expired_pending_payments,
    get_latest_pending_payment_for_participant,
    get_payment_by_id,
    get_payment_by_yukassa_id,
    mark_payment_cancelled,
    mark_payment_expired,
    mark_payment_succeeded,
    update_payment_status,
)
from services.yookassa import YooKassaError, create_payment, get_payment, parse_webhook


logger = logging.getLogger(__name__)


class PaymentServiceError(RuntimeError):
    pass


@dataclass
class PaidParticipationResult:
    participant_id: int
    payment_id: int
    payment_url: str
    amount: int
    expires_at: datetime
    reused_existing: bool = False


def _calc_commission(amount: int) -> tuple[int, int]:
    commission = round(amount * (settings.service_commission_percent / 100))
    net_amount = amount - commission
    return int(commission), int(net_amount)


async def _ensure_bundle_open_and_paid_slot(pool: Pool, bundle_id: int) -> tuple[dict, int]:
    bundle = await get_bundle_with_creator(pool, bundle_id)
    if not bundle or bundle["status"] != "open":
        raise PaymentServiceError("Подборка недоступна")
    if not bundle["has_paid_slot"]:
        raise PaymentServiceError("В этой подборке нет платного места")
    amount = int(bundle["paid_slot_price"] or 0)
    if amount <= 0:
        raise PaymentServiceError("Для этой подборки не задана цена платного места")
    return bundle, amount


async def create_paid_participation_request(
    *,
    pool: Pool,
    bundle_id: int,
    channel_id: int,
    ad_text: str,
) -> PaidParticipationResult:
    bundle, amount = await _ensure_bundle_open_and_paid_slot(pool, bundle_id)

    if await channel_already_in_bundle(pool, bundle_id, channel_id):
        raise PaymentServiceError("Этот канал уже участвует в подборке")
    if await channel_has_bundle_at_time(pool, channel_id, bundle["scheduled_at"]):
        raise PaymentServiceError("У этого канала уже есть участие в подборке на это время")
    if not await bundle_has_free_slots(pool, bundle_id):
        raise PaymentServiceError("Похоже, эта подборка уже заполнилась. Обнови список и выбери другую")
    if await bundle_paid_slot_taken(pool, bundle_id):
        raise PaymentServiceError("Платное место уже занято")

    existing_participant = await get_user_participant_for_bundle(
        pool=pool,
        bundle_id=bundle_id,
        channel_id=channel_id,
        participant_type="paid",
    )
    if existing_participant and existing_participant["status"] == "awaiting_payment":
        existing_payment = await get_latest_pending_payment_for_participant(pool, existing_participant["id"])
        if existing_payment and existing_payment["payment_expires_at"] and existing_payment["payment_expires_at"] > datetime.utcnow():
            if not existing_payment["payment_url"]:
                raise PaymentServiceError("Не удалось восстановить ссылку на оплату")
            logger.info(
                "Reusing pending payment participant=%s payment=%s",
                existing_participant["id"],
                existing_payment["id"],
            )
            return PaidParticipationResult(
                participant_id=int(existing_participant["id"]),
                payment_id=int(existing_payment["id"]),
                payment_url=str(existing_payment["payment_url"]),
                amount=int(existing_payment["amount"]),
                expires_at=existing_payment["payment_expires_at"],
                reused_existing=True,
            )

    participant = await create_participant(
        pool=pool,
        bundle_id=bundle_id,
        channel_id=channel_id,
        participant_type="paid",
        ad_text=ad_text,
        confirmed=False,
        status="awaiting_payment",
    )
    if not participant:
        raise PaymentServiceError("Не удалось создать платную заявку")

    paid_reservations = await count_paid_participants_for_bundle(pool, bundle_id)
    if paid_reservations > 1:
        await cancel_participant(pool, participant["id"])
        logger.info("Paid slot race conflict bundle=%s participant=%s", bundle_id, participant["id"])
        raise PaymentServiceError("Платное место уже занято")

    commission, net_amount = _calc_commission(amount)
    payment_expires_at = datetime.utcnow() + timedelta(minutes=settings.payment_timeout_minutes)
    idempotence_key = str(uuid.uuid4())

    try:
        response = await create_payment(
            amount_rub=amount,
            description=f"Платное участие в подборке #{bundle_id}",
            metadata={
                "bundle_id": str(bundle_id),
                "participant_id": str(participant["id"]),
                "channel_id": str(channel_id),
            },
            idempotence_key=idempotence_key,
        )
    except YooKassaError as exc:
        await cancel_participant(pool, participant["id"])
        logger.info("YooKassa create payment failed bundle=%s participant=%s error=%s", bundle_id, participant["id"], str(exc))
        raise PaymentServiceError("Не удалось создать платёж. Попробуй ещё раз.") from exc

    payment_url = (response.get("confirmation") or {}).get("confirmation_url")
    yukassa_id = response.get("id")
    external_status = response.get("status") or "pending"
    if not payment_url or not yukassa_id:
        await cancel_participant(pool, participant["id"])
        raise PaymentServiceError("Не удалось получить ссылку на оплату")

    payment = await create_payment_record(
        pool=pool,
        participant_id=participant["id"],
        amount=amount,
        commission=commission,
        net_amount=net_amount,
        status="pending",
        yukassa_id=yukassa_id,
        payment_url=payment_url,
        idempotence_key=idempotence_key,
        external_status=external_status,
        payment_expires_at=payment_expires_at,
        raw_payload=response,
    )
    if not payment:
        await cancel_participant(pool, participant["id"])
        raise PaymentServiceError("Не удалось сохранить платёж")

    logger.info("Paid request created bundle=%s participant=%s payment=%s yukassa_id=%s", bundle_id, participant["id"], payment["id"], yukassa_id)
    return PaidParticipationResult(
        participant_id=int(participant["id"]),
        payment_id=int(payment["id"]),
        payment_url=str(payment_url),
        amount=amount,
        expires_at=payment_expires_at,
        reused_existing=False,
    )


async def _activate_participant_if_needed(pool: Pool, payment_row) -> tuple[bool, Optional[int], Optional[int]]:
    participant_id = int(payment_row["participant_id"])
    participant = await get_participant_by_id(pool, participant_id)
    if not participant:
        return False, None, None

    activated_now = False
    if participant["status"] != "active":
        updated = await activate_paid_participant(pool, participant_id)
        activated_now = updated is not None

    bundle = await get_bundle_with_creator(pool, participant["bundle_id"])
    if bundle:
        active_count = await count_active_bundle_participants(pool, participant["bundle_id"])
        if active_count >= int(bundle["slots"]):
            await update_bundle_status(pool, participant["bundle_id"], "full")
    return activated_now, int(participant["bundle_id"]), participant_id


async def check_and_activate_payment(pool: Pool, payment_id: int) -> tuple[str, Optional[int], Optional[int], bool]:
    payment = await get_payment_by_id(pool, payment_id)
    if not payment:
        raise PaymentServiceError("Платёж не найден")

    if payment["status"] == "succeeded":
        activated_now, bundle_id, participant_id = await _activate_participant_if_needed(pool, payment)
        return "succeeded", bundle_id, participant_id, activated_now
    if payment["status"] in {"cancelled", "expired", "failed"}:
        return str(payment["status"]), None, None, False

    try:
        response = await get_payment(str(payment["yukassa_id"]))
    except YooKassaError as exc:
        logger.info("YooKassa get payment failed payment_id=%s error=%s", payment_id, str(exc))
        raise PaymentServiceError("Не удалось проверить оплату. Попробуй ещё раз.") from exc

    external_status = response.get("status") or "pending"
    if external_status == "succeeded":
        updated = await mark_payment_succeeded(pool, payment_id, external_status=external_status, raw_payload=response)
        if not updated:
            raise PaymentServiceError("Не удалось обновить статус платежа")
        activated_now, bundle_id, participant_id = await _activate_participant_if_needed(pool, updated)
        logger.info("Payment succeeded payment_id=%s", payment_id)
        return "succeeded", bundle_id, participant_id, activated_now

    if external_status in {"canceled", "cancelled"}:
        await mark_payment_cancelled(pool, payment_id, external_status=external_status, raw_payload=response)
        await cancel_participant(pool, payment["participant_id"])
        return "cancelled", None, None, False

    await update_payment_status(pool, payment_id, status="pending", external_status=external_status, raw_payload=response)
    return "pending", None, None, False


async def cancel_paid_participation(pool: Pool, payment_id: int) -> bool:
    payment = await get_payment_by_id(pool, payment_id)
    if not payment:
        return False
    if payment["status"] == "succeeded":
        return False

    await mark_payment_cancelled(pool, payment_id, external_status=payment["external_status"], raw_payload=payment["raw_payload"])
    await cancel_participant(pool, payment["participant_id"])
    logger.info("Payment cancelled payment_id=%s participant=%s", payment_id, payment["participant_id"])
    return True


async def expire_stale_payments(pool: Pool) -> int:
    expired = await get_expired_pending_payments(pool)
    count = 0
    for payment in expired:
        await mark_payment_expired(pool, payment["id"])
        await cancel_participant(pool, payment["participant_id"])
        logger.info("Payment expired payment_id=%s participant=%s", payment["id"], payment["participant_id"])
        count += 1
    return count


async def process_yookassa_webhook(pool: Pool, payload: dict) -> tuple[str, Optional[int]]:
    parsed = parse_webhook(payload)
    yukassa_id = parsed.get("yukassa_id")
    status = parsed.get("status")
    if not yukassa_id:
        return "ignored", None

    payment = await get_payment_by_yukassa_id(pool, str(yukassa_id))
    if not payment:
        return "not_found", None

    if payment["status"] == "succeeded":
        logger.info("Duplicate webhook for succeeded payment_id=%s", payment["id"])
        return "already_succeeded", int(payment["id"])

    if status == "succeeded":
        updated = await mark_payment_succeeded(pool, payment["id"], external_status=status, raw_payload=parsed["raw"])
        if updated:
            await _activate_participant_if_needed(pool, updated)
        return "succeeded", int(payment["id"])

    if status in {"canceled", "cancelled"}:
        await mark_payment_cancelled(pool, payment["id"], external_status=status, raw_payload=parsed["raw"])
        await cancel_participant(pool, payment["participant_id"])
        return "cancelled", int(payment["id"])

    await update_payment_status(
        pool,
        payment["id"],
        status="pending",
        external_status=status or "pending",
        raw_payload=parsed["raw"],
    )
    return "pending", int(payment["id"])
