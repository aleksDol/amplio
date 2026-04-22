import asyncio
import base64
import json
import uuid
from typing import Any, Optional
from urllib import error, request

from config import settings


YOOKASSA_API_BASE = "https://api.yookassa.ru/v3/payments"


class YooKassaError(RuntimeError):
    pass


def _build_auth_header() -> str:
    token = f"{settings.yookassa_shop_id}:{settings.yookassa_secret_key}".encode("utf-8")
    return "Basic " + base64.b64encode(token).decode("ascii")


def _http_json(
    method: str,
    url: str,
    payload: Optional[dict[str, Any]] = None,
    idempotence_key: Optional[str] = None,
) -> dict[str, Any]:
    headers = {
        "Authorization": _build_auth_header(),
        "Content-Type": "application/json",
    }
    if idempotence_key:
        headers["Idempotence-Key"] = idempotence_key

    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    req = request.Request(url=url, data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=20) as resp:
            response_body = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        raise YooKassaError(f"HTTP {exc.code}: {details}") from exc
    except error.URLError as exc:
        raise YooKassaError(f"Network error: {exc.reason}") from exc
    try:
        return json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise YooKassaError("Invalid JSON response from YooKassa.") from exc


async def create_payment(
    amount_rub: int,
    description: str,
    metadata: dict[str, str],
    idempotence_key: Optional[str] = None,
) -> dict[str, Any]:
    if not idempotence_key:
        idempotence_key = str(uuid.uuid4())

    payload = {
        "amount": {"value": f"{amount_rub}.00", "currency": "RUB"},
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": settings.yookassa_return_url or "https://example.com",
        },
        "description": description[:128],
        "metadata": metadata,
    }
    return await asyncio.to_thread(
        _http_json,
        "POST",
        YOOKASSA_API_BASE,
        payload,
        idempotence_key,
    )


async def get_payment(yukassa_id: str) -> dict[str, Any]:
    return await asyncio.to_thread(
        _http_json,
        "GET",
        f"{YOOKASSA_API_BASE}/{yukassa_id}",
        None,
        None,
    )


def parse_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    event = payload.get("event")
    obj = payload.get("object") or {}
    return {
        "event": event,
        "yukassa_id": obj.get("id"),
        "status": obj.get("status"),
        "raw": payload,
    }
