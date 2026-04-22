from datetime import datetime
from typing import Optional

from asyncpg import Pool, Record


async def create_participant(
    pool: Pool,
    bundle_id: int,
    channel_id: int,
    ad_text: str,
    participant_type: str = "free",
    confirmed: bool = True,
    status: str = "active",
) -> Optional[Record]:
    query = """
    INSERT INTO participants (
        bundle_id,
        channel_id,
        type,
        ad_text,
        confirmed,
        status
    )
    VALUES ($1, $2, $3, $4, $5, $6)
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(
            query,
            bundle_id,
            channel_id,
            participant_type,
            ad_text,
            confirmed,
            status,
        )


async def count_bundle_participants(pool: Pool, bundle_id: int) -> int:
    query = """
    SELECT COUNT(*)::INT AS cnt
    FROM participants
    WHERE bundle_id = $1
      AND status = 'active'
    """
    async with pool.acquire() as connection:
        row = await connection.fetchrow(query, bundle_id)
    return int(row["cnt"]) if row else 0


async def get_channel_participation_in_bundle(
    pool: Pool,
    bundle_id: int,
    channel_id: int,
) -> Optional[Record]:
    query = """
    SELECT *
    FROM participants
    WHERE bundle_id = $1
      AND channel_id = $2
      AND status IN ('active', 'awaiting_payment')
    LIMIT 1
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, bundle_id, channel_id)


async def channel_already_in_bundle(pool: Pool, bundle_id: int, channel_id: int) -> bool:
    row = await get_channel_participation_in_bundle(pool, bundle_id, channel_id)
    return row is not None


async def channel_has_bundle_at_time(pool: Pool, channel_id: int, scheduled_at) -> bool:
    query = """
    SELECT 1
    FROM participants p
    JOIN bundles b ON b.id = p.bundle_id
    WHERE p.channel_id = $1
      AND b.scheduled_at = $2
      AND p.status IN ('active', 'awaiting_payment')
      AND b.status IN ('open', 'full', 'scheduled')
    LIMIT 1
    """
    async with pool.acquire() as connection:
        row = await connection.fetchrow(query, channel_id, scheduled_at)
    return row is not None


async def get_bundle_participating_channel_ids(pool: Pool, bundle_id: int) -> list[int]:
    query = """
    SELECT channel_id
    FROM participants
    WHERE bundle_id = $1
      AND status IN ('active', 'awaiting_payment')
    """
    async with pool.acquire() as connection:
        rows = await connection.fetch(query, bundle_id)
    return [int(row["channel_id"]) for row in rows]


async def count_paid_participants_for_bundle(pool: Pool, bundle_id: int) -> int:
    query = """
    SELECT COUNT(*)::INT AS cnt
    FROM participants
    WHERE bundle_id = $1
      AND type = 'paid'
      AND status IN ('active', 'awaiting_payment')
    """
    async with pool.acquire() as connection:
        row = await connection.fetchrow(query, bundle_id)
    return int(row["cnt"]) if row else 0


async def get_participant_by_id(pool: Pool, participant_id: int) -> Optional[Record]:
    query = """
    SELECT *
    FROM participants
    WHERE id = $1
    LIMIT 1
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, participant_id)


async def get_user_participant_for_bundle(
    pool: Pool,
    bundle_id: int,
    channel_id: int,
    participant_type: Optional[str] = None,
) -> Optional[Record]:
    query = """
    SELECT *
    FROM participants
    WHERE bundle_id = $1
      AND channel_id = $2
      AND ($3::text IS NULL OR type = $3)
    ORDER BY id DESC
    LIMIT 1
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, bundle_id, channel_id, participant_type)


