import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError
from asyncpg import Pool

from config import settings as app_settings
from keyboards.admin import get_set_paid_price_keyboard
from keyboards.notifications import (
    get_bundle_notification_keyboard,
    get_creator_participant_joined_keyboard,
)
from repositories.bundles import (
    bundle_has_free_slots,
    bundle_paid_slot_taken,
    get_bundle_with_creator_channel,
)
from repositories.channels import get_ready_channels_by_niche
from repositories.notifications import (
    create_bundle_notification,
    notification_already_sent,
)
from repositories.participants import (
    channel_already_in_bundle,
    channel_has_bundle_at_time,
    get_participant_with_bundle_channel,
    get_bundle_participating_channel_ids,
)
from repositories.user_settings import get_bundle_notifications_enabled
from services.bundle_matching import resolve_available_entry_types
from services.datetime_utils import format_datetime_for_preview


logger = logging.getLogger(__name__)


def _notification_type(free_allowed: bool, paid_allowed: bool) -> str:
    if free_allowed and paid_allowed:
        return "free_and_paid_match"
    if free_allowed:
        return "free_match"
    return "paid_match"


def _paid_entry_enabled(bundle) -> bool:
    paid_price = bundle["paid_slot_price"]
    if paid_price is None:
        return False
    return bool(bundle["has_paid_slot"]) and int(paid_price) > 0


async def find_matching_channels_for_bundle(pool: Pool, bundle_id: int) -> list[dict]:
    bundle = await get_bundle_with_creator_channel(pool, bundle_id)
    if not bundle or bundle["status"] != "open":
        return []

    if not await bundle_has_free_slots(pool, bundle_id):
        return []

    candidate_channels = await get_ready_channels_by_niche(pool, bundle["niche"])
    participating_channel_ids = set(await get_bundle_participating_channel_ids(pool, bundle_id))
    paid_taken = await bundle_paid_slot_taken(pool, bundle_id)

    matching_channels: list[dict] = []
    for channel in candidate_channels:
        if int(channel["owner_id"]) == int(bundle["creator_owner_id"]):
            continue
        if int(channel["id"]) == int(bundle["creator_channel_id"]):
            continue
        if int(channel["id"]) in participating_channel_ids:
            continue
        if await channel_has_bundle_at_time(pool, int(channel["id"]), bundle["scheduled_at"]):
            continue

        notifications_enabled = await get_bundle_notifications_enabled(pool, int(channel["owner_id"]))
        if not notifications_enabled:
            continue

        match = resolve_available_entry_types(
            same_niche=channel["niche"] == bundle["niche"],
            channel_subscribers=channel["subscribers"],
            creator_subscribers=bundle["creator_subscribers"],
            bundle_has_paid_slot=_paid_entry_enabled(bundle),
            paid_slot_taken=paid_taken,
        )
        if not match["free_allowed"] and not match["paid_allowed"]:
            continue

        matching_channels.append(
            {
                "bundle_id": int(bundle_id),
                "user_telegram_id": int(channel["owner_id"]),
                "channel_id": int(channel["id"]),
                "channel_username": channel["username"],
                "channel_title": channel["title"],
                "channel_subscribers": int(channel["subscribers"]),
                "free_allowed": bool(match["free_allowed"]),
                "paid_allowed": bool(match["paid_allowed"]),
                "notification_type": _notification_type(
                    bool(match["free_allowed"]),
                    bool(match["paid_allowed"]),
                ),
                "bundle": bundle,
            }
        )
    return matching_channels


def group_matching_channels_by_user(channels: list[dict]) -> list[dict]:
    grouped: dict[int, list[dict]] = {}
    for channel in channels:
        grouped.setdefault(channel["user_telegram_id"], []).append(channel)

    grouped_results: list[dict] = []
    for user_id, items in grouped.items():
        free_items = [item for item in items if item["free_allowed"]]
        if free_items:
            creator_subscribers = int(free_items[0]["bundle"]["creator_subscribers"] or 0)
            free_items.sort(
                key=lambda x: abs(int(x["channel_subscribers"]) - creator_subscribers)
            )
            primary = free_items[0]
        else:
            primary = items[0]
        grouped_results.append(
            {
                "user_telegram_id": user_id,
                "primary": primary,
                "channels": items[:3],
            }
        )
    return grouped_results


