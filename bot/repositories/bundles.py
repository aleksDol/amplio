from datetime import datetime
from typing import Iterable, Optional

from asyncpg import Pool, Record


async def create_bundle(
    pool: Pool,
    creator_channel_id: int,
    niche: str,
    scheduled_at: datetime,
    slots: int,
    has_paid_slot: bool,
    paid_slot_price: int | None,
    post_lifetime_hours: int,
) -> Optional[Record]:
    query = """
    INSERT INTO bundles (
        creator_channel_id,
        niche,
        scheduled_at,
        slots,
        has_paid_slot,
        paid_slot_price,
        post_lifetime_hours,
        status
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, 'open')
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(
            query,
            creator_channel_id,
            niche,
            scheduled_at,
            slots,
            has_paid_slot,
            paid_slot_price,
            post_lifetime_hours,
        )


async def get_bundle_by_id(pool: Pool, bundle_id: int) -> Optional[Record]:
    query = """
    SELECT *
    FROM bundles
    WHERE id = $1
    LIMIT 1
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, bundle_id)


async def get_open_bundles_by_creator(pool: Pool, creator_channel_id: int) -> list[Record]:
    query = """
    SELECT *
    FROM bundles
    WHERE creator_channel_id = $1
      AND status = 'open'
    ORDER BY scheduled_at ASC
    """
    async with pool.acquire() as connection:
        return await connection.fetch(query, creator_channel_id)


async def channel_has_bundle_at_time(
    pool: Pool,
    creator_channel_id: int,
    scheduled_at: datetime,
) -> bool:
    query = """
    SELECT 1
    FROM bundles
    WHERE creator_channel_id = $1
      AND scheduled_at = $2
      AND status IN ('open', 'full', 'scheduled')
    LIMIT 1
    """
    async with pool.acquire() as connection:
        row = await connection.fetchrow(query, creator_channel_id, scheduled_at)
    return row is not None


async def get_open_bundles_for_channel(pool: Pool, channel_id: int) -> list[Record]:
    query = """
    SELECT
        b.*,
        c.owner_id AS creator_owner_id,
        c.username AS creator_username,
        c.title AS creator_title,
        c.subscribers AS creator_subscribers
    FROM bundles b
    JOIN channels c ON c.id = b.creator_channel_id
    JOIN channels seeker ON seeker.id = $1
    WHERE b.status = 'open'
      AND b.niche = seeker.niche
      AND b.creator_channel_id <> $1
    ORDER BY b.scheduled_at ASC
    """
    async with pool.acquire() as connection:
        return await connection.fetch(query, channel_id)


async def get_bundle_with_creator(pool: Pool, bundle_id: int) -> Optional[Record]:
    query = """
    SELECT
        b.*,
        c.owner_id AS creator_owner_id,
        c.username AS creator_username,
        c.title AS creator_title,
        c.subscribers AS creator_subscribers
    FROM bundles b
    JOIN channels c ON c.id = b.creator_channel_id
    WHERE b.id = $1
    LIMIT 1
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, bundle_id)


async def get_bundle_with_creator_channel(pool: Pool, bundle_id: int) -> Optional[Record]:
    return await get_bundle_with_creator(pool, bundle_id)


async def count_active_bundle_participants(pool: Pool, bundle_id: int) -> int:
    query = """
    SELECT COUNT(*)::INT AS cnt
    FROM participants
    WHERE bundle_id = $1
      AND status = 'active'
    """
    async with pool.acquire() as connection:
        row = await connection.fetchrow(query, bundle_id)
    return int(row["cnt"]) if row else 0


async def get_bundle_active_participants_count(pool: Pool, bundle_id: int) -> int:
    return await count_active_bundle_participants(pool, bundle_id)


async def bundle_has_free_slots(pool: Pool, bundle_id: int) -> bool:
    query = """
    SELECT
        b.slots,
        (
            SELECT COUNT(*)::INT
            FROM participants p
            WHERE p.bundle_id = b.id
              AND p.status IN ('active', 'awaiting_payment')
        ) AS used_slots
    FROM bundles b
    WHERE b.id = $1
      AND b.status = 'open'
    LIMIT 1
    """
    async with pool.acquire() as connection:
        row = await connection.fetchrow(query, bundle_id)
    if not row:
        return False
    return int(row["used_slots"]) < int(row["slots"])


async def bundle_paid_slot_taken(pool: Pool, bundle_id: int) -> bool:
    query = """
    SELECT 1
    FROM participants
    WHERE bundle_id = $1
      AND type = 'paid'
      AND status IN ('active', 'awaiting_payment')
    LIMIT 1
    """
    async with pool.acquire() as connection:
        row = await connection.fetchrow(query, bundle_id)
    return row is not None


async def update_bundle_status(pool: Pool, bundle_id: int, status: str) -> Optional[Record]:
    query = """
    UPDATE bundles
    SET status = $2
    WHERE id = $1
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, bundle_id, status)


