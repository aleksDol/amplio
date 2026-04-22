from typing import Optional

from asyncpg import Pool, Record


async def notification_already_sent(pool: Pool, bundle_id: int, user_telegram_id: int) -> bool:
    query = """
    SELECT 1
    FROM bundle_notifications
    WHERE bundle_id = $1
      AND user_telegram_id = $2
    LIMIT 1
    """
    async with pool.acquire() as connection:
        row = await connection.fetchrow(query, bundle_id, user_telegram_id)
    return row is not None


async def create_bundle_notification(
    pool: Pool,
    bundle_id: int,
    user_telegram_id: int,
    channel_id: Optional[int],
    notification_type: str,
) -> Optional[Record]:
    query = """
    INSERT INTO bundle_notifications (bundle_id, user_telegram_id, channel_id, notification_type)
    VALUES ($1, $2, $3, $4)
    ON CONFLICT (bundle_id, user_telegram_id) DO NOTHING
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(
            query,
            bundle_id,
            user_telegram_id,
            channel_id,
            notification_type,
        )


async def get_notified_users_for_bundle(pool: Pool, bundle_id: int) -> list[int]:
    query = """
    SELECT user_telegram_id
    FROM bundle_notifications
    WHERE bundle_id = $1
    """
    async with pool.acquire() as connection:
        rows = await connection.fetch(query, bundle_id)
    return [int(row["user_telegram_id"]) for row in rows]
