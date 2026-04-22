import re
from dataclasses import dataclass
import logging
from typing import Optional
import asyncio

from aiogram import Bot
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError


USERNAME_PATTERN = re.compile(r"^@[A-Za-z0-9_]{4,32}$")
logger = logging.getLogger(__name__)


@dataclass
class TelegramChannelInfo:
    chat_id: int
    username: str
    title: str
    chat_type: str


def validate_channel_username(username: str) -> bool:
    return bool(USERNAME_PATTERN.fullmatch(username.strip()))


async def get_channel_info(bot: Bot, username: str) -> Optional[TelegramChannelInfo]:
    try:
        chat = await bot.get_chat(username)
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        logger.info("Telegram API error while get_chat for %s: %s", username, str(exc))
        return None

    normalized_username = f"@{chat.username}" if chat.username else username
    title = chat.title or normalized_username
    return TelegramChannelInfo(
        chat_id=chat.id,
        username=normalized_username,
        title=title,
        chat_type=chat.type,
    )


async def check_bot_admin_rights(bot: Bot, chat_id: int, bot_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=bot_id)
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        logger.info("Telegram API error while get_chat_member for %s: %s", chat_id, str(exc))
        return False

    if member.status == ChatMemberStatus.CREATOR:
        return True

    if member.status != ChatMemberStatus.ADMINISTRATOR:
        return False

    can_post = bool(getattr(member, "can_post_messages", False))
    can_delete = bool(getattr(member, "can_delete_messages", False))
    can_edit = bool(getattr(member, "can_edit_messages", False))
    return can_post and (can_delete or can_edit)


def is_channel_chat(chat_type: str) -> bool:
    return chat_type == ChatType.CHANNEL


async def get_subscribers_count(bot: Bot, chat_id: int) -> Optional[int]:
    try:
        subscribers = await bot.get_chat_member_count(chat_id=chat_id)
    except (
        TelegramBadRequest,
        TelegramForbiddenError,
        TelegramNetworkError,
        asyncio.TimeoutError,
    ) as exc:
        logger.info(
            "Telegram API error while get_chat_member_count for %s: %s",
            chat_id,
            str(exc),
        )
        return None
    except Exception as exc:
        logger.info("Unexpected error while get_chat_member_count for %s: %s", chat_id, str(exc))
        return None

    return int(subscribers)
