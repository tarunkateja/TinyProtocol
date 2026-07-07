"""Local-day <-> UTC window conversion. Timestamps are stored UTC; 'a day' is
defined by the family's timezone (DST-correct: a day can be 23 or 25 hours)."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def day_window(day: date, tz_name: str) -> tuple[datetime, datetime]:
    """UTC [start, end) of the given local calendar day."""
    tz = ZoneInfo(tz_name)
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def to_local(dt: datetime, tz_name: str) -> datetime:
    return dt.astimezone(ZoneInfo(tz_name))
