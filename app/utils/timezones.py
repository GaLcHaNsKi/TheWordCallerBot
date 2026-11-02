from __future__ import annotations

from datetime import datetime, time, timedelta, timezone, tzinfo
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

OFFSET = re.compile(r"^(?:UTC)?([+-]?)(\d{1,2})(?::(\d{2}))?$", re.I)


def parse_timezone(value: str) -> tuple[str, str, tzinfo]:
    raw = value.strip()
    match = OFFSET.fullmatch(raw)
    if match:
        sign, hours_raw, minutes_raw = match.groups()
        hours, minutes = int(hours_raw), int(minutes_raw or 0)
        if minutes >= 60 or hours > 14 or (hours == 14 and minutes):
            raise ValueError("Допустимо смещение от UTC−12:00 до UTC+14:00")
        delta = timedelta(hours=hours, minutes=minutes)
        if sign == "-":
            delta = -delta
        if delta < timedelta(hours=-12) or delta > timedelta(hours=14):
            raise ValueError("Допустимо смещение от UTC−12:00 до UTC+14:00")
        total = int(delta.total_seconds() // 60)
        prefix = "+" if total >= 0 else "-"
        absolute = abs(total)
        rendered = f"{prefix}{absolute // 60:02d}:{absolute % 60:02d}"
        return "FIXED", rendered, timezone(delta)
    try:
        return "IANA", raw, ZoneInfo(raw)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Неизвестный часовой пояс") from exc


def timezone_from_db(kind: str, value: str) -> tzinfo:
    if kind == "IANA":
        return ZoneInfo(value)
    return parse_timezone(value)[2]


def as_time(value: time | timedelta | str) -> time:
    """Normalise MySQL TIME (PyMySQL returns it as timedelta) to datetime.time."""
    if isinstance(value, time):
        return value
    if isinstance(value, str):
        return time.fromisoformat(value)
    seconds = int(value.total_seconds()) % (24 * 60 * 60)
    return time(seconds // 3600, (seconds % 3600) // 60, seconds % 60)


def due_at(now: datetime, local_time: time | timedelta | str, tz: tzinfo, weekday: int | None = None) -> datetime:
    """Return the next UTC occurrence of local time, optionally a weekday (Mon=0)."""
    local_time = as_time(local_time)
    local_now = now.astimezone(tz)
    days = 0 if weekday is None else (weekday - local_now.weekday()) % 7
    candidate = local_now.replace(hour=local_time.hour, minute=local_time.minute, second=0, microsecond=0)
    candidate += timedelta(days=days)
    if candidate <= local_now:
        candidate += timedelta(days=7 if weekday is not None else 1)
    return candidate.astimezone(timezone.utc)
