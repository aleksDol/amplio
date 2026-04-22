import asyncio
import logging

from aiogram import Bot, Dispatcher

from config import settings as app_settings
from database.connection import close_pool, create_pool, get_pool
from database.models import create_tables
from handlers import (
    add_channel,
    admin,
    bundle_monitoring,
    bundle_preview,
    channel_setup,
    channels,
    create_bundle,
    find_bundle,
    payments,
    scheduler,
    settings as settings_handler,
    stats,
    start,
)
from services.scheduler_service import init_scheduler, restore_scheduled_jobs, shutdown_scheduler


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    await create_pool(app_settings.database_url)
    await create_tables(get_pool())

    bot = Bot(token=app_settings.bot_token)
    init_scheduler(bot, get_pool())
    await restore_scheduled_jobs(get_pool(), bot)

    dp = Dispatcher()
    dp.include_router(start.router)
    dp.include_router(add_channel.router)
    dp.include_router(channel_setup.router)
    dp.include_router(channels.router)
    dp.include_router(create_bundle.router)
    dp.include_router(find_bundle.router)
    dp.include_router(payments.router)
    dp.include_router(bundle_preview.router)
    dp.include_router(bundle_monitoring.router)
    dp.include_router(scheduler.router)
    dp.include_router(stats.router)
    dp.include_router(admin.router)
    dp.include_router(settings_handler.router)

    try:
        await dp.start_polling(bot)
    finally:
        shutdown_scheduler()
        await bot.session.close()
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
