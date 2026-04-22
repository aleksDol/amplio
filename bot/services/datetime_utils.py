from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


LOCAL_TZ = ZoneInfo("Europe/Amsterdam")


def get_local_now() -> datetime:
    return datetime.now(LOCAL_TZ)


def get_date_by_choice(choice: str) -> date | None:
    today = get_local_now().date()
    if choice == "today":
        return today
    if choice == "tomorrow":
        return today + timedelta(days=1)
    if choice == "day_after_tomorrow":
        return today + timedelta(days=2)
    return None


def combine_local_date_and_time(target_date: date, hour: int, minute: int) -> datetime:
    return datetime(
        year=target_date.year,
        month=target_date.month,
        day=target_date.day,
        hour=hour,
        minute=minute,
        tzinfo=LOCAL_TZ,
    )


def is_future_datetime(value: datetime) -> bool:
    return value > get_local_now()


def format_datetime_for_preview(value: datetime) -> str:
    return value.strftime("%d.%m.%Y %H:%M")