async def send_bundle_notifications(bot: Bot, pool: Pool, bundle_id: int) -> None:
    logger.info("Starting bundle notifications for bundle_id=%s", bundle_id)

    matching_channels = await find_matching_channels_for_bundle(pool, bundle_id)
    logger.info("Matching channels found for bundle_id=%s: %s", bundle_id, len(matching_channels))
    grouped = group_matching_channels_by_user(matching_channels)
    logger.info("Unique users for bundle_id=%s: %s", bundle_id, len(grouped))

    success_count = 0
    failed_count = 0
    skipped_count = 0

    for group in grouped:
        user_id = group["user_telegram_id"]
        primary = group["primary"]
        bundle = primary["bundle"]

        if bundle["status"] != "open" or not await bundle_has_free_slots(pool, bundle_id):
            logger.info("Skipping notifications: bundle_id=%s is not open/has no slots", bundle_id)
            break

        if await notification_already_sent(pool, bundle_id, user_id):
            logger.info("Skipping duplicate notification bundle_id=%s user_id=%s", bundle_id, user_id)
            skipped_count += 1
            continue

        if not await get_bundle_notifications_enabled(pool, user_id):
            logger.info("Skipping disabled notifications bundle_id=%s user_id=%s", bundle_id, user_id)
            skipped_count += 1
            continue

        organizer_name = bundle["creator_username"] or bundle["creator_title"] or f"Канал #{bundle['creator_channel_id']}"
        channel_name = primary["channel_username"] or primary["channel_title"] or f"Канал #{primary['channel_id']}"
        used_slots = len(await get_bundle_participating_channel_ids(pool, bundle_id))
        free_slots = max(0, int(bundle["slots"]) - used_slots)

        if primary["free_allowed"]:
            text = (
                f"Новая подборка по теме “{bundle['niche']}”\n"
                f"Публикация: {format_datetime_for_preview(bundle['scheduled_at'])}\n"
                f"Организатор: {organizer_name}\n\n"
                f"Для канала {channel_name} подходит бесплатное участие ✅\n"
                f"Свободных мест: {free_slots}"
            )
        else:
            paid_price = bundle["paid_slot_price"]
            price_text = f"{paid_price} ₽" if paid_price else "по цене организатора"
            text = (
                f"Новая подборка по теме “{bundle['niche']}”\n"
                f"Публикация: {format_datetime_for_preview(bundle['scheduled_at'])}\n"
                f"Организатор: {organizer_name}\n\n"
                f"Для канала {channel_name} бесплатное участие не подходит по диапазону подписчиков,\n"
                f"но доступно платное место: {price_text}"
            )

        try:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=get_bundle_notification_keyboard(bundle_id),
            )
        except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError) as exc:
            logger.info(
                "Failed to send bundle notification bundle_id=%s user_id=%s error=%s",
                bundle_id,
                user_id,
                str(exc),
            )
            failed_count += 1
            continue
        except Exception as exc:
            logger.info(
                "Unexpected notification send error bundle_id=%s user_id=%s error=%s",
                bundle_id,
                user_id,
                str(exc),
            )
            failed_count += 1
            continue

        created = await create_bundle_notification(
            pool=pool,
            bundle_id=bundle_id,
            user_telegram_id=user_id,
            channel_id=primary["channel_id"],
            notification_type=primary["notification_type"],
        )
        if created is None:
            logger.info("Notification race duplicate bundle_id=%s user_id=%s", bundle_id, user_id)
            skipped_count += 1
            continue
        success_count += 1

    logger.info(
        "Bundle notifications done bundle_id=%s sent=%s failed=%s skipped=%s",
        bundle_id,
        success_count,
        failed_count,
        skipped_count,
    )


async def notify_creator_about_new_participant(bot: Bot, pool: Pool, participant_id: int) -> None:
    participant = await get_participant_with_bundle_channel(pool, participant_id)
    if not participant or participant["status"] not in {"active", "awaiting_payment"}:
        return

    bundle = await get_bundle_with_creator_channel(pool, int(participant["bundle_id"]))
    if not bundle:
        return

    creator_owner_id = int(bundle["creator_owner_id"])
    participant_owner_id = int(participant["owner_id"])
    if creator_owner_id == participant_owner_id:
        return

    channel_name = participant["channel_username"] or participant["channel_title"] or f"Канал #{participant['channel_id']}"
    used_slots = len(await get_bundle_participating_channel_ids(pool, int(participant["bundle_id"])))
    slots = int(bundle["slots"])
    place_text = f"{used_slots} из {slots}"

    if participant["status"] == "awaiting_payment":
        status_text = "отправил заявку на платное участие"
    elif participant["type"] == "paid":
        status_text = "вступил платно"
    else:
        status_text = "вступил"

    text = (
        f"В вашу подборку #{bundle['id']} {status_text} участник.\n"
        f"Канал: {channel_name}\n"
        f"Публикация: {format_datetime_for_preview(bundle['scheduled_at'])}\n"
        f"Участников сейчас: {place_text}"
    )

    try:
        await bot.send_message(
            chat_id=creator_owner_id,
            text=text,
            reply_markup=get_creator_participant_joined_keyboard(),
        )
    except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError) as exc:
        logger.info(
            "Failed to notify creator about participant bundle_id=%s participant_id=%s error=%s",
            bundle["id"],
            participant_id,
            str(exc),
        )
    except Exception as exc:
        logger.info(
            "Unexpected creator notification error bundle_id=%s participant_id=%s error=%s",
            bundle["id"],
            participant_id,
            str(exc),
        )


async def notify_admins_to_set_paid_price(bot: Bot, pool: Pool, bundle_id: int) -> None:
    bundle = await get_bundle_with_creator_channel(pool, bundle_id)
    if not bundle:
        return

    creator_name = bundle["creator_username"] or bundle["creator_title"] or f"Канал #{bundle['creator_channel_id']}"
    text = (
        f"Новая подборка #{bundle['id']} создана и скоро будет опубликована.\n"
        f"Организатор: {creator_name}\n"
        f"Публикация: {format_datetime_for_preview(bundle['scheduled_at'])}\n\n"
        "Назначь цену платного места."
    )

    for admin_id in app_settings.admin_telegram_ids:
        try:
            await bot.send_message(
                chat_id=int(admin_id),
                text=text,
                reply_markup=get_set_paid_price_keyboard(int(bundle["id"])),
            )
        except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError) as exc:
            logger.info(
                "Failed to notify admin for paid price bundle_id=%s admin_id=%s error=%s",
                bundle_id,
                admin_id,
                str(exc),
            )
        except Exception as exc:
            logger.info(
                "Unexpected admin paid price notification error bundle_id=%s admin_id=%s error=%s",
                bundle_id,
                admin_id,
                str(exc),
            )
