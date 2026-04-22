from asyncpg import Pool

from repositories.bundles import get_bundle_by_id
from repositories.participants import get_active_participants_with_channels


def _channel_name(username: str | None, title: str | None, channel_id: int) -> str:
    if username:
        return username
    if title:
        return title
    return f"Канал #{channel_id}"


async def build_bundle_preview_text(pool: Pool, bundle_id: int) -> str:
    bundle = await get_bundle_by_id(pool, bundle_id)
    if not bundle:
        raise ValueError("Bundle not found")

    participants = await get_active_participants_with_channels(pool, bundle_id)
    creator_channel_id = int(bundle["creator_channel_id"])
    ordered = sorted(
        participants,
        key=lambda row: (0 if int(row["channel_id"]) == creator_channel_id else 1, int(row["id"])),
    )

    lines: list[str] = [f"Подборка каналов по теме: {bundle['niche']}", ""]
    for participant in ordered:
        channel_label = _channel_name(
            username=participant["channel_username"],
            title=participant["channel_title"],
            channel_id=int(participant["channel_id"]),
        )
        ad_text = (participant["ad_text"] or "").strip()
        lines.append(f"{channel_label} — {ad_text}")

    lines.extend(["", "Подписывайся на лучшие каналы из подборки 🚀"])
    return "\n".join(lines)
