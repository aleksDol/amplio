from datetime import datetime
from typing import Optional

from asyncpg import Pool, Record


async def create_post_record(
    pool: Pool,
    bundle_id: int,
    channel_id: int,
    message_id: int | None,
    status: str,
    published_at: datetime | None,
    delete_at: datetime | None,
    error_text: str | None = None,
) -> Optional[Record]:
    query = """
    INSERT INTO posts (
        bundle_id,
        channel_id,
        message_id,
        status,
        published_at,
        delete_at,
        error_text
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7)
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(
            query,
            bundle_id,
            channel_id,
            message_id,
            status,
            published_at,
            delete_at,
            error_text,
        )


async def get_posts_for_bundle(pool: Pool, bundle_id: int) -> list[Record]:
    query = """
    SELECT
        p.*,
        c.telegram_chat_id,
        c.owner_id,
        c.username AS channel_username,
        c.title AS channel_title
    FROM posts p
    JOIN channels c ON c.id = p.channel_id
    WHERE p.bundle_id = $1
    ORDER BY p.id ASC
    """
    async with pool.acquire() as connection:
        return await connection.fetch(query, bundle_id)


async def get_active_posts_for_bundle(pool: Pool, bundle_id: int) -> list[Record]:
    query = """
    SELECT
        p.*,
        c.telegram_chat_id,
        c.owner_id,
        c.username AS channel_username,
        c.title AS channel_title
    FROM posts p
    JOIN channels c ON c.id = p.channel_id
    WHERE p.bundle_id = $1
      AND p.status = 'active'
      AND p.message_id IS NOT NULL
      AND p.deleted_at IS NULL
    ORDER BY p.id ASC
    """
    async with pool.acquire() as connection:
        return await connection.fetch(query, bundle_id)


async def get_posts_for_monitoring(pool: Pool) -> list[Record]:
    query = """
    SELECT
        p.*,
        c.telegram_chat_id,
        c.owner_id,
        c.username AS channel_username,
        c.title AS channel_title,
        b.status AS bundle_status
    FROM posts p
    JOIN channels c ON c.id = p.channel_id
    JOIN bundles b ON b.id = p.bundle_id
    WHERE p.status = 'active'
      AND p.deleted_at IS NULL
      AND b.status IN ('published', 'partially_published', 'published_changed')
    ORDER BY p.bundle_id ASC, p.id ASC
    """
    async with pool.acquire() as connection:
        return await connection.fetch(query)


async def get_posts_by_channel(pool: Pool, channel_id: int, only_active: bool = True) -> list[Record]:
    query = """
    SELECT *
    FROM posts
    WHERE channel_id = $1
      AND ($2::bool = FALSE OR status = 'active')
    ORDER BY id DESC
    """
    async with pool.acquire() as connection:
        return await connection.fetch(query, channel_id, only_active)


async def mark_post_status(
    pool: Pool,
    post_id: int,
    status: str,
    error_text: str | None = None,
) -> Optional[Record]:
    query = """
    UPDATE posts
    SET
        status = $2,
        error_text = COALESCE($3, error_text)
    WHERE id = $1
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, post_id, status, error_text)


async def mark_post_deleted(
    pool: Pool,
    post_id: int,
    deleted_at: datetime,
    status: str = "deleted",
    error_text: str | None = None,
) -> Optional[Record]:
    query = """
    UPDATE posts
    SET
        status = $2,
        deleted_at = $3,
        error_text = COALESCE($4, error_text)
    WHERE id = $1
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, post_id, status, deleted_at, error_text)


async def mark_post_checked(pool: Pool, post_id: int, checked_at: datetime) -> Optional[Record]:
    query = """
    UPDATE posts
    SET checked_at = $2
    WHERE id = $1
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, post_id, checked_at)


async def update_post_status(
    pool: Pool,
    post_id: int,
    status: str,
    error_text: str | None = None,
    deleted_at: datetime | None = None,
) -> Optional[Record]:
    query = """
    UPDATE posts
    SET
        status = $2,
        error_text = COALESCE($3, error_text),
        deleted_at = COALESCE($4, deleted_at)
    WHERE id = $1
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, post_id, status, error_text, deleted_at)
