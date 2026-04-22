from typing import Optional

from asyncpg import Pool, Record


async def create_violation(
    pool: Pool,
    channel_id: int,
    violation_type: str,
    bundle_id: int | None = None,
    participant_id: int | None = None,
    details: str | None = None,
) -> Optional[Record]:
    query = """
    INSERT INTO channel_violations (
        channel_id,
        bundle_id,
        participant_id,
        violation_type,
        details
    )
    VALUES ($1, $2, $3, $4, $5)
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(
            query,
            channel_id,
            bundle_id,
            participant_id,
            violation_type,
            details,
        )


async def get_channel_violations(pool: Pool, channel_id: int) -> list[Record]:
    query = """
    SELECT *
    FROM channel_violations
    WHERE channel_id = $1
    ORDER BY created_at DESC, id DESC
    """
    async with pool.acquire() as connection:
        return await connection.fetch(query, channel_id)


async def count_channel_violations(pool: Pool, channel_id: int) -> int:
    query = """
    SELECT COUNT(*)::INT AS cnt
    FROM channel_violations
    WHERE channel_id = $1
    """
    async with pool.acquire() as connection:
        row = await connection.fetchrow(query, channel_id)
    return int(row["cnt"]) if row else 0


async def get_channel_violations_limited(pool: Pool, channel_id: int, limit: int = 20) -> list[Record]:
    query = """
    SELECT *
    FROM channel_violations
    WHERE channel_id = $1
    ORDER BY created_at DESC, id DESC
    LIMIT $2
    """
    async with pool.acquire() as connection:
        return await connection.fetch(query, channel_id, limit)
