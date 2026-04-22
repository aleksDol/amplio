from typing import Optional

import asyncpg
from asyncpg import Pool


_pool: Optional[Pool] = None


async def create_pool(database_url: str) -> Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn=database_url)
    return _pool


def get_pool() -> Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialized. Call create_pool() first.")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
