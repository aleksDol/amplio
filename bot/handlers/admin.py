import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from config import is_admin
from database.connection import get_pool
from keyboards.admin import get_admin_keyboard
from repositories.stats import (
    get_admin_dashboard_stats,
    get_problem_channels,
    get_recent_violations,
)
from services.stats_service import build_admin_dashboard_text


logger = logging.getLogger(__name__)
router = Router()


def _format_problem_channels(rows) -> str:
    if not rows:
        return "Проблемных каналов пока нет."
    lines = ["Проблемные каналы:"]
    for row in rows:
        name = row["username"] or row["title"] or f"Канал #{row['id']}"
        lines.append(
            f"{name} · rating {float(row['rating'] or 0.0):.1f} · violations {int(row['violations_count'] or 0)} · cancel {int(row['cancelled_after_preview_count'] or 0)}"
        )
    return "\n".join(lines)


def _format_violations(rows) -> str:
    if not rows:
        return "Нарушений пока нет."
    lines = ["Последние нарушения:"]
    for row in rows:
        name = row["channel_username"] or row["channel_title"] or f"Канал #{row['channel_id']}"
        lines.append(f"{row['created_at']:%d.%m %H:%M} · {name} · {row['violation_type']} · bundle #{row['bundle_id'] or '-'}")
    return "\n".join(lines)


async def _send_admin_dashboard(message: Message | CallbackQuery, user_id: int) -> None:
    if not is_admin(user_id):
        logger.info("Non-admin tried admin command user=%s", user_id)
        target = message.message if isinstance(message, CallbackQuery) else message
        await target.answer("Эта команда доступна только администратору сервиса")
        return

    pool = get_pool()
    dashboard = await get_admin_dashboard_stats(pool)
    recent_violations = await get_recent_violations(pool, limit=5)
    problem_channels = await get_problem_channels(pool, limit=5)
    text = build_admin_dashboard_text(dashboard, recent_violations, problem_channels)
    target = message.message if isinstance(message, CallbackQuery) else message
    await target.answer(text, reply_markup=get_admin_keyboard())


@router.message(Command("admin"))
async def admin_command(message: Message) -> None:
    if not message.from_user:
        return
    logger.info("Admin dashboard requested by user=%s", message.from_user.id)
    await _send_admin_dashboard(message, message.from_user.id)


@router.callback_query(F.data == "admin:refresh")
async def admin_refresh_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.from_user:
        return
    await _send_admin_dashboard(callback, callback.from_user.id)


@router.message(Command("problem_channels"))
@router.callback_query(F.data == "admin:problem_channels")
async def admin_problem_channels(target: Message | CallbackQuery) -> None:
    user = target.from_user if isinstance(target, Message) else target.from_user
    if isinstance(target, CallbackQuery):
        await target.answer()
    if not user or not is_admin(user.id):
        logger.info("Non-admin tried /problem_channels user=%s", user.id if user else None)
        receiver = target.message if isinstance(target, CallbackQuery) else target
        await receiver.answer("Эта команда доступна только администратору сервиса")
        return

    pool = get_pool()
    rows = await get_problem_channels(pool, limit=10)
    receiver = target.message if isinstance(target, CallbackQuery) else target
    await receiver.answer(_format_problem_channels(rows), reply_markup=get_admin_keyboard())


@router.message(Command("violations"))
@router.callback_query(F.data == "admin:violations")
async def admin_violations(target: Message | CallbackQuery) -> None:
    user = target.from_user if isinstance(target, Message) else target.from_user
    if isinstance(target, CallbackQuery):
        await target.answer()
    if not user or not is_admin(user.id):
        logger.info("Non-admin tried /violations user=%s", user.id if user else None)
        receiver = target.message if isinstance(target, CallbackQuery) else target
        await receiver.answer("Эта команда доступна только администратору сервиса")
        return

    pool = get_pool()
    rows = await get_recent_violations(pool, limit=20)
    receiver = target.message if isinstance(target, CallbackQuery) else target
    await receiver.answer(_format_violations(rows), reply_markup=get_admin_keyboard())


@router.message(Command("payments_admin"))
async def admin_payments_summary(message: Message) -> None:
    if not message.from_user or not is_admin(message.from_user.id):
        logger.info("Non-admin tried /payments_admin user=%s", message.from_user.id if message.from_user else None)
        await message.answer("Эта команда доступна только администратору сервиса")
        return
    pool = get_pool()
    dashboard = await get_admin_dashboard_stats(pool)
    count = int(dashboard["payments_success_count"] or 0)
    turnover = int(dashboard["turnover_amount"] or 0)
    commission = int(dashboard["commission_amount"] or 0)
    avg = int(turnover / count) if count > 0 else 0
    await message.answer(
        "Платежи\n"
        f"Успешных: {count}\n"
        f"Оборот: {turnover:,} ₽\n"
        f"Комиссия: {commission:,} ₽\n"
        f"Средний чек: {avg:,} ₽".replace(",", " "),
        reply_markup=get_admin_keyboard(),
    )
