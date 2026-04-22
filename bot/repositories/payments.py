from datetime import datetime
from typing import Optional

from asyncpg import Pool, Record


async def create_payment_record(
    pool: Pool,
    participant_id: int,
    amount: int,
    commission: int,
    net_amount: int,
    status: str,
    yukassa_id: str,
    payment_url: str,
    idempotence_key: str,
    external_status: str,
    payment_expires_at: datetime,
    raw_payload: dict | None,
) -> Optional[Record]:
    query = """
    INSERT INTO payments (
        participant_id,
        amount,
        commission,
        net_amount,
        status,
        yukassa_id,
        payment_url,
        idempotence_key,
        external_status,
        payment_expires_at,
        raw_payload
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb)
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(
            query,
            participant_id,
            amount,
            commission,
            net_amount,
            status,
            yukassa_id,
            payment_url,
            idempotence_key,
            external_status,
            payment_expires_at,
            raw_payload,
        )


async def get_payment_by_id(pool: Pool, payment_id: int) -> Optional[Record]:
    query = "SELECT * FROM payments WHERE id = $1 LIMIT 1"
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, payment_id)


async def get_payment_by_yukassa_id(pool: Pool, yukassa_id: str) -> Optional[Record]:
    query = "SELECT * FROM payments WHERE yukassa_id = $1 LIMIT 1"
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, yukassa_id)


async def get_latest_pending_payment_for_participant(pool: Pool, participant_id: int) -> Optional[Record]:
    query = """
    SELECT *
    FROM payments
    WHERE participant_id = $1
      AND status = 'pending'
    ORDER BY created_at DESC, id DESC
    LIMIT 1
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, participant_id)


async def update_payment_status(
    pool: Pool,
    payment_id: int,
    status: str,
    external_status: Optional[str] = None,
    raw_payload: Optional[dict] = None,
) -> Optional[Record]:
    query = """
    UPDATE payments
    SET
        status = $2,
        external_status = COALESCE($3, external_status),
        raw_payload = COALESCE($4::jsonb, raw_payload)
    WHERE id = $1
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, payment_id, status, external_status, raw_payload)


async def mark_payment_succeeded(
    pool: Pool,
    payment_id: int,
    external_status: Optional[str] = None,
    raw_payload: Optional[dict] = None,
) -> Optional[Record]:
    query = """
    UPDATE payments
    SET
        status = 'succeeded',
        external_status = COALESCE($2, external_status),
        raw_payload = COALESCE($3::jsonb, raw_payload),
        paid_at = NOW()
    WHERE id = $1
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, payment_id, external_status, raw_payload)


async def mark_payment_cancelled(
    pool: Pool,
    payment_id: int,
    external_status: Optional[str] = None,
    raw_payload: Optional[dict] = None,
) -> Optional[Record]:
    query = """
    UPDATE payments
    SET
        status = 'cancelled',
        external_status = COALESCE($2, external_status),
        raw_payload = COALESCE($3::jsonb, raw_payload),
        cancelled_at = NOW()
    WHERE id = $1
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, payment_id, external_status, raw_payload)


async def mark_payment_expired(pool: Pool, payment_id: int) -> Optional[Record]:
    query = """
    UPDATE payments
    SET status = 'expired'
    WHERE id = $1
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, payment_id)


async def get_expired_pending_payments(pool: Pool) -> list[Record]:
    query = """
    SELECT *
    FROM payments
    WHERE status = 'pending'
      AND payment_expires_at IS NOT NULL
      AND payment_expires_at < NOW()
    """
    async with pool.acquire() as connection:
        return await connection.fetch(query)


async def get_success_payments_summary(pool: Pool) -> Record:
    query = """
    SELECT
        COUNT(*)::INT AS payments_count,
        COALESCE(SUM(amount), 0)::BIGINT AS total_amount,
        COALESCE(SUM(commission), 0)::BIGINT AS total_commission
    FROM payments
    WHERE status = 'succeeded'
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query)


async def get_total_commission_amount(pool: Pool) -> int:
    query = """
    SELECT COALESCE(SUM(commission), 0)::BIGINT AS total_commission
    FROM payments
    WHERE status = 'succeeded'
    """
    async with pool.acquire() as connection:
        row = await connection.fetchrow(query)
    return int(row["total_commission"]) if row else 0
