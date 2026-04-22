from asyncpg import Record


def _fmt_int(value) -> int:
    return int(value or 0)


def _fmt_money(value) -> str:
    return f"{_fmt_int(value):,}".replace(",", " ")


def _success_rate(completed: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((completed / total) * 100, 1)


def build_channel_stats_text(channel_stats: Record) -> str:
    total = _fmt_int(channel_stats["participations_count"])
    completed = _fmt_int(channel_stats["completed_participations_count"])
    rate = _success_rate(completed, total)
    channel_name = channel_stats["username"] or channel_stats["title"] or f"Канал #{channel_stats['id']}"
    return (
        f"Статистика канала {channel_name}\n"
        f"Рейтинг: {float(channel_stats['rating'] or 0.0):.1f}\n"
        f"Подписчики: {_fmt_money(channel_stats['subscribers'])}\n"
        f"Участий: {total}\n"
        f"Бесплатных: {_fmt_int(channel_stats['free_participations_count'])}\n"
        f"Платных: {_fmt_int(channel_stats['paid_participations_count'])}\n"
        f"Завершённых: {completed}\n"
        f"Нарушений: {_fmt_int(channel_stats['violations_count'])}\n"
        f"Отмен после превью: {_fmt_int(channel_stats['cancelled_after_preview_count'])}\n"
        f"Успешность: {rate}%"
    )


def build_user_stats_text(global_stats: Record, channels_stats: list[Record]) -> str:
    lines = [
        "Твоя статистика",
        f"Каналов: {_fmt_int(global_stats['channels_count'])}",
        f"Готовых: {_fmt_int(global_stats['ready_channels_count'])}",
        f"Создано подборок: {_fmt_int(global_stats['created_bundles_count'])}",
        f"Участий: {_fmt_int(global_stats['participations_count'])}",
        f"Успешно завершено: {_fmt_int(global_stats['completed_participations_count'])}",
        f"Нарушений: {_fmt_int(global_stats['violations_count'])}",
        f"Платных участий: {_fmt_int(global_stats['paid_participations_count'])}",
        f"Бесплатных участий: {_fmt_int(global_stats['free_participations_count'])}",
    ]
    if channels_stats:
        lines.append("")
        lines.append("Каналы:")
        for channel in channels_stats:
            name = channel["username"] or channel["title"] or f"Канал #{channel['id']}"
            lines.append(
                f"{name} — рейтинг {float(channel['rating'] or 0.0):.1f} · {_fmt_int(channel['participations_count'])} участий"
            )
    else:
        lines.append("")
        lines.append("У тебя пока нет каналов и статистики")
    return "\n".join(lines)


def build_admin_dashboard_text(
    dashboard: Record,
    recent_violations: list[Record] | None = None,
    problem_channels: list[Record] | None = None,
) -> str:
    lines = [
        "Админ-панель",
        f"Пользователей: {_fmt_int(dashboard['users_count'])}",
        f"Каналов: {_fmt_int(dashboard['channels_count'])}",
        f"Готовых каналов: {_fmt_int(dashboard['ready_channels_count'])}",
        f"Подборок всего: {_fmt_int(dashboard['bundles_count'])}",
        f"Open: {_fmt_int(dashboard['bundles_open_count'])}",
        f"Scheduled: {_fmt_int(dashboard['bundles_scheduled_count'])}",
        f"Published: {_fmt_int(dashboard['bundles_published_count'])}",
        f"Completed: {_fmt_int(dashboard['bundles_completed_count'])}",
        "",
        f"Платежей успешно: {_fmt_int(dashboard['payments_success_count'])}",
        f"Оборот: {_fmt_money(dashboard['turnover_amount'])} ₽",
        f"Комиссия: {_fmt_money(dashboard['commission_amount'])} ₽",
    ]
    if recent_violations:
        lines.append("")
        lines.append("Последние нарушения:")
        for row in recent_violations[:5]:
            name = row["channel_username"] or row["channel_title"] or f"Канал #{row['channel_id']}"
            lines.append(f"{row['created_at']:%d.%m %H:%M} · {name} · {row['violation_type']} · bundle #{row['bundle_id'] or '-'}")
    if problem_channels:
        lines.append("")
        lines.append("Проблемные каналы:")
        for row in problem_channels[:5]:
            name = row["username"] or row["title"] or f"Канал #{row['id']}"
            lines.append(
                f"{name} · rating {float(row['rating'] or 0.0):.1f} · violations {int(row['violations_count'] or 0)}"
            )
    return "\n".join(lines)