async def update_bundle_preview(
    pool: Pool,
    bundle_id: int,
    preview_text: str,
    preview_generated_at: datetime,
) -> Optional[Record]:
    query = """
    UPDATE bundles
    SET
        preview_text = $2,
        preview_generated_at = $3
    WHERE id = $1
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, bundle_id, preview_text, preview_generated_at)


async def update_bundle_publication_status(
    pool: Pool,
    bundle_id: int,
    status: str,
    published_at: datetime | None = None,
) -> Optional[Record]:
    query = """
    UPDATE bundles
    SET
        status = $2,
        published_at = COALESCE($3, published_at)
    WHERE id = $1
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, bundle_id, status, published_at)


async def mark_bundle_completed(
    pool: Pool,
    bundle_id: int,
    completed_at: datetime | None = None,
) -> Optional[Record]:
    query = """
    UPDATE bundles
    SET
        status = 'completed',
        completed_at = COALESCE($2, completed_at)
    WHERE id = $1
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, bundle_id, completed_at)


async def get_bundles_by_status(pool: Pool, statuses: Iterable[str]) -> list[Record]:
    query = """
    SELECT *
    FROM bundles
    WHERE status = ANY($1::text[])
    ORDER BY scheduled_at ASC NULLS LAST, id ASC
    """
    async with pool.acquire() as connection:
        return await connection.fetch(query, list(statuses))


async def mark_bundle_changed_after_publication(pool: Pool, bundle_id: int) -> Optional[Record]:
    query = """
    UPDATE bundles
    SET status = 'published_changed'
    WHERE id = $1
      AND status IN ('published', 'partially_published', 'published_changed')
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, bundle_id)


async def get_published_bundles_for_monitoring(pool: Pool) -> list[Record]:
    query = """
    SELECT *
    FROM bundles
    WHERE status IN ('published', 'partially_published', 'published_changed')
    ORDER BY published_at DESC NULLS LAST, id DESC
    """
    async with pool.acquire() as connection:
        return await connection.fetch(query)


async def update_bundle_last_checked(pool: Pool, bundle_id: int, checked_at: datetime) -> Optional[Record]:
    query = """
    UPDATE bundles
    SET last_checked_at = $2
    WHERE id = $1
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, bundle_id, checked_at)


async def completion_bonus_already_applied(pool: Pool, bundle_id: int) -> bool:
    query = """
    SELECT 1
    FROM bundle_completion_bonus_applied
    WHERE bundle_id = $1
    LIMIT 1
    """
    async with pool.acquire() as connection:
        row = await connection.fetchrow(query, bundle_id)
    return row is not None


async def mark_completion_bonus_applied(pool: Pool, bundle_id: int) -> None:
    query = """
    INSERT INTO bundle_completion_bonus_applied (bundle_id)
    VALUES ($1)
    ON CONFLICT (bundle_id) DO NOTHING
    """
    async with pool.acquire() as connection:
        await connection.execute(query, bundle_id)
