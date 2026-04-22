import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database.connection import get_pool
from keyboards.find_bundle import (
    get_find_bundle_card_keyboard,
    get_find_bundle_channel_keyboard,
    get_find_bundle_empty_results_keyboard,
    get_find_bundle_no_ready_channels_keyboard,
    get_find_bundle_results_keyboard,
    get_pending_participations_empty_keyboard,
    get_pending_participations_keyboard,
)
from keyboards.payments import get_payment_actions_keyboard
from repositories.bundles import (
    bundle_has_free_slots,
    bundle_paid_slot_taken,
    count_active_bundle_participants,
    get_bundle_with_creator,
    get_open_bundles_for_channel,
    update_bundle_status,
)
from repositories.channels import get_channel_by_id, get_user_ready_channels
from repositories.participants import (
    channel_already_in_bundle,
    channel_has_bundle_at_time,
    create_participant,
    get_participant_with_bundle_channel,
    get_user_pending_participations,
)
from services.payment_service import (
    PaymentServiceError,
    create_paid_participation_request,
    expire_stale_payments,
)
from services.bundle_preview_service import try_start_preview_for_bundle
from services.bundle_matching import resolve_available_entry_types
from services.datetime_utils import format_datetime_for_preview
from services.notifications import notify_creator_about_new_participant
from states.find_bundle import FindBundleStates


logger = logging.getLogger(__name__)
router = Router()


def _is_channel_ready(channel) -> bool:
    return (
        bool(channel["bot_is_admin"])
        and bool(channel["is_verified"])
        and channel["niche"] is not None
        and channel["subscribers"] is not None
    )


def _format_number(value: int | None) -> str:
    if value is None:
        return "не задано"
    return f"{value:,}".replace(",", " ")


def _parse_int_suffix(data: str, prefix: str) -> int | None:
    if not data.startswith(prefix):
        return None
    suffix = data[len(prefix) :]
    if not suffix.isdigit():
        return None
    return int(suffix)


async def _load_ready_channels(user_id: int):
    pool = get_pool()
    channels = await get_user_ready_channels(pool, user_id)
    return [channel for channel in channels if _is_channel_ready(channel)]


async def _evaluate_bundle_for_channel(pool, seeker_channel, bundle) -> dict:
    bundle_id = bundle["id"]
    scheduled_at = bundle["scheduled_at"]
    slots = int(bundle["slots"])

    if bundle["status"] != "open":
        return {"available": False, "reason": "Подборка закрыта"}

    active_count = await count_active_bundle_participants(pool, bundle_id)
    has_slots = await bundle_has_free_slots(pool, bundle_id)
    if not has_slots:
        return {
            "available": False,
            "reason": "Подборка заполнена",
            "active_count": active_count,
            "slots": slots,
        }

    already_joined = await channel_already_in_bundle(pool, bundle_id, seeker_channel["id"])
    if already_joined:
        return {"available": False, "reason": "Канал уже участвует в этой подборке"}

    time_conflict = await channel_has_bundle_at_time(pool, seeker_channel["id"], scheduled_at)
    if time_conflict:
        return {"available": False, "reason": "У канала уже есть участие на это время"}

    paid_taken = await bundle_paid_slot_taken(pool, bundle_id)
    match = resolve_available_entry_types(
        same_niche=seeker_channel["niche"] == bundle["niche"],
        channel_subscribers=seeker_channel["subscribers"],
        creator_subscribers=bundle["creator_subscribers"],
        bundle_has_paid_slot=bool(bundle["has_paid_slot"]),
        paid_slot_taken=paid_taken,
    )
    return {
        "available": bool(match["free_allowed"] or match["paid_allowed"]),
        "free_allowed": bool(match["free_allowed"]),
        "paid_allowed": bool(match["paid_allowed"]),
        "reason": match["reason"],
        "active_count": active_count,
        "slots": slots,
        "paid_taken": paid_taken,
    }


