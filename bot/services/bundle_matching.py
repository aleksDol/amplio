import math


def is_free_match(channel_subscribers: int, creator_subscribers: int) -> bool:
    min_allowed = math.floor(creator_subscribers * 0.8)
    max_allowed = math.ceil(creator_subscribers * 1.2)
    return min_allowed <= channel_subscribers <= max_allowed


def is_paid_match(bundle_has_paid_slot: bool, paid_slot_taken: bool, same_niche: bool) -> bool:
    return bundle_has_paid_slot and not paid_slot_taken and same_niche


def resolve_available_entry_types(
    *,
    same_niche: bool,
    channel_subscribers: int | None,
    creator_subscribers: int | None,
    bundle_has_paid_slot: bool,
    paid_slot_taken: bool,
) -> dict:
    if not same_niche:
        return {"free_allowed": False, "paid_allowed": False, "reason": "Ниша не совпадает"}

    free_allowed = False
    if channel_subscribers is not None and creator_subscribers is not None:
        free_allowed = is_free_match(channel_subscribers, creator_subscribers)

    paid_allowed = is_paid_match(bundle_has_paid_slot, paid_slot_taken, same_niche)

    if free_allowed or paid_allowed:
        return {"free_allowed": free_allowed, "paid_allowed": paid_allowed, "reason": None}

    return {
        "free_allowed": False,
        "paid_allowed": False,
        "reason": "Канал не подходит по условиям вступления",
    }
