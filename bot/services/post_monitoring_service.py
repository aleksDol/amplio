import logging

from aiogram import Bot
from asyncpg import Pool

from repositories.bundles import (
    get_published_bundles_for_monitoring,
    update_bundle_last_checked,
)
from repositories.channels import get_channel_by_id
from repositories.posts import get_active_posts_for_bundle, mark_post_checked
from repositories.violations import create_violation
from services.bundle_update_service import remove_participant_from_published_bundle
from services.datetime_utils import get_local_now
from services.rating_service import apply_violation_penalty
from services.telegram_channels import check_bot_admin_rights


logger = logging.getLogger(__name__)


async def handle_channel_access_lost(
    bot: Bot,
    pool: Pool,
    channel_id: int,
    bundle_id: int | None = None,
) -> None:
    channel = await get_channel_by_id(pool, channel_id)
    if not channel:
        return

    channel_name = channel["username"] or channel["title"] or f"Канал #{channel_id}"
    if bundle_id is not None:
        await remove_participant_from_published_bundle(
            bot=bot,
            pool=pool,
            bundle_id=bundle_id,
            channel_id=channel_id,
            reason="bot_lost_access",
        )
    else:
        await create_violation(
            pool=pool,
            channel_id=channel_id,
            bundle_id=bundle_id,
            participant_id=None,
            violation_type="bot_lost_access",
            details="Bot lost admin rights or posting permissions during published bundle monitoring.",
        )
        await apply_violation_penalty(
            pool=pool,
            channel_id=channel_id,
            violation_type="bot_lost_access",
            bundle_id=None,
        )

    owner_id = int(channel["owner_id"])
    try:
        await bot.send_message(
            chat_id=owner_id,
            text=(
                f"Я потерял доступ к каналу {channel_name}\n"
                "Проверь, что бот всё ещё добавлен как администратор с нужными правами"
            ),
        )
    except Exception:
        pass


async def check_published_channels_access(bot: Bot, pool: Pool) -> None:
    bundles = await get_published_bundles_for_monitoring(pool)
    bot_id = int(bot.id)
    checked_at = get_local_now().replace(tzinfo=None)
    logger.info("Running published channels access check bundles=%s", len(bundles))

    for bundle in bundles:
        bundle_id = int(bundle["id"])
        posts = await get_active_posts_for_bundle(pool, bundle_id)
        for post in posts:
            post_id = int(post["id"])
            channel_id = int(post["channel_id"])
            await mark_post_checked(pool, post_id, checked_at)

            has_access = await check_bot_admin_rights(
                bot=bot,
                chat_id=int(post["telegram_chat_id"]),
                bot_id=bot_id,
            )
            if not has_access:
                logger.info(
                    "Access lost for channel_id=%s bundle_id=%s post_id=%s",
                    channel_id,
                    bundle_id,
                    post_id,
                )
                await handle_channel_access_lost(
                    bot=bot,
                    pool=pool,
                    channel_id=channel_id,
                    bundle_id=bundle_id,
                )
        await update_bundle_last_checked(pool, bundle_id, checked_at)


async def scan_published_bundles_health(bot: Bot, pool: Pool) -> None:
    await check_published_channels_access(bot, pool)