async def set_participant_status(
    pool: Pool,
    participant_id: int,
    status: str,
    confirmed: Optional[bool] = None,
) -> Optional[Record]:
    query = """
    UPDATE participants
    SET
        status = $2,
        confirmed = COALESCE($3, confirmed)
    WHERE id = $1
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, participant_id, status, confirmed)


async def cancel_participant(pool: Pool, participant_id: int) -> Optional[Record]:
    return await set_participant_status(pool, participant_id, status="cancelled", confirmed=False)


async def activate_paid_participant(pool: Pool, participant_id: int) -> Optional[Record]:
    return await set_participant_status(pool, participant_id, status="active", confirmed=True)


async def count_participants_by_status(pool: Pool, bundle_id: int, status: str) -> int:
    query = """
    SELECT COUNT(*)::INT AS cnt
    FROM participants
    WHERE bundle_id = $1
      AND status = $2
    """
    async with pool.acquire() as connection:
        row = await connection.fetchrow(query, bundle_id, status)
    return int(row["cnt"]) if row else 0


async def get_active_participants_with_channels(pool: Pool, bundle_id: int) -> list[Record]:
    query = """
    SELECT
        p.*,
        c.owner_id,
        c.username AS channel_username,
        c.title AS channel_title,
        c.telegram_chat_id
    FROM participants p
    JOIN channels c ON c.id = p.channel_id
    WHERE p.bundle_id = $1
      AND p.status = 'active'
    ORDER BY p.id ASC
    """
    async with pool.acquire() as connection:
        return await connection.fetch(query, bundle_id)


async def get_user_pending_participations(pool: Pool, user_id: int) -> list[Record]:
    query = """
    SELECT
        p.id AS participant_id,
        p.bundle_id,
        p.channel_id,
        p.type AS participant_type,
        p.status AS participant_status,
        c.username AS participant_channel_username,
        c.title AS participant_channel_title,
        b.niche,
        b.scheduled_at,
        b.slots,
        b.has_paid_slot,
        b.paid_slot_price,
        b.creator_channel_id,
        creator.username AS creator_username,
        creator.title AS creator_title,
        (
            SELECT COUNT(*)::INT
            FROM participants p2
            WHERE p2.bundle_id = b.id
              AND p2.status IN ('active', 'awaiting_payment')
        ) AS used_slots
    FROM participants p
    JOIN channels c ON c.id = p.channel_id
    JOIN bundles b ON b.id = p.bundle_id
    JOIN channels creator ON creator.id = b.creator_channel_id
    WHERE c.owner_id = $1
      AND p.status IN ('active', 'awaiting_payment')
      AND b.status = 'open'
    ORDER BY b.scheduled_at ASC, p.id ASC
    """
    async with pool.acquire() as connection:
        return await connection.fetch(query, user_id)


async def get_participant_with_bundle_channel(pool: Pool, participant_id: int) -> Optional[Record]:
    query = """
    SELECT
        p.*,
        b.id AS bundle_id,
        b.status AS bundle_status,
        b.scheduled_at,
        b.post_lifetime_hours,
        b.slots,
        c.owner_id,
        c.username AS channel_username,
        c.title AS channel_title
    FROM participants p
    JOIN bundles b ON b.id = p.bundle_id
    JOIN channels c ON c.id = p.channel_id
    WHERE p.id = $1
    LIMIT 1
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, participant_id)


async def mark_preview_sent(
    pool: Pool,
    participant_id: int,
    preview_message_id: int | None,
    preview_sent_at: datetime,
) -> Optional[Record]:
    query = """
    UPDATE participants
    SET
        preview_message_id = $2,
        preview_sent_at = $3,
        preview_confirmed = FALSE,
        preview_confirmed_at = NULL
    WHERE id = $1
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, participant_id, preview_message_id, preview_sent_at)


async def confirm_preview(
    pool: Pool,
    participant_id: int,
    confirmed_at: datetime,
) -> Optional[Record]:
    query = """
    UPDATE participants
    SET
        preview_confirmed = TRUE,
        preview_confirmed_at = $2
    WHERE id = $1
      AND status = 'active'
      AND preview_sent_at IS NOT NULL
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, participant_id, confirmed_at)


async def reset_preview_confirmations(pool: Pool, bundle_id: int) -> str:
    query = """
    UPDATE participants
    SET
        preview_confirmed = FALSE,
        preview_confirmed_at = NULL,
        preview_sent_at = NULL,
        preview_message_id = NULL
    WHERE bundle_id = $1
      AND status = 'active'
    """
    async with pool.acquire() as connection:
        return await connection.execute(query, bundle_id)


async def get_pending_preview_participants(
    pool: Pool,
    bundle_id: int,
    older_than: datetime | None = None,
) -> list[Record]:
    query = """
    SELECT *
    FROM participants
    WHERE bundle_id = $1
      AND status = 'active'
      AND COALESCE(preview_confirmed, FALSE) = FALSE
      AND preview_sent_at IS NOT NULL
      AND ($2::timestamp IS NULL OR preview_sent_at <= $2)
    ORDER BY id ASC
    """
    async with pool.acquire() as connection:
        return await connection.fetch(query, bundle_id, older_than)


async def get_active_participant_by_channel_and_bundle(
    pool: Pool,
    channel_id: int,
    bundle_id: int,
) -> Optional[Record]:
    query = """
    SELECT *
    FROM participants
    WHERE channel_id = $1
      AND bundle_id = $2
      AND status = 'active'
    LIMIT 1
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, channel_id, bundle_id)


async def remove_participant_from_bundle(
    pool: Pool,
    participant_id: int,
    reason: str,
    removed_at: datetime,
) -> Optional[Record]:
    query = """
    UPDATE participants
    SET
        status = 'removed',
        confirmed = FALSE,
        removed_reason = $2,
        removed_at = $3
    WHERE id = $1
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, participant_id, reason, removed_at)


async def count_active_participants(pool: Pool, bundle_id: int) -> int:
    return await count_participants_by_status(pool, bundle_id, "active")
