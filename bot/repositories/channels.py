from typing import Optional

from asyncpg import Pool, Record


async def get_channel_by_username(pool: Pool, username: str) -> Optional[Record]:
    query = """
    SELECT *
    FROM channels
    WHERE lower(username) = lower($1)
    LIMIT 1
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, username)


async def get_channel_by_chat_id(pool: Pool, telegram_channel_id: int) -> Optional[Record]:
    query = """
    SELECT *
    FROM channels
    WHERE telegram_chat_id = $1
    LIMIT 1
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, telegram_channel_id)


async def upsert_user(pool: Pool, telegram_id: int, username: Optional[str]) -> None:
    query = """
    INSERT INTO users (telegram_id, username)
    VALUES ($1, $2)
    ON CONFLICT (telegram_id) DO UPDATE
    SET username = EXCLUDED.username
    """
    async with pool.acquire() as connection:
        await connection.execute(query, telegram_id, username)


async def create_channel(
    pool: Pool,
    owner_id: int,
    telegram_chat_id: int,
    username: str,
    title: str,
) -> Optional[Record]:
    query = """
    INSERT INTO channels (
        owner_id,
        telegram_chat_id,
        username,
        title,
        subscribers,
        niche,
        is_verified,
        bot_is_admin
    )
    VALUES ($1, $2, $3, $4, NULL, NULL, TRUE, TRUE)
    ON CONFLICT (telegram_chat_id) DO NOTHING
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(
            query,
            owner_id,
            telegram_chat_id,
            username,
            title,
        )


async def get_channel_by_id(pool: Pool, channel_id: int) -> Optional[Record]:
    query = """
    SELECT *
    FROM channels
    WHERE id = $1
    LIMIT 1
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, channel_id)


async def get_user_channels(pool: Pool, owner_id: int) -> list[Record]:
    query = """
    SELECT *
    FROM channels
    WHERE owner_id = $1
    ORDER BY created_at DESC, id DESC
    """
    async with pool.acquire() as connection:
        return await connection.fetch(query, owner_id)


async def get_user_ready_channels(pool: Pool, owner_id: int) -> list[Record]:
    query = """
    SELECT *
    FROM channels
    WHERE owner_id = $1
      AND bot_is_admin = TRUE
      AND is_verified = TRUE
      AND niche IS NOT NULL
      AND subscribers IS NOT NULL
    ORDER BY created_at DESC, id DESC
    """
    async with pool.acquire() as connection:
        return await connection.fetch(query, owner_id)


async def get_ready_channels_by_niche(pool: Pool, niche: str) -> list[Record]:
    query = """
    SELECT *
    FROM channels
    WHERE bot_is_admin = TRUE
      AND is_verified = TRUE
      AND niche = $1
      AND subscribers IS NOT NULL
    ORDER BY id ASC
    """
    async with pool.acquire() as connection:
        return await connection.fetch(query, niche)


async def update_channel_niche(pool: Pool, channel_id: int, niche: str) -> Optional[Record]:
    query = """
    UPDATE channels
    SET niche = $2
    WHERE id = $1
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, channel_id, niche)


async def update_channel_subscribers(
    pool: Pool,
    channel_id: int,
    subscribers: int,
    min_subscribers: int,
    max_subscribers: int,
) -> Optional[Record]:
    query = """
    UPDATE channels
    SET
        subscribers = $2,
        min_free_match_subscribers = $3,
        max_free_match_subscribers = $4,
        last_subscribers_updated_at = CURRENT_TIMESTAMP
    WHERE id = $1
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(
            query,
            channel_id,
            subscribers,
            min_subscribers,
            max_subscribers,
        )


async def get_channel_rating(pool: Pool, channel_id: int) -> Optional[float]:
    query = """
    SELECT rating
    FROM channels
    WHERE id = $1
    LIMIT 1
    """
    async with pool.acquire() as connection:
        row = await connection.fetchrow(query, channel_id)
    if not row:
        return None
    return float(row["rating"] or 0.0)


async def update_channel_rating(pool: Pool, channel_id: int, new_rating: float) -> Optional[Record]:
    query = """
    UPDATE channels
    SET
        rating = $2,
        last_rating_update_at = CURRENT_TIMESTAMP
    WHERE id = $1
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, channel_id, new_rating)


async def increment_completed_bundles_count(pool: Pool, channel_id: int) -> Optional[Record]:
    query = """
    UPDATE channels
    SET
        completed_bundles_count = completed_bundles_count + 1,
        last_rating_update_at = CURRENT_TIMESTAMP
    WHERE id = $1
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, channel_id)


async def increment_violations_count(pool: Pool, channel_id: int) -> Optional[Record]:
    query = """
    UPDATE channels
    SET
        violations_count = violations_count + 1,
        last_rating_update_at = CURRENT_TIMESTAMP
    WHERE id = $1
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, channel_id)


async def increment_cancelled_after_preview_count(pool: Pool, channel_id: int) -> Optional[Record]:
    query = """
    UPDATE channels
    SET
        cancelled_after_preview_count = cancelled_after_preview_count + 1,
        last_rating_update_at = CURRENT_TIMESTAMP
    WHERE id = $1
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, channel_id)


async def increment_publish_failures_count(pool: Pool, channel_id: int) -> Optional[Record]:
    query = """
    UPDATE channels
    SET
        publish_failures_count = publish_failures_count + 1,
        last_rating_update_at = CURRENT_TIMESTAMP
    WHERE id = $1
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, channel_id)


async def get_channels_by_ids(pool: Pool, channel_ids: list[int]) -> list[Record]:
    if not channel_ids:
        return []
    query = """
    SELECT *
    FROM channels
    WHERE id = ANY($1::int[])
    ORDER BY id ASC
    """
    async with pool.acquire() as connection:
        return await connection.fetch(query, channel_ids)
