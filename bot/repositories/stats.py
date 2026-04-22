from asyncpg import Pool, Record


async def get_user_global_stats(pool: Pool, user_telegram_id: int) -> Record:
    query = """
    WITH user_channels AS (
        SELECT *
        FROM channels
        WHERE owner_id = $1
    ),
    participations AS (
        SELECT p.*, b.status AS bundle_status
        FROM participants p
        JOIN bundles b ON b.id = p.bundle_id
        JOIN user_channels uc ON uc.id = p.channel_id
    )
    SELECT
        (SELECT COUNT(*)::INT FROM user_channels) AS channels_count,
        (
            SELECT COUNT(*)::INT
            FROM user_channels
            WHERE bot_is_admin = TRUE
              AND is_verified = TRUE
              AND niche IS NOT NULL
              AND subscribers IS NOT NULL
        ) AS ready_channels_count,
        (
            SELECT COUNT(*)::INT
            FROM bundles b
            JOIN user_channels uc ON uc.id = b.creator_channel_id
        ) AS created_bundles_count,
        (SELECT COUNT(*)::INT FROM participations) AS participations_count,
        (
            SELECT COUNT(*)::INT
            FROM participations
            WHERE bundle_status = 'completed'
              AND status = 'active'
        ) AS completed_participations_count,
        (
            SELECT COALESCE(SUM(violations_count), 0)::INT
            FROM user_channels
        ) AS violations_count,
        (
            SELECT COUNT(*)::INT
            FROM participations
            WHERE type = 'paid'
        ) AS paid_participations_count,
        (
            SELECT COUNT(*)::INT
            FROM participations
            WHERE type = 'free'
        ) AS free_participations_count
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, user_telegram_id)


async def get_user_channels_stats(pool: Pool, user_telegram_id: int) -> list[Record]:
    query = """
    SELECT
        c.id,
        c.username,
        c.title,
        c.subscribers,
        c.rating,
        c.completed_bundles_count,
        c.violations_count,
        c.cancelled_after_preview_count,
        c.publish_failures_count,
        COALESCE(s.participations_count, 0)::INT AS participations_count,
        COALESCE(s.paid_participations_count, 0)::INT AS paid_participations_count,
        COALESCE(s.free_participations_count, 0)::INT AS free_participations_count,
        COALESCE(s.completed_participations_count, 0)::INT AS completed_participations_count,
        COALESCE(s.created_bundles_count, 0)::INT AS created_bundles_count
    FROM channels c
    LEFT JOIN (
        SELECT
            p.channel_id,
            COUNT(*)::INT AS participations_count,
            COUNT(*) FILTER (WHERE p.type = 'paid')::INT AS paid_participations_count,
            COUNT(*) FILTER (WHERE p.type = 'free')::INT AS free_participations_count,
            COUNT(*) FILTER (WHERE b.status = 'completed' AND p.status = 'active')::INT AS completed_participations_count,
            (
                SELECT COUNT(*)::INT
                FROM bundles b2
                WHERE b2.creator_channel_id = p.channel_id
            ) AS created_bundles_count
        FROM participants p
        JOIN bundles b ON b.id = p.bundle_id
        GROUP BY p.channel_id
    ) s ON s.channel_id = c.id
    WHERE c.owner_id = $1
    ORDER BY c.created_at DESC, c.id DESC
    """
    async with pool.acquire() as connection:
        return await connection.fetch(query, user_telegram_id)


async def get_channel_stats(pool: Pool, channel_id: int) -> Record:
    query = """
    SELECT
        c.*,
        COALESCE(s.participations_count, 0)::INT AS participations_count,
        COALESCE(s.paid_participations_count, 0)::INT AS paid_participations_count,
        COALESCE(s.free_participations_count, 0)::INT AS free_participations_count,
        COALESCE(s.completed_participations_count, 0)::INT AS completed_participations_count,
        COALESCE(s.created_bundles_count, 0)::INT AS created_bundles_count
    FROM channels c
    LEFT JOIN (
        SELECT
            p.channel_id,
            COUNT(*)::INT AS participations_count,
            COUNT(*) FILTER (WHERE p.type = 'paid')::INT AS paid_participations_count,
            COUNT(*) FILTER (WHERE p.type = 'free')::INT AS free_participations_count,
            COUNT(*) FILTER (WHERE b.status = 'completed' AND p.status = 'active')::INT AS completed_participations_count,
            (
                SELECT COUNT(*)::INT
                FROM bundles b2
                WHERE b2.creator_channel_id = p.channel_id
            ) AS created_bundles_count
        FROM participants p
        JOIN bundles b ON b.id = p.bundle_id
        GROUP BY p.channel_id
    ) s ON s.channel_id = c.id
    WHERE c.id = $1
    LIMIT 1
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, channel_id)


async def get_admin_dashboard_stats(pool: Pool) -> Record:
    query = """
    SELECT
        (SELECT COUNT(*)::INT FROM users) AS users_count,
        (SELECT COUNT(*)::INT FROM channels) AS channels_count,
        (
            SELECT COUNT(*)::INT
            FROM channels
            WHERE bot_is_admin = TRUE
              AND is_verified = TRUE
              AND niche IS NOT NULL
              AND subscribers IS NOT NULL
        ) AS ready_channels_count,
        (SELECT COUNT(*)::INT FROM bundles) AS bundles_count,
        (SELECT COUNT(*)::INT FROM bundles WHERE status = 'open') AS bundles_open_count,
        (SELECT COUNT(*)::INT FROM bundles WHERE status = 'scheduled') AS bundles_scheduled_count,
        (
            SELECT COUNT(*)::INT
            FROM bundles
            WHERE status IN ('published', 'partially_published', 'published_changed')
        ) AS bundles_published_count,
        (SELECT COUNT(*)::INT FROM bundles WHERE status = 'completed') AS bundles_completed_count,
        (SELECT COUNT(*)::INT FROM payments) AS payments_total_count,
        (SELECT COUNT(*)::INT FROM payments WHERE status = 'succeeded') AS payments_success_count,
        (SELECT COALESCE(SUM(amount), 0)::BIGINT FROM payments WHERE status = 'succeeded') AS turnover_amount,
        (SELECT COALESCE(SUM(commission), 0)::BIGINT FROM payments WHERE status = 'succeeded') AS commission_amount
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query)


async def get_recent_violations(pool: Pool, limit: int = 10) -> list[Record]:
    query = """
    SELECT
        v.*,
        c.username AS channel_username,
        c.title AS channel_title
    FROM channel_violations v
    JOIN channels c ON c.id = v.channel_id
    ORDER BY v.created_at DESC, v.id DESC
    LIMIT $1
    """
    async with pool.acquire() as connection:
        return await connection.fetch(query, limit)


async def get_problem_channels(pool: Pool, limit: int = 10) -> list[Record]:
    query = """
    SELECT
        c.id,
        c.username,
        c.title,
        c.rating,
        c.violations_count,
        c.cancelled_after_preview_count,
        c.publish_failures_count
    FROM channels c
    ORDER BY c.violations_count DESC, c.rating ASC, c.cancelled_after_preview_count DESC, c.id ASC
    LIMIT $1
    """
    async with pool.acquire() as connection:
        return await connection.fetch(query, limit)
