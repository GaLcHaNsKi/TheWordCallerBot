from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from datetime import timedelta

from app.utils.timezones import as_time, due_at, parse_timezone


def test_fixed_timezone() -> None:
    kind, value, _ = parse_timezone("UTC+5:30")
    assert (kind, value) == ("FIXED", "+05:30")


def test_due_is_next_calendar_occurrence() -> None:
    now = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
    due = due_at(now, time(8, 0), ZoneInfo("UTC"))
    assert due == datetime(2026, 1, 2, 8, 0, tzinfo=timezone.utc)


def test_mysql_time_timedelta_is_normalized() -> None:
    assert as_time(timedelta(hours=8, minutes=30)) == time(8, 30)
