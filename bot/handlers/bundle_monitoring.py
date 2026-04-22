import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database.connection import get_pool
from repositories.bundles import get_published_bundles_for_monitoring
from services.post_monitoring_service import scan_published_bundles_health
from services.publishing_service import delete_bundle_posts


logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("scan_posts"))
async def debug_scan_posts(message: Message) -> None:
    pool = get_pool()
    await scan_published_bundles_health(message.bot, pool)
    await message.answer("Проверка опубликованных подборок завершена.")


@router.message(Command("expire_posts"))
async def debug_expire_posts(message: Message) -> None:
    pool = get_pool()
    bundles = await get_published_bundles_for_monitoring(pool)
    processed = 0
    for bundle in bundles:
        await delete_bundle_posts(message.bot, pool, int(bundle["id"]))
        processed += 1
    logger.info("Manual expire posts triggered bundles=%s", processed)
    await message.answer(f"Запущено удаление постов для {processed} подборок.")
