import logging
import re
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database.connection import get_pool
from keyboards.create_bundle import (
    NICHES_BY_SLUG,
    get_bundle_confirmation_keyboard,
    get_bundle_created_keyboard,
    get_bundle_creator_channels_keyboard,
    get_bundle_date_keyboard,
    get_bundle_niche_choice_keyboard,
    get_bundle_niches_keyboard,
    get_bundle_post_lifetime_keyboard,
    get_bundle_slots_keyboard,
    get_no_ready_channels_keyboard,
)
from keyboards.main_menu import get_main_menu_keyboard
from repositories.bundles import channel_has_bundle_at_time, create_bundle
from repositories.channels import get_channel_by_id, get_user_channels
from repositories.participants import count_bundle_participants, create_participant
from services.datetime_utils import (
    combine_local_date_and_time,
    format_datetime_for_preview,
    get_date_by_choice,
    is_future_datetime,
)
from services.notifications import notify_admins_to_set_paid_price, send_bundle_notifications
from states.create_bundle import BundleCreateStates


logger = logging.getLogger(__name__)
router = Router()

TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _parse_int_suffix(data: str, prefix: str) -> int | None:
    if not data.startswith(prefix):
        return None
    suffix = data[len(prefix) :]
    if not suffix.isdigit():
        return None
    return int(suffix)


def _is_channel_ready(channel) -> bool:
    return (
        bool(channel["bot_is_admin"])
        and bool(channel["is_verified"])
        and channel["niche"] is not None
        and channel["subscribers"] is not None
    )


async def _ask_publish_date(message: Message | CallbackQuery) -> None:
    target = message.message if isinstance(message, CallbackQuery) else message
    await target.answer(
        "Выбери дату публикации",
        reply_markup=get_bundle_date_keyboard(),
    )


