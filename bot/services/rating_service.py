import logging

from asyncpg import Pool

from repositories.bundles import completion_bonus_already_applied, mark_completion_bonus_applied
from repositories.channels import (
    get_channel_rating,
    increment_cancelled_after_preview_count,
    increment_completed_bundles_count,
    increment_publish_failures_count,
    increment_violations_count,
    update_channel_rating,
)


logger = logging.getLogger(__name__)


def _clamp_rating(value: float) -> float:
    return max(0.0, min(5.0, round(value, 2)))


async def _insert_rating_history(
    pool: Pool,
    channel_id: int,
    delta: float,
    reason: str,
    rating_before: float,
    rating_after: float,
    bundle_id: int | None = None,
) -> None:
    query = """
    INSERT INTO channel_rating_history (
        channel_id,
        bundle_id,
        delta,
        reason,
        rating_before,
        rating_after
    )
    VALUES ($1, $2, $3, $4, $5, $6)
    """
    async with pool.acquire() as connection:
        await connection.execute(
            query,
            channel_id,
            bundle_id,
            delta,
            reason,
            rating_before,
            rating_after,
        )


async def apply_rating_delta(
    pool: Pool,
    channel_id: int,
    delta: float,
    reason: str,
    bundle_id: int | None = None,
) -> float:
    current_rating = await get_channel_rating(pool, channel_id)
    if current_rating is None:
        current_rating = 5.0
    new_rating = _clamp_rating(float(current_rating) + float(delta))
    await update_channel_rating(pool, channel_id, new_rating)
    await _insert_rating_history(
        pool=pool,
        channel_id=channel_id,
        delta=delta,
        reason=reason,
        rating_before=float(current_rating),
        rating_after=new_rating,
        bundle_id=bundle_id,
    )
    logger.info(
        "Rating updated channel_id=%s delta=%s reason=%s bundle_id=%s before=%s after=%s",
        channel_id,
        delta,
        reason,
        bundle_id,
        current_rating,
        new_rating,
    )
    return new_rating


async def apply_violation_penalty(
    pool: Pool,
    channel_id: int,
    violation_type: str,
    bundle_id: int | None = None,
) -> float:
    mapping = {
        "early_post_deletion": -1.0,
        "bot_lost_access": -0.5,
        "publish_rights_missing": -0.5,
    }
    delta = mapping.get(violation_type, -0.5)
    await increment_violations_count(pool, channel_id)
    return await apply_rating_delta(
        pool=pool,
        channel_id=channel_id,
        delta=delta,
        reason=f"violation:{violation_type}",
        bundle_id=bundle_id,
    )


async def apply_preview_cancel_penalty(
    pool: Pool,
    channel_id: int,
    bundle_id: int | None = None,
) -> float:
    await increment_cancelled_after_preview_count(pool, channel_id)
    return await apply_rating_delta(
        pool=pool,
        channel_id=channel_id,
        delta=-0.5,
        reason="cancel_after_preview",
        bundle_id=bundle_id,
    )


async def apply_publish_failure_penalty(
    pool: Pool,
    channel_id: int,
    bundle_id: int | None = None,
) -> float:
    await increment_publish_failures_count(pool, channel_id)
    return await apply_rating_delta(
        pool=pool,
        channel_id=channel_id,
        delta=-0.5,
        reason="publish_failure",
        bundle_id=bundle_id,
    )


async def apply_completion_bonus(pool: Pool, bundle_id: int) -> int:
    if await completion_bonus_already_applied(pool, bundle_id):
        logger.info("Completion bonus already applied bundle_id=%s", bundle_id)
        return 0

    query = """
    SELECT p.channel_id
    FROM participants p
    WHERE p.bundle_id = $1
      AND p.status = 'active'
      AND NOT EXISTS (
          SELECT 1
          FROM channel_violations v
          WHERE v.bundle_id = p.bundle_id
            AND v.channel_id = p.channel_id
      )
    """
    async with pool.acquire() as connection:
        rows = await connection.fetch(query, bundle_id)

    applied = 0
    for row in rows:
        channel_id = int(row["channel_id"])
        await increment_completed_bundles_count(pool, channel_id)
        await apply_rating_delta(
            pool=pool,
            channel_id=channel_id,
            delta=0.1,
            reason="bundle_completed_bonus",
            bundle_id=bundle_id,
        )
        applied += 1

    await mark_completion_bonus_applied(pool, bundle_id)
    logger.info("Completion bonus applied bundle_id=%s channels=%s", bundle_id, applied)
    return applied
