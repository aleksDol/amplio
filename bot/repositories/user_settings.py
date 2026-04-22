from asyncpg import Pool, Record


async def _ensure_user_exists(pool: Pool, user_telegram_id: int) -> None:
    query = """
    INSERT INTO users (telegram_id, username)
    VALUES ($1, NULL)
    ON CONFLICT (telegram_id) DO NOTHING
    """
    async with pool.acquire() as connection:
        await connection.execute(query, user_telegram_id)


async def get_or_create_user_settings(pool: Pool, user_telegram_id: int) -> Record:
    await _ensure_user_exists(pool, user_telegram_id)
    query = """
    INSERT INTO user_settings (user_telegram_id)
    VALUES ($1)
    ON CONFLICT (user_telegram_id) DO UPDATE
    SET updated_at = user_settings.updated_at
    RETURNING *
    """
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, user_telegram_id)


async def set_bundle_notifications_enabled(pool: Pool, user_telegram_id: int, enabled: bool) -> None:
    await _ensure_user_exists(pool, user_telegram_id)
    query = """
    INSERT INTO user_settings (user_telegram_id, bundle_notifications_enabled, updated_at)
    VALUES ($1, $2, NOW())
    ON CONFLICT (user_telegram_id) DO UPDATE
    SET
        bundle_notifications_enabled = EXCLUDED.bundle_notifications_enabled,
        updated_at = NOW()
    """
    async with pool.acquire() as connection:
        await connection.execute(query, user_telegram_id, enabled)


async def get_bundle_notifications_enabled(pool: Pool, user_telegram_id: int) -> bool:
    settings = await get_or_create_user_settings(pool, user_telegram_id)
    return bool(settings["bundle_notifications_enabled"])