async def _show_preview(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    scheduled_at_raw = data.get("scheduled_at")
    if not isinstance(scheduled_at_raw, str):
        await message.answer("Не удалось подготовить превью. Начни создание подборки заново.")
        return

    scheduled_at = datetime.fromisoformat(scheduled_at_raw)
    channel_username = data.get("channel_username") or "без username"
    niche = data.get("niche") or "не выбрана"
    slots = data.get("slots")
    post_lifetime_hours = data.get("post_lifetime_hours")
    ad_text = data.get("ad_text") or ""

    preview_text = (
        "Проверь данные перед созданием подборки:\n\n"
        f"Канал: {channel_username}\n"
        f"Тематика: {niche}\n"
        f"Публикация: {format_datetime_for_preview(scheduled_at)}\n"
        f"Участников: {slots}\n"
        f"Срок поста: {post_lifetime_hours} часов\n"
        "Платное место: 1 (обязательное)\n"
        "Цена платного места: назначается администратором сервиса\n"
        f"Твой текст: {ad_text}"
    )
    await message.answer(preview_text, reply_markup=get_bundle_confirmation_keyboard())


@router.callback_query(F.data == "create_bundle")
@router.callback_query(F.data == "bundle:create:start")
async def start_create_bundle(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.from_user:
        return

    await state.clear()
    await state.set_state(BundleCreateStates.waiting_for_creator_channel)

    pool = get_pool()
    user_channels = await get_user_channels(pool, callback.from_user.id)
    ready_channels = [channel for channel in user_channels if _is_channel_ready(channel)]

    logger.info("Bundle create started by user=%s ready_channels=%s", callback.from_user.id, len(ready_channels))

    if not ready_channels:
        await callback.message.answer(
            "У тебя пока нет каналов, готовых к созданию подборки",
            reply_markup=get_no_ready_channels_keyboard(),
        )
        return

    await callback.message.answer(
        "Выбери канал, от имени которого создаём подборку",
        reply_markup=get_bundle_creator_channels_keyboard(ready_channels),
    )


@router.callback_query(
    F.data.startswith("bundle:create:channel:"),
    BundleCreateStates.waiting_for_creator_channel,
)
async def choose_creator_channel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.data or not callback.from_user:
        return

    channel_id = _parse_int_suffix(callback.data, "bundle:create:channel:")
    if channel_id is None:
        await callback.message.answer("Не удалось выбрать канал. Попробуй ещё раз.")
        return

    pool = get_pool()
    channel = await get_channel_by_id(pool, channel_id)
    if not channel or channel["owner_id"] != callback.from_user.id or not _is_channel_ready(channel):
        await callback.message.answer("Канал недоступен для создания подборки.")
        return

    channel_username = channel["username"] or channel["title"] or f"Канал #{channel_id}"
    logger.info("User %s selected creator_channel_id=%s", callback.from_user.id, channel_id)

    await state.set_state(BundleCreateStates.waiting_for_niche_choice)
    await state.set_data(
        {
            "creator_channel_id": channel_id,
            "channel_username": channel_username,
            "niche": channel["niche"],
        }
    )
    await callback.message.answer(f"Создаём подборку для канала {channel_username}")
    await callback.message.answer(
        f"Тематика подборки: {channel['niche']}",
        reply_markup=get_bundle_niche_choice_keyboard(),
    )


@router.callback_query(
    F.data == "bundle:create:niche:keep",
    BundleCreateStates.waiting_for_niche_choice,
)
async def keep_bundle_niche(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    niche = data.get("niche")
    if not isinstance(niche, str) or not niche.strip():
        await callback.message.answer("Не удалось определить тематику. Выбери её вручную.")
        await callback.message.answer(
            "Выбери тематику подборки",
            reply_markup=get_bundle_niches_keyboard(),
        )
        return

    await state.set_state(BundleCreateStates.waiting_for_time)
    await _ask_publish_date(callback)


@router.callback_query(
    F.data == "bundle:create:niche:change",
    BundleCreateStates.waiting_for_niche_choice,
)
async def change_bundle_niche(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        "Выбери тематику подборки",
        reply_markup=get_bundle_niches_keyboard(),
    )


@router.callback_query(
    F.data.startswith("bundle:create:niche:set:"),
    BundleCreateStates.waiting_for_niche_choice,
)
async def set_bundle_niche(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.data:
        return

    slug = callback.data.replace("bundle:create:niche:set:", "", 1)
    niche = NICHES_BY_SLUG.get(slug)
    if not niche:
        await callback.message.answer("Не удалось выбрать тематику. Попробуй ещё раз.")
        return

    await state.update_data(niche=niche)
    await state.set_state(BundleCreateStates.waiting_for_time)
    await _ask_publish_date(callback)


@router.callback_query(
    F.data.startswith("bundle:create:date:"),
    BundleCreateStates.waiting_for_time,
)
async def choose_bundle_date(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.data:
        return

    choice = callback.data.replace("bundle:create:date:", "", 1)
    selected_date = get_date_by_choice(choice)
    if selected_date is None:
        await callback.message.answer("Не удалось выбрать дату. Попробуй ещё раз.")
        return

    await state.update_data(scheduled_date=selected_date.isoformat())
    await callback.message.answer("Отправь время в формате HH:MM, например 18:30")


@router.message(BundleCreateStates.waiting_for_time)
async def receive_bundle_time(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Отправь время в формате HH:MM, например 18:30")
        return

    data = await state.get_data()
    scheduled_date_raw = data.get("scheduled_date")
    if not isinstance(scheduled_date_raw, str):
        await message.answer(
            "Сначала выбери дату публикации",
            reply_markup=get_bundle_date_keyboard(),
        )
        return

    match = TIME_PATTERN.fullmatch(message.text.strip())
    if not match:
        await message.answer("Отправь время в формате HH:MM, например 18:30")
        return

    hours = int(match.group(1))
    minutes = int(match.group(2))
    selected_date = datetime.fromisoformat(scheduled_date_raw).date()
    scheduled_local = combine_local_date_and_time(selected_date, hours, minutes)

    if not is_future_datetime(scheduled_local):
        await message.answer("Нельзя создать подборку на прошедшее время")
        return

    scheduled_at_db = scheduled_local.replace(tzinfo=None)
    await state.update_data(
        scheduled_time=message.text.strip(),
        scheduled_at=scheduled_at_db.isoformat(sep=" "),
    )
    await state.set_state(BundleCreateStates.waiting_for_slots)
    await message.answer(
        "Сколько всего участников будет в подборке?",
        reply_markup=get_bundle_slots_keyboard(),
    )


@router.callback_query(
    F.data.startswith("bundle:create:slots:"),
    BundleCreateStates.waiting_for_slots,
)
async def choose_bundle_slots(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.data:
        return

    slots = _parse_int_suffix(callback.data, "bundle:create:slots:")
    if slots not in {4, 5, 6}:
        await callback.message.answer("Выбери один из вариантов: 4, 5 или 6")
        return

    await state.update_data(slots=slots)
    await state.set_state(BundleCreateStates.waiting_for_post_lifetime)
    await callback.message.answer(
        "Сколько часов пост должен висеть до автоудаления?",
        reply_markup=get_bundle_post_lifetime_keyboard(),
    )


@router.callback_query(
    F.data.startswith("bundle:create:lifetime:"),
    BundleCreateStates.waiting_for_post_lifetime,
)
async def choose_post_lifetime(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.data:
        return

    lifetime = _parse_int_suffix(callback.data, "bundle:create:lifetime:")
    if lifetime not in {24, 48, 72}:
        await callback.message.answer("Выбери один из вариантов: 24, 48 или 72 часа")
        return

    await state.update_data(post_lifetime_hours=lifetime, has_paid_slot=True, paid_slot_price=None)
    await state.set_state(BundleCreateStates.waiting_for_ad_text)
    await callback.message.answer(
        "Отправь рекламный текст своего канала до 200 символов",
    )


@router.message(BundleCreateStates.waiting_for_ad_text)
async def receive_ad_text(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text or len(text) > 200:
        await message.answer("Отправь короткий рекламный текст до 200 символов")
        return

    await state.update_data(ad_text=text)
    await state.set_state(BundleCreateStates.waiting_for_confirmation)
    await _show_preview(message, state)


@router.callback_query(
    F.data == "bundle:create:confirm",
    BundleCreateStates.waiting_for_confirmation,
)
async def confirm_bundle_creation(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.from_user:
        return

    data = await state.get_data()
    creator_channel_id = data.get("creator_channel_id")
    niche = data.get("niche")
    scheduled_at_raw = data.get("scheduled_at")
    slots = data.get("slots")
    post_lifetime_hours = data.get("post_lifetime_hours")
    ad_text = data.get("ad_text")

    if (
        not isinstance(creator_channel_id, int)
        or not isinstance(niche, str)
        or not isinstance(scheduled_at_raw, str)
        or not isinstance(slots, int)
        or not isinstance(post_lifetime_hours, int)
        or not isinstance(ad_text, str)
    ):
        await state.clear()
        await callback.message.answer("Не удалось создать подборку. Начни сценарий заново.")
        return

    scheduled_at = datetime.fromisoformat(scheduled_at_raw)
    pool = get_pool()

    channel = await get_channel_by_id(pool, creator_channel_id)
    if not channel or channel["owner_id"] != callback.from_user.id:
        await state.clear()
        await callback.message.answer("Канал недоступен для создания подборки.")
        return

    conflict = await channel_has_bundle_at_time(
        pool=pool,
        creator_channel_id=creator_channel_id,
        scheduled_at=scheduled_at,
    )
    if conflict:
        logger.info(
            "Bundle schedule conflict for user=%s channel_id=%s scheduled_at=%s",
            callback.from_user.id,
            creator_channel_id,
            scheduled_at,
        )
        await callback.message.answer("У этого канала уже есть подборка на это время")
        return

    logger.info(
        "Creating bundle user=%s channel_id=%s niche=%s scheduled_at=%s slots=%s lifetime=%s paid=%s price=%s",
        callback.from_user.id,
        creator_channel_id,
        niche,
        scheduled_at,
        slots,
        post_lifetime_hours,
        True,
        None,
    )
    created_bundle = await create_bundle(
        pool=pool,
        creator_channel_id=creator_channel_id,
        niche=niche,
        scheduled_at=scheduled_at,
        slots=slots,
        has_paid_slot=True,
        paid_slot_price=None,
        post_lifetime_hours=post_lifetime_hours,
    )
    if not created_bundle:
        await state.clear()
        await callback.message.answer("Не удалось создать подборку. Попробуй ещё раз.")
        return

    created_participant = await create_participant(
        pool=pool,
        bundle_id=created_bundle["id"],
        channel_id=creator_channel_id,
        ad_text=ad_text,
        participant_type="free",
        confirmed=True,
        status="active",
    )
    if not created_participant:
        await state.clear()
        await callback.message.answer("Подборка создана, но не удалось добавить участника.")
        return

    participants_count = await count_bundle_participants(pool=pool, bundle_id=created_bundle["id"])
    logger.info(
        "Bundle created successfully bundle_id=%s first_participant_channel_id=%s",
        created_bundle["id"],
        creator_channel_id,
    )

    try:
        await send_bundle_notifications(
            bot=callback.bot,
            pool=pool,
            bundle_id=created_bundle["id"],
        )
    except Exception as exc:
        logger.info(
            "Bundle notifications failed bundle_id=%s error=%s",
            created_bundle["id"],
            str(exc),
        )

    try:
        await notify_admins_to_set_paid_price(
            bot=callback.bot,
            pool=pool,
            bundle_id=created_bundle["id"],
        )
    except Exception as exc:
        logger.info(
            "Notify admins to set paid price failed bundle_id=%s error=%s",
            created_bundle["id"],
            str(exc),
        )

    await state.clear()
    await callback.message.answer(
        f"Подборка создана ✅\nСейчас в ней {participants_count} из {slots} участников",
        reply_markup=get_bundle_created_keyboard(created_bundle["id"]),
    )


@router.callback_query(
    F.data == "bundle:create:cancel",
    StateFilter(
        BundleCreateStates.waiting_for_creator_channel,
        BundleCreateStates.waiting_for_niche_choice,
        BundleCreateStates.waiting_for_time,
        BundleCreateStates.waiting_for_slots,
        BundleCreateStates.waiting_for_post_lifetime,
        BundleCreateStates.waiting_for_ad_text,
        BundleCreateStates.waiting_for_confirmation,
    ),
)
async def cancel_bundle_creation(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.answer(
        "Создание подборки отменено. Возвращаю в главное меню.",
        reply_markup=get_main_menu_keyboard(),
    )


@router.callback_query(F.data.startswith("bundle:view:"))
async def open_bundle_stub(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer("Карточка подборки появится на следующем этапе.")
