import asyncio
import logging
from datetime import timedelta
from typing import Any

from aiogram import Bot
from asyncpg import Pool

from repositories.bundles import (
    get_bundle_by_id,
    mark_bundle_completed,
    update_bundle_publication_status,
)
from repositories.participants import get_active_participants_with_channels
from repositories.posts import (
    create_post_record,
    get_active_posts_for_bundle,
    mark_post_deleted,
    mark_post_status,
)
from services.bundle_post_builder import build_bundle_preview_text
from services.datetime_utils import get_local_now
from services.rating_service import apply_completion_bonus, apply_publish_failure_penalty
from services.scheduler_service import schedule_bundle_delete


logger = logging.getLogger(__name__)


def _is_message_missing_error(error_text: str) -> bool:
    normalized = error_text.lower()
    patterns = (
        "message to delete not found",
        "message to edit not found",
        "message can't be deleted",
        "chat not found",
    )
    return any(pattern in normalized for pattern in patterns)


def _is_channel_access_error(error_text: str) -> bool:
    normalized = error_text.lower()
    patterns = (
        "not enough rights",
        "forbidden",
        "bot was kicked",
        "chat not found",
        "need administrator rights",
    )
    return any(pattern in normalized for pattern in patterns)


async def publish_bundle_to_channel(
    bot: Bot,
    pool: Pool,
    bundle_id: int,
    channel_id: int,
    telegram_chat_id: int,
    text: str,
    delete_at,
) -> dict[str, Any]:
    published_at = get_local_now().replace(tzinfo=None)
    try:
        message = await bot.send_message(chat_id=telegram_chat_id, text=text)
        await create_post_record(
            pool=pool,
            bundle_id=bundle_id,
            channel_id=channel_id,
            message_id=message.message_id,
            status="active",
            published_at=published_at,
            delete_at=delete_at,
            error_text=None,
        )
        return {"success": True, "channel_id": channel_id}
    except Exception as exc:
        error_text = str(exc)
        await create_post_record(
            pool=pool,
            bundle_id=bundle_id,
            channel_id=channel_id,
            message_id=None,
            status="publish_failed",
            published_at=published_at,
            delete_at=delete_at,
            error_text=error_text,
        )
        if _is_channel_access_error(error_text):
            await apply_publish_failure_penalty(pool, channel_id=channel_id, bundle_id=bundle_id)
        return {"success": False, "channel_id": channel_id, "error": error_text}


async def publish_bundle(bot: Bot, pool: Pool, bundle_id: int) -> None:
    bundle = await get_bundle_by_id(pool, bundle_id)
    if not bundle or bundle["status"] != "scheduled":
        logger.info("Skip publish bundle_id=%s status_not_scheduled", bundle_id)
        return

    participants = await get_active_participants_with_channels(pool, bundle_id)
    if len(participants) != int(bundle["slots"]):
        logger.info("Skip publish bundle_id=%s active_count=%s slots=%s", bundle_id, len(participants), bundle["slots"])
        return

    text = bundle["preview_text"] or await build_bundle_preview_text(pool, bundle_id)
    now_naive = get_local_now().replace(tzinfo=None)
    delete_at = now_naive + timedelta(hours=int(bundle["post_lifetime_hours"] or 24))

    logger.info("Publishing bundle bundle_id=%s channels=%s", bundle_id, len(participants))
    tasks = [
        publish_bundle_to_channel(
            bot=bot,
            pool=pool,
            bundle_id=bundle_id,
            channel_id=int(participant["channel_id"]),
            telegram_chat_id=int(participant["telegram_chat_id"]),
            text=text,
            delete_at=delete_at,
        )
        for participant in participants
    ]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    failures = [result for result in results if not result["success"]]
    if failures:
        await update_bundle_publication_status(
            pool=pool,
            bundle_id=bundle_id,
            status="partially_published",
            published_at=now_naive,
        )
        logger.info("Bundle partially published bundle_id=%s failed=%s", bundle_id, len(failures))
    else:
        await update_bundle_publication_status(
            pool=pool,
            bundle_id=bundle_id,
            status="published",
            published_at=now_naive,
        )
        logger.info("Bundle published successfully bundle_id=%s", bundle_id)

    schedule_bundle_delete(bundle_id=bundle_id, run_at=delete_at)


async def delete_single_post(bot: Bot, chat_id: int, message_id: int) -> dict[str, Any]:
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        return {"success": True, "missing": False}
    except Exception as exc:
        error_text = str(exc)
        return {
            "success": False,
            "missing": _is_message_missing_error(error_text),
            "error_text": error_text,
        }


async def mark_post_delete_failed(pool: Pool, post_id: int, error_text: str) -> None:
    await mark_post_status(
        pool=pool,
        post_id=post_id,
        status="edit_failed",
        error_text=error_text,
    )


async def delete_bundle_posts(bot: Bot, pool: Pool, bundle_id: int) -> None:
    posts = await get_active_posts_for_bundle(pool, bundle_id)
    if not posts:
        await mark_bundle_completed(pool, bundle_id, get_local_now().replace(tzinfo=None))
        await apply_completion_bonus(pool, bundle_id)
        return

    deleted_at = get_local_now().replace(tzinfo=None)
    failures = 0
    for post in posts:
        result = await delete_single_post(
            bot=bot,
            chat_id=int(post["telegram_chat_id"]),
            message_id=int(post["message_id"]),
        )
        if result["success"]:
            await mark_post_deleted(
                pool=pool,
                post_id=int(post["id"]),
                deleted_at=deleted_at,
                status="deleted",
            )
            continue

        if result.get("missing", False):
            # Message was already absent by deletion time; treat as processed.
            await mark_post_deleted(
                pool=pool,
                post_id=int(post["id"]),
                deleted_at=deleted_at,
                status="deleted",
                error_text=f"Message already absent at delete time: {result['error_text'][:500]}",
            )
            logger.info(
                "Post already missing at delete time bundle_id=%s post_id=%s",
                bundle_id,
                post["id"],
            )
            continue

        failures += 1
        await mark_post_delete_failed(
            pool=pool,
            post_id=int(post["id"]),
            error_text=result.get("error_text", "Unknown delete error"),
        )

    if failures == 0:
        await mark_bundle_completed(pool, bundle_id, deleted_at)
        await apply_completion_bonus(pool, bundle_id)
        logger.info("Bundle posts deleted bundle_id=%s", bundle_id)
    else:
        logger.info("Bundle delete had failures bundle_id=%s failures=%s", bundle_id, failures)
