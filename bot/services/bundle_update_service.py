import logging

from aiogram import Bot
from asyncpg import Pool

from repositories.bundles import (
    get_bundle_by_id,
    mark_bundle_changed_after_publication,
    update_bundle_preview,
)
from repositories.channels import get_channel_by_id
from repositories.participants import (
    get_active_participant_by_channel_and_bundle,
    get_active_participants_with_channels,
    remove_participant_from_bundle,
)
from repositories.posts import (
    get_active_posts_for_bundle,
    get_posts_for_bundle,
    mark_post_status,
)
from repositories.violations import create_violation
from services.rating_service import apply_violation_penalty
from services.bundle_post_builder import build_bundle_preview_text
from services.datetime_utils import get_local_now


logger = logging.getLogger(__name__)


def _looks_like_missing_or_access_error(error_text: str) -> bool:
    normalized = error_text.lower()
    patterns = (
        "message to edit not found",
        "message is not modified",
        "chat not found",
        "message can't be edited",
        "have no rights",
        "not enough rights",
        "forbidden",
        "bot was kicked",
    )
    return any(pattern in normalized for pattern in patterns)


async def rebuild_bundle_text_without_channel(pool: Pool, bundle_id: int, channel_id: int) -> str:
    participant = await get_active_participant_by_channel_and_bundle(pool, channel_id, bundle_id)
    if participant:
        await remove_participant_from_bundle(
            pool=pool,
            participant_id=int(participant["id"]),
            reason="early_post_deletion",
            removed_at=get_local_now().replace(tzinfo=None),
        )
    return await build_bundle_preview_text(pool, bundle_id)


async def edit_published_bundle_posts(
    bot: Bot,
    pool: Pool,
    bundle_id: int,
    new_text: str,
    excluded_channel_id: int,
) -> tuple[int, int]:
    posts = await get_active_posts_for_bundle(pool, bundle_id)
    success_count = 0
    failed_count = 0
    for post in posts:
        post_channel_id = int(post["channel_id"])
        if post_channel_id == excluded_channel_id:
            continue

        try:
            await bot.edit_message_text(
                chat_id=int(post["telegram_chat_id"]),
                message_id=int(post["message_id"]),
                text=new_text,
            )
            success_count += 1
        except Exception as exc:
            failed_count += 1
            error_text = str(exc)
            await mark_post_status(
                pool=pool,
                post_id=int(post["id"]),
                status="edit_failed",
                error_text=error_text,
            )
            if _looks_like_missing_or_access_error(error_text):
                await remove_participant_from_published_bundle(
                    bot=bot,
                    pool=pool,
                    bundle_id=bundle_id,
                    channel_id=post_channel_id,
                    reason="early_post_deletion",
                )
            logger.info(
                "Failed to edit post post_id=%s bundle_id=%s error=%s",
                post["id"],
                bundle_id,
                error_text,
            )
    return success_count, failed_count


async def notify_bundle_changed(
    bot: Bot,
    pool: Pool,
    bundle_id: int,
    removed_channel_id: int,
    had_edit_failures: bool,
) -> None:
    removed_channel = await get_channel_by_id(pool, removed_channel_id)
    removed_name = (
        removed_channel["username"]
        if removed_channel and removed_channel["username"]
        else (removed_channel["title"] if removed_channel else f"Канал #{removed_channel_id}")
    )
    participants = await get_active_participants_with_channels(pool, bundle_id)
    for participant in participants:
        owner_id = int(participant["owner_id"])
        text = (
            "Состав опубликованной подборки изменён\n"
            f"Канал {removed_name} был исключён из подборки.\n"
        )
        if had_edit_failures:
            text += "Состав подборки изменён, но не все посты удалось обновить автоматически"
        else:
            text += "Посты в остальных каналах обновлены."
        try:
            await bot.send_message(chat_id=owner_id, text=text)
        except Exception:
            continue


async def remove_participant_from_published_bundle(
    bot: Bot,
    pool: Pool,
    bundle_id: int,
    channel_id: int,
    reason: str = "early_post_deletion",
) -> bool:
    bundle = await get_bundle_by_id(pool, bundle_id)
    if not bundle or bundle["status"] not in {"published", "partially_published", "published_changed"}:
        return False

    participant = await get_active_participant_by_channel_and_bundle(pool, channel_id, bundle_id)
    if not participant:
        return False

    removed_at = get_local_now().replace(tzinfo=None)
    removed = await remove_participant_from_bundle(
        pool=pool,
        participant_id=int(participant["id"]),
        reason=reason,
        removed_at=removed_at,
    )
    if not removed:
        return False

    await create_violation(
        pool=pool,
        channel_id=channel_id,
        bundle_id=bundle_id,
        participant_id=int(participant["id"]),
        violation_type=reason,
        details="Channel removed after publication due to policy violation.",
    )
    await apply_violation_penalty(
        pool=pool,
        channel_id=channel_id,
        violation_type=reason,
        bundle_id=bundle_id,
    )

    # Mark removed channel post as removed early
    posts = await get_posts_for_bundle(pool, bundle_id)
    for post in posts:
        if int(post["channel_id"]) == channel_id and post["status"] == "active":
            await mark_post_status(
                pool=pool,
                post_id=int(post["id"]),
                status="removed_early",
                error_text="Post was removed before scheduled delete time.",
            )

    new_text = await build_bundle_preview_text(pool, bundle_id)
    await update_bundle_preview(
        pool=pool,
        bundle_id=bundle_id,
        preview_text=new_text,
        preview_generated_at=removed_at,
    )
    await mark_bundle_changed_after_publication(pool, bundle_id)

    _, failed_count = await edit_published_bundle_posts(
        bot=bot,
        pool=pool,
        bundle_id=bundle_id,
        new_text=new_text,
        excluded_channel_id=channel_id,
    )
    await notify_bundle_changed(
        bot=bot,
        pool=pool,
        bundle_id=bundle_id,
        removed_channel_id=channel_id,
        had_edit_failures=failed_count > 0,
    )
    logger.info(
        "Participant removed from published bundle bundle_id=%s channel_id=%s reason=%s",
        bundle_id,
        channel_id,
        reason,
    )
    return True