async def _show_channels_for_find(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user:
        return
    ready_channels = await _load_ready_channels(callback.from_user.id)
    await state.set_state(FindBundleStates.waiting_for_channel_selection)
    await state.set_data({})

    if not ready_channels:
        await callback.message.answer(
            "У тебя пока нет каналов, готовых к участию в подборках",
            reply_markup=get_find_bundle_no_ready_channels_keyboard(),
        )
        return

    await callback.message.answer(
        "Выбери канал, для которого ищем подборки",
        reply_markup=get_find_bundle_channel_keyboard(ready_channels),
    )


async def _render_results_for_channel(message_target, state: FSMContext, channel_id: int) -> None:
    pool = get_pool()
    channel = await get_channel_by_id(pool, channel_id)
    if not channel:
        await message_target.answer("Канал не найден. Выбери другой канал.")
        return

    logger.info("Searching bundles for channel_id=%s", channel_id)
    bundles = await get_open_bundles_for_channel(pool, channel_id)

    available_bundle_ids: list[int] = []
    cards: list[str] = []
    reject_reason_counts: dict[str, int] = {}

    for bundle in bundles:
        eval_result = await _evaluate_bundle_for_channel(pool, channel, bundle)
        if not eval_result.get("available"):
            reason = str(eval_result.get("reason") or "Подборка недоступна")
            reject_reason_counts[reason] = reject_reason_counts.get(reason, 0) + 1
            continue

        bundle_id = int(bundle["id"])
        active_count = int(eval_result.get("active_count", 0))
        slots = int(eval_result.get("slots", bundle["slots"]))
        free_allowed = bool(eval_result.get("free_allowed"))
        paid_allowed = bool(eval_result.get("paid_allowed"))
        paid_price = bundle["paid_slot_price"]
        creator_name = bundle["creator_username"] or bundle["creator_title"] or f"Канал #{bundle['creator_channel_id']}"
        paid_text = "нет"
        if bundle["has_paid_slot"]:
            paid_text = f"{_format_number(paid_price)} ₽" if paid_price else "доступно"
        free_text = "доступно ✅" if free_allowed else "недоступно"
        paid_availability = "доступно ✅" if paid_allowed else "недоступно"

        cards.append(
            (
                f"Подборка #{bundle_id}\n"
                f"Организатор: {creator_name}\n"
                f"Публикация: {format_datetime_for_preview(bundle['scheduled_at'])}\n"
                f"Участников: {active_count} из {slots}\n"
                f"Бесплатное участие: {free_text}\n"
                f"Платное место: {paid_text}\n"
                f"Платное участие: {paid_availability}"
            )
        )
        available_bundle_ids.append(bundle_id)

    channel_name = channel["username"] or channel["title"] or f"Канал #{channel_id}"
    intro = (
        f"Ищу подборки для {channel_name}\n"
        f"Тематика: {channel['niche']}\n"
        f"Подписчики: {_format_number(channel['subscribers'])}"
    )
    await message_target.answer(intro)

    logger.info("Found %s matching bundles for channel_id=%s", len(available_bundle_ids), channel_id)
    await state.set_state(FindBundleStates.waiting_for_bundle_selection)
    await state.update_data(channel_id=channel_id)

    if not available_bundle_ids:
        if reject_reason_counts:
            reasons = sorted(reject_reason_counts.items(), key=lambda item: (-item[1], item[0]))
            reason_lines = "\n".join([f"{reason}: {count}" for reason, count in reasons[:3]])
            await message_target.answer(
                "Сейчас нет доступных подборок для вступления.\n"
                "Основные причины:\n"
                f"{reason_lines}",
                reply_markup=get_find_bundle_empty_results_keyboard(),
            )
        else:
            await message_target.answer(
                "Сейчас подходящих подборок нет",
                reply_markup=get_find_bundle_empty_results_keyboard(),
            )
        return

    await message_target.answer(
        "Подходящие подборки:\n\n" + "\n\n".join(cards),
        reply_markup=get_find_bundle_results_keyboard(available_bundle_ids),
    )


def _format_participation_type(participant_type: str, participant_status: str) -> str:
    if participant_status == "awaiting_payment":
        return "Ожидает оплату"
    if participant_type == "paid":
        return "Платное участие"
    return "Бесплатное участие"


async def _render_pending_participations(message_target, state: FSMContext, user_id: int) -> None:
    pool = get_pool()
    participations = await get_user_pending_participations(pool, user_id)

    await state.set_state(FindBundleStates.waiting_for_bundle_selection)
    await state.set_data({"participations_mode": True})

    if not participations:
        await message_target.answer(
            "У тебя пока нет участий в подборках, которые ещё набирают участников.",
            reply_markup=get_pending_participations_empty_keyboard(),
        )
        return

    cards: list[str] = []
    participant_ids: list[int] = []
    for row in participations:
        participant_id = int(row["participant_id"])
        participant_ids.append(participant_id)
        creator_name = row["creator_username"] or row["creator_title"] or f"Канал #{row['creator_channel_id']}"
        channel_name = row["participant_channel_username"] or row["participant_channel_title"] or f"Канал #{row['channel_id']}"
        cards.append(
            (
                f"Участие #{participant_id}\n"
                f"Подборка #{row['bundle_id']}\n"
                f"Твой канал: {channel_name}\n"
                f"Организатор: {creator_name}\n"
                f"Тематика: {row['niche']}\n"
                f"Публикация: {format_datetime_for_preview(row['scheduled_at'])}\n"
                f"Участников: {int(row['used_slots'])} из {int(row['slots'])}\n"
                f"Формат: {_format_participation_type(str(row['participant_type']), str(row['participant_status']))}"
            )
        )

    await message_target.answer(
        "Твои участия в подборках, которые сейчас набираются:\n\n" + "\n\n".join(cards),
        reply_markup=get_pending_participations_keyboard(participant_ids),
    )


async def _show_bundle_card(
    callback: CallbackQuery,
    state: FSMContext,
    bundle_id: int,
    back_callback: str = "find_bundle:back_to_results",
) -> None:
    if not callback.from_user:
        return
    data = await state.get_data()
    channel_id = data.get("channel_id")
    if not isinstance(channel_id, int):
        await callback.message.answer("Сначала выбери канал для поиска подборок.")
        await _show_channels_for_find(callback, state)
        return

    pool = get_pool()
    channel = await get_channel_by_id(pool, channel_id)
    bundle = await get_bundle_with_creator(pool, bundle_id)
    if not channel or not bundle:
        await callback.message.answer("Подборка не найдена или уже недоступна.")
        return

    logger.info("User %s opened bundle card bundle_id=%s via channel_id=%s", callback.from_user.id, bundle_id, channel_id)
    eval_result = await _evaluate_bundle_for_channel(pool, channel, bundle)
    free_allowed = bool(eval_result.get("free_allowed", False))
    paid_allowed = bool(eval_result.get("paid_allowed", False))

    active_count = int(eval_result.get("active_count", 0))
    slots = int(eval_result.get("slots", bundle["slots"]))
    creator_name = bundle["creator_username"] or bundle["creator_title"] or f"Канал #{bundle['creator_channel_id']}"
    paid_label = "нет"
    if bundle["has_paid_slot"]:
        paid_label = f"{_format_number(bundle['paid_slot_price'])} ₽" if bundle["paid_slot_price"] else "да"

    if free_allowed and paid_allowed:
        entry_text = "Можно бесплатно и платно"
    elif free_allowed:
        entry_text = "Можно бесплатно"
    elif paid_allowed:
        entry_text = "Можно только платно"
    else:
        entry_text = eval_result.get("reason") or "Нельзя вступить"

    text = (
        f"Подборка #{bundle_id}\n"
        f"Организатор: {creator_name}\n"
        f"Тематика: {bundle['niche']}\n"
        f"Публикация: {format_datetime_for_preview(bundle['scheduled_at'])}\n"
        f"Участников: {active_count} из {slots}\n"
        f"Срок жизни поста: {bundle['post_lifetime_hours']} часов\n"
        f"Платное место: {paid_label}\n"
        f"Доступность для канала: {entry_text}"
    )

    await state.set_state(FindBundleStates.waiting_for_bundle_selection)
    await state.update_data(bundle_id=bundle_id)
    await callback.message.answer(
        text,
        reply_markup=get_find_bundle_card_keyboard(bundle_id, free_allowed, paid_allowed, back_callback=back_callback),
    )


async def _pick_best_channel_for_bundle(user_id: int, bundle_id: int):
    pool = get_pool()
    ready_channels = await get_user_ready_channels(pool, user_id)
    bundle = await get_bundle_with_creator(pool, bundle_id)
    if not bundle:
        return None

    scored: list[tuple[int, int]] = []
    for channel in ready_channels:
        eval_result = await _evaluate_bundle_for_channel(pool, channel, bundle)
        if not eval_result.get("available"):
            continue
        free_allowed = bool(eval_result.get("free_allowed"))
        creator_subscribers = int(bundle["creator_subscribers"] or 0)
        distance = abs(int(channel["subscribers"]) - creator_subscribers)
        priority = 0 if free_allowed else 1
        scored.append((priority, distance, int(channel["id"])))
    if not scored:
        return None
    scored.sort(key=lambda x: (x[0], x[1], x[2]))
    return scored[0][2]


@router.callback_query(F.data == "find_bundle")
async def start_find_bundle(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    user_id = callback.from_user.id if callback.from_user else 0
    logger.info("User %s opened find bundle flow", user_id)
    await _show_channels_for_find(callback, state)


@router.callback_query(F.data == "participations:pending")
async def open_pending_participations(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.from_user:
        return
    await _render_pending_participations(callback.message, state, callback.from_user.id)


@router.callback_query(F.data == "find_bundle:choose_channel")
@router.callback_query(F.data == "find_bundle:back_to_results", StateFilter(FindBundleStates.waiting_for_bundle_selection))
@router.callback_query(F.data == "participations:back_to_list", StateFilter(FindBundleStates.waiting_for_bundle_selection))
async def choose_channel_or_back(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.data == "participations:back_to_list":
        if callback.from_user:
            await _render_pending_participations(callback.message, state, callback.from_user.id)
        return

    if callback.data == "find_bundle:back_to_results":
        data = await state.get_data()
        channel_id = data.get("channel_id")
        if isinstance(channel_id, int):
            await _render_results_for_channel(callback.message, state, channel_id)
            return
    await _show_channels_for_find(callback, state)


@router.callback_query(F.data == "find_bundle:refresh", StateFilter(FindBundleStates.waiting_for_bundle_selection))
async def refresh_find_results(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    channel_id = data.get("channel_id")
    if not isinstance(channel_id, int):
        await _show_channels_for_find(callback, state)
        return
    await _render_results_for_channel(callback.message, state, channel_id)


@router.callback_query(F.data == "participations:refresh", StateFilter(FindBundleStates.waiting_for_bundle_selection))
async def refresh_pending_participations(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.from_user:
        return
    await _render_pending_participations(callback.message, state, callback.from_user.id)


@router.callback_query(F.data.startswith("find_bundle:channel:"), StateFilter(FindBundleStates.waiting_for_channel_selection))
async def select_channel_for_find(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.data or not callback.from_user:
        return

    channel_id = _parse_int_suffix(callback.data, "find_bundle:channel:")
    if channel_id is None:
        await callback.message.answer("Не удалось выбрать канал. Попробуй снова.")
        return

    pool = get_pool()
    channel = await get_channel_by_id(pool, channel_id)
    if not channel or channel["owner_id"] != callback.from_user.id or not _is_channel_ready(channel):
        await callback.message.answer("Этот канал пока нельзя использовать для вступления.")
        return

    logger.info("User %s selected channel_id=%s for find flow", callback.from_user.id, channel_id)
    await state.update_data(channel_id=channel_id)
    await _render_results_for_channel(callback.message, state, channel_id)


@router.callback_query(F.data.startswith("find_bundle:view:"), StateFilter(FindBundleStates.waiting_for_bundle_selection))
async def open_bundle_for_find(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.data:
        return
    bundle_id = _parse_int_suffix(callback.data, "find_bundle:view:")
    if bundle_id is None:
        await callback.message.answer("Не удалось открыть подборку.")
        return
    await _show_bundle_card(callback, state, bundle_id)


@router.callback_query(F.data.startswith("participations:open:"), StateFilter(FindBundleStates.waiting_for_bundle_selection))
async def open_pending_participation_bundle(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.data or not callback.from_user:
        return

    participant_id = _parse_int_suffix(callback.data, "participations:open:")
    if participant_id is None:
        await callback.message.answer("Не удалось открыть участие.")
        return

    pool = get_pool()
    participant = await get_participant_with_bundle_channel(pool, participant_id)
    if not participant:
        await callback.message.answer("Это участие уже недоступно.")
        return
    if int(participant["owner_id"]) != int(callback.from_user.id):
        await callback.message.answer("Это участие тебе недоступно.")
        return

    await state.set_state(FindBundleStates.waiting_for_bundle_selection)
    await state.set_data(
        {
            "participations_mode": True,
            "channel_id": int(participant["channel_id"]),
            "bundle_id": int(participant["bundle_id"]),
            "participant_id": participant_id,
        }
    )
    await _show_bundle_card(callback, state, int(participant["bundle_id"]), back_callback="participations:back_to_list")


@router.callback_query(F.data.startswith("notifications:open_bundle:"))
async def open_bundle_from_notification(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.data or not callback.from_user:
        return

    bundle_id = _parse_int_suffix(callback.data, "notifications:open_bundle:")
    if bundle_id is None:
        await callback.message.answer("Не удалось открыть подборку из уведомления.")
        return

    best_channel_id = await _pick_best_channel_for_bundle(callback.from_user.id, bundle_id)
    if best_channel_id is None:
        await callback.message.answer(
            "Для этой подборки сейчас нет подходящих готовых каналов. Проверь свои каналы и попробуй снова."
        )
        return

    await state.set_state(FindBundleStates.waiting_for_bundle_selection)
    await state.set_data({"channel_id": best_channel_id, "bundle_id": bundle_id})
    await _show_bundle_card(callback, state, bundle_id)


@router.callback_query(F.data.startswith("find_bundle:join_free:"), StateFilter(FindBundleStates.waiting_for_bundle_selection))
async def join_bundle_free(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.data:
        return
    bundle_id = _parse_int_suffix(callback.data, "find_bundle:join_free:")
    if bundle_id is None:
        await callback.message.answer("Не удалось начать вступление.")
        return
    await state.set_state(FindBundleStates.waiting_for_free_ad_text)
    await state.update_data(bundle_id=bundle_id, entry_type="free")
    await callback.message.answer("Отправь рекламный текст своего канала до 200 символов")


@router.callback_query(F.data.startswith("find_bundle:join_paid:"), StateFilter(FindBundleStates.waiting_for_bundle_selection))
async def join_bundle_paid(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.data:
        return
    bundle_id = _parse_int_suffix(callback.data, "find_bundle:join_paid:")
    if bundle_id is None:
        await callback.message.answer("Не удалось начать вступление.")
        return
    await state.set_state(FindBundleStates.waiting_for_paid_ad_text)
    await state.update_data(bundle_id=bundle_id, entry_type="paid")
    await callback.message.answer("Отправь рекламный текст своего канала до 200 символов")


async def _finalize_join(message: Message, state: FSMContext, entry_type: str) -> None:
    if not message.from_user:
        return
    text = (message.text or "").strip()
    if not text or len(text) > 200:
        await message.answer("Отправь короткий рекламный текст до 200 символов")
        return

    data = await state.get_data()
    channel_id = data.get("channel_id")
    bundle_id = data.get("bundle_id")
    if not isinstance(channel_id, int) or not isinstance(bundle_id, int):
        await state.clear()
        await message.answer("Не удалось завершить вступление. Начни поиск заново.")
        return

    pool = get_pool()
    await expire_stale_payments(pool)
    channel = await get_channel_by_id(pool, channel_id)
    bundle = await get_bundle_with_creator(pool, bundle_id)
    if not channel or channel["owner_id"] != message.from_user.id or not bundle:
        await state.clear()
        await message.answer("Подборка больше недоступна. Обнови список и выбери другую.")
        return

    if bundle["status"] != "open":
        await message.answer("Похоже, эта подборка уже недоступна. Обнови список и выбери другую")
        await state.set_state(FindBundleStates.waiting_for_bundle_selection)
        await _render_results_for_channel(message, state, channel_id)
        return

    if await channel_already_in_bundle(pool, bundle_id, channel_id):
        logger.info("Repeated join attempt channel_id=%s bundle_id=%s", channel_id, bundle_id)
        await message.answer("Этот канал уже участвует в подборке")
        return

    if await channel_has_bundle_at_time(pool, channel_id, bundle["scheduled_at"]):
        logger.info("Time conflict join attempt channel_id=%s bundle_id=%s", channel_id, bundle_id)
        await message.answer("У этого канала уже есть участие в подборке на это время")
        return

    has_slots = await bundle_has_free_slots(pool, bundle_id)
    if not has_slots:
        logger.info("Bundle became full while joining bundle_id=%s", bundle_id)
        await message.answer("Похоже, эта подборка уже заполнилась. Обнови список и выбери другую")
        await state.set_state(FindBundleStates.waiting_for_bundle_selection)
        await _render_results_for_channel(message, state, channel_id)
        return

    paid_taken = await bundle_paid_slot_taken(pool, bundle_id)
    availability = resolve_available_entry_types(
        same_niche=channel["niche"] == bundle["niche"],
        channel_subscribers=channel["subscribers"],
        creator_subscribers=bundle["creator_subscribers"],
        bundle_has_paid_slot=bool(bundle["has_paid_slot"]),
        paid_slot_taken=paid_taken,
    )

    if entry_type == "free" and not availability["free_allowed"]:
        await message.answer("Бесплатное участие в этой подборке недоступно для выбранного канала")
        return
    if entry_type == "paid" and not availability["paid_allowed"]:
        await message.answer("Платное место в этой подборке сейчас недоступно")
        return

    if entry_type == "free":
        created = await create_participant(
            pool=pool,
            bundle_id=bundle_id,
            channel_id=channel_id,
            participant_type="free",
            ad_text=text,
            confirmed=True,
            status="active",
        )
        if not created:
            await message.answer("Не удалось вступить в подборку. Попробуй снова.")
            return

        await notify_creator_about_new_participant(message.bot, pool, int(created["id"]))

        active_count = await count_active_bundle_participants(pool, bundle_id)
        if active_count >= int(bundle["slots"]):
            await update_bundle_status(pool, bundle_id, "full")
            await try_start_preview_for_bundle(message.bot, pool, bundle_id)

        logger.info("Free join success user=%s channel_id=%s bundle_id=%s", message.from_user.id, channel_id, bundle_id)
        await message.answer("Ты вступил в подборку ✅")
    else:
        try:
            paid_result = await create_paid_participation_request(
                pool=pool,
                bundle_id=bundle_id,
                channel_id=channel_id,
                ad_text=text,
            )
        except PaymentServiceError as exc:
            await message.answer(str(exc))
            return
        logger.info(
            "Paid join request created user=%s channel_id=%s bundle_id=%s payment_id=%s",
            message.from_user.id,
            channel_id,
            bundle_id,
            paid_result.payment_id,
        )
        await message.answer(
            (
                (
                    "У тебя уже есть активная заявка на оплату для этой подборки\n"
                    if paid_result.reused_existing
                    else "Заявка на платное участие создана ✅\n"
                )
                + f"Стоимость: {paid_result.amount} ₽\n"
                + "Оплати участие в течение 30 минут"
            ),
            reply_markup=get_payment_actions_keyboard(
                payment_id=paid_result.payment_id,
                payment_url=paid_result.payment_url,
            ),
        )
        await state.set_state(FindBundleStates.waiting_for_bundle_selection)
        await state.update_data(entry_type=None, bundle_id=None)
        return

    await state.set_state(FindBundleStates.waiting_for_bundle_selection)
    await state.update_data(entry_type=None, bundle_id=None)
    await _render_results_for_channel(message, state, channel_id)


@router.message(FindBundleStates.waiting_for_free_ad_text)
async def receive_free_join_ad_text(message: Message, state: FSMContext) -> None:
    await _finalize_join(message, state, entry_type="free")


@router.message(FindBundleStates.waiting_for_paid_ad_text)
async def receive_paid_join_ad_text(message: Message, state: FSMContext) -> None:
    await _finalize_join(message, state, entry_type="paid")
