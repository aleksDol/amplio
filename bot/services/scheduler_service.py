import logging
from datetime import datetime, timedelta

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from asyncpg import Pool

from repositories.bundles import get_bundles_by_status
from repositories.participants import get_active_participants_with_channels
from repositories.posts import get_active_posts_for_bundle
from services.datetime_utils import LOCAL_TZ, get_local_now


logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_bot: Bot | None = None
_pool: Pool | None = None


def _to_local_aware(run_at: datetime) -> datetime:
    if run_at.tzinfo is None:
        return run_at.replace(tzinfo=LOCAL_TZ)
    return run_at.astimezone(LOCAL_TZ)


def init_scheduler(bot: Bot, pool: Pool) -> AsyncIOScheduler:
    global _scheduler, _bot, _pool
    _bot = bot
    _pool = pool
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone=LOCAL_TZ)
        _scheduler.start()
        logger.info("Scheduler started")
    _scheduler.add_job(
        func=_run_scan_published_bundles_health,
        trigger=IntervalTrigger(minutes=5, timezone=LOCAL_TZ),
        id="bundle_health_scan",
        replace_existing=True,
        misfire_grace_time=300,
    )
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
    _scheduler = None


def _require_scheduler() -> AsyncIOScheduler:
    if _scheduler is None:
        raise RuntimeError("Scheduler is not initialized")
    return _scheduler


def schedule_bundle_preview(bundle_id: int, run_at: datetime) -> None:
    scheduler = _require_scheduler()
    run_at_local = _to_local_aware(run_at)
    scheduler.add_job(
        func=_run_send_bundle_preview,
        trigger=DateTrigger(run_date=run_at_local),
        id=f"bundle_preview:{bundle_id}",
        kwargs={"bundle_id": bundle_id},
        replace_existing=True,
        misfire_grace_time=3600,
    )


def schedule_bundle_auto_confirm(bundle_id: int, run_at: datetime) -> None:
    scheduler = _require_scheduler()
    run_at_local = _to_local_aware(run_at)
    scheduler.add_job(
        func=_run_auto_confirm_bundle_preview,
        trigger=DateTrigger(run_date=run_at_local),
        id=f"bundle_auto_confirm:{bundle_id}",
        kwargs={"bundle_id": bundle_id},
        replace_existing=True,
        misfire_grace_time=3600,
    )


def schedule_bundle_publish(bundle_id: int, run_at: datetime) -> None:
    scheduler = _require_scheduler()
    run_at_local = _to_local_aware(run_at)
    scheduler.add_job(
        func=_run_publish_bundle,
        trigger=DateTrigger(run_date=run_at_local),
        id=f"bundle_publish:{bundle_id}",
        kwargs={"bundle_id": bundle_id},
        replace_existing=True,
        misfire_grace_time=3600,
    )


def schedule_bundle_delete(bundle_id: int, run_at: datetime) -> None:
    scheduler = _require_scheduler()
    run_at_local = _to_local_aware(run_at)
    scheduler.add_job(
        func=_run_delete_bundle_posts,
        trigger=DateTrigger(run_date=run_at_local),
        id=f"bundle_delete:{bundle_id}",
        kwargs={"bundle_id": bundle_id},
        replace_existing=True,
        misfire_grace_time=3600,
    )


async def _run_send_bundle_preview(bundle_id: int) -> None:
    if _bot is None or _pool is None:
        return
    from services.bundle_preview_service import send_bundle_preview

    await send_bundle_preview(_bot, _pool, bundle_id)


async def _run_auto_confirm_bundle_preview(bundle_id: int) -> None:
    if _pool is None:
        return
    from services.bundle_preview_service import auto_confirm_pending_previews, try_move_bundle_to_scheduled

    await auto_confirm_pending_previews(_pool, bundle_id)
    await try_move_bundle_to_scheduled(_pool, bundle_id)


async def _run_publish_bundle(bundle_id: int) -> None:
    if _bot is None or _pool is None:
        return
    from services.publishing_service import publish_bundle

    await publish_bundle(_bot, _pool, bundle_id)


async def _run_delete_bundle_posts(bundle_id: int) -> None:
    if _bot is None or _pool is None:
        return
    from services.publishing_service import delete_bundle_posts

    await delete_bundle_posts(_bot, _pool, bundle_id)


async def _run_scan_published_bundles_health() -> None:
    if _bot is None or _pool is None:
        return
    from services.post_monitoring_service import scan_published_bundles_health

    await scan_published_bundles_health(_bot, _pool)


async def restore_scheduled_jobs(pool: Pool, bot: Bot) -> None:
    init_scheduler(bot, pool)
    now_local = get_local_now()
    now_naive = now_local.replace(tzinfo=None)

    full_bundles = await get_bundles_by_status(pool, ["full"])
    for bundle in full_bundles:
        participants = await get_active_participants_with_channels(pool, int(bundle["id"]))
        if not participants:
            continue
        if all(bool(participant["preview_confirmed"]) for participant in participants):
            from services.bundle_preview_service import try_move_bundle_to_scheduled

            await try_move_bundle_to_scheduled(pool, int(bundle["id"]))
            continue
        preview_sent_values = [p["preview_sent_at"] for p in participants if p["preview_sent_at"] is not None]
        if not preview_sent_values:
            schedule_bundle_preview(int(bundle["id"]), now_local)
            continue
        auto_confirm_at = (max(preview_sent_values) + timedelta(hours=2)).replace(tzinfo=LOCAL_TZ)
        if auto_confirm_at < now_local:
            auto_confirm_at = now_local
        schedule_bundle_auto_confirm(int(bundle["id"]), auto_confirm_at)

    scheduled_bundles = await get_bundles_by_status(pool, ["scheduled"])
    for bundle in scheduled_bundles:
        publish_at = bundle["scheduled_at"]
        if publish_at is None:
            continue
        run_at = publish_at.replace(tzinfo=LOCAL_TZ) if publish_at.tzinfo is None else publish_at
        if run_at < now_local:
            run_at = now_local
        schedule_bundle_publish(int(bundle["id"]), run_at)

    published_bundles = await get_bundles_by_status(pool, ["published", "partially_published", "published_changed"])
    for bundle in published_bundles:
        posts = await get_active_posts_for_bundle(pool, int(bundle["id"]))
        if not posts:
            continue
        delete_dates = [post["delete_at"] for post in posts if post["delete_at"] is not None]
        if not delete_dates:
            continue
        run_naive = min(delete_dates)
        run_at = run_naive.replace(tzinfo=LOCAL_TZ)
        if run_naive < now_naive:
            run_at = now_local
        schedule_bundle_delete(int(bundle["id"]), run_at)

    logger.info(
        "Scheduler restore completed full=%s scheduled=%s published=%s",
        len(full_bundles),
        len(scheduled_bundles),
        len(published_bundles),
    )
