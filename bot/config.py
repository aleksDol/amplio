from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


def _load_env() -> None:
    project_root = Path(__file__).resolve().parent.parent
    bot_dir = Path(__file__).resolve().parent

    env_file = os.getenv("ENV_FILE", "").strip()
    candidates: list[Path] = []
    if env_file:
        path = Path(env_file)
        candidates.append(path if path.is_absolute() else Path.cwd() / path)

    candidates.extend(
        [
            project_root / ".env.production",
            project_root / ".env",
            bot_dir / ".env",
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            load_dotenv(dotenv_path=candidate, override=False)
            break


_load_env()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    yookassa_shop_id: str
    yookassa_secret_key: str
    yookassa_return_url: str
    yookassa_webhook_secret: str
    payment_timeout_minutes: int
    service_commission_percent: int
    admin_telegram_ids: tuple[int, ...]


def _parse_admin_ids(raw: str) -> tuple[int, ...]:
    ids: list[int] = []
    for chunk in raw.split(","):
        value = chunk.strip()
        if not value:
            continue
        if value.isdigit():
            ids.append(int(value))
    return tuple(ids)


def _load_settings() -> Settings:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    database_url = os.getenv("DATABASE_URL", "").strip()
    yookassa_shop_id = os.getenv("YOOKASSA_SHOP_ID", "").strip()
    yookassa_secret_key = os.getenv("YOOKASSA_SECRET_KEY", "").strip()
    yookassa_return_url = os.getenv("YOOKASSA_RETURN_URL", "").strip()
    yookassa_webhook_secret = os.getenv("YOOKASSA_WEBHOOK_SECRET", "").strip()
    payment_timeout_minutes_raw = os.getenv("PAYMENT_TIMEOUT_MINUTES", "30").strip()
    service_commission_percent_raw = os.getenv("SERVICE_COMMISSION_PERCENT", "20").strip()
    admin_ids_raw = os.getenv("ADMIN_TELEGRAM_IDS", "").strip()

    if not bot_token:
        raise ValueError("BOT_TOKEN is not set in environment variables.")
    if not database_url:
        raise ValueError("DATABASE_URL is not set in environment variables.")
    try:
        payment_timeout_minutes = int(payment_timeout_minutes_raw)
        service_commission_percent = int(service_commission_percent_raw)
    except ValueError as exc:
        raise ValueError("PAYMENT_TIMEOUT_MINUTES and SERVICE_COMMISSION_PERCENT must be integers.") from exc

    return Settings(
        bot_token=bot_token,
        database_url=database_url,
        yookassa_shop_id=yookassa_shop_id,
        yookassa_secret_key=yookassa_secret_key,
        yookassa_return_url=yookassa_return_url,
        yookassa_webhook_secret=yookassa_webhook_secret,
        payment_timeout_minutes=payment_timeout_minutes,
        service_commission_percent=service_commission_percent,
        admin_telegram_ids=_parse_admin_ids(admin_ids_raw),
    )


settings = _load_settings()


def is_admin(user_id: int) -> bool:
    return int(user_id) in settings.admin_telegram_ids
