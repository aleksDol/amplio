import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import is_admin
from database.connection import get_pool
from keyboards.admin import get_admin_keyboard
from repositories.bundles import get_bundle_with_creator, update_bundle_paid_slot_price
from repositories.stats import (
    get_admin_dashboard_stats,
    get_problem_channels,
    get_recent_violations,
)
from services.datetime_utils import format_datetime_for_preview
from services.notifications import send_bundle_notifications
from services.stats_service import build_admin_dashboard_text
from states.admin import AdminStates


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


def _parse_int_suffix(data: str, prefix: str) -> int | None:
    if not data.startswith(prefix):
        return None
    suffix = data[len(prefix) :]
    if not suffix.isdigit():
        return None
    return int(suffix)


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


@router.callback_query(F.data.startswith("admin:set_paid_price:"))
async def admin_set_paid_price_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.message.answer("Эта команда доступна только администратору сервиса")
        return
    if not callback.data:
        return

    bundle_id = _parse_int_suffix(callback.data, "admin:set_paid_price:")
    if bundle_id is None:
        await callback.message.answer("Не удалось определить подборку.")
        return

    pool = get_pool()
    bundle = await get_bundle_with_creator(pool, bundle_id)
    if not bundle:
        await callback.message.answer("Подборка не найдена.")
        return

    creator_name = bundle["creator_username"] or bundle["creator_title"] or f"Канал #{bundle['creator_channel_id']}"
    await state.set_state(AdminStates.waiting_for_paid_slot_price)
    await state.set_data({"bundle_id": bundle_id})
    await callback.message.answer(
        "Назначение цены платного места\n"
        f"Подборка #{bundle_id}\n"
        f"Организатор: {creator_name}\n"
        f"Публикация: {format_datetime_for_preview(bundle['scheduled_at'])}\n\n"
        "Отправь цену в рублях (например: 2000)."
    )


@router.message(AdminStates.waiting_for_paid_slot_price)
async def admin_set_paid_price_submit(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("Эта команда доступна только администратору сервиса")
        return

    raw = (message.text or "").strip().replace(" ", "")
    if not raw.isdigit():
        await message.answer("Отправь цену числом, например: 2000")
        return

    price = int(raw)
    if price <= 0 or price > 1_000_000:
        await message.answer("Отправь цену от 1 до 1 000 000")
        return

    data = await state.get_data()
    bundle_id = data.get("bundle_id")
    if not isinstance(bundle_id, int):
        await state.clear()
        await message.answer("Не удалось определить подборку. Нажми кнопку назначения цены ещё раз.")
        return

    pool = get_pool()
    updated = await update_bundle_paid_slot_price(pool, bundle_id, price)
    if not updated:
        await state.clear()
        await message.answer("Не удалось назначить цену. Возможно, подборка уже недоступна.")
        return

    try:
        await send_bundle_notifications(message.bot, pool, bundle_id)
    except Exception as exc:
        logger.info("Resend bundle notifications after paid price set failed bundle_id=%s error=%s", bundle_id, str(exc))

    await state.clear()
    await message.answer(
        f"Цена платного места для подборки #{bundle_id} установлена: {price:,} ₽".replace(",", " "),
        reply_markup=get_admin_keyboard(),
    )
