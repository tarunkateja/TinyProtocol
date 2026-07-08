"""Local-day <-> UTC window conversion. Timestamps are stored UTC; 'a day' is
defined by the family's timezone (DST-correct: a day can be 23 or 25 hours)."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def day_window(
    day: date, tz_name: str, day_start: time = time.min
) -> tuple[datetime, datetime]:
    """UTC [start, end) of the given local day. A family can define its day to
    start at e.g. 08:00, so "July 7" runs 7th 8am -> 8th 8am local."""
    tz = ZoneInfo(tz_name)
    start = datetime.combine(day, day_start, tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), day_start, tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def to_local(dt: datetime, tz_name: str) -> datetime:
    return dt.astimezone(ZoneInfo(tz_name))


def since_local(wall_time: time, tz_name: str, now: datetime) -> datetime:
    """UTC instant of the most recent occurrence of a local wall-clock time
    (today if already passed, else yesterday)."""
    tz = ZoneInfo(tz_name)
    local_now = now.astimezone(tz)
    candidate = datetime.combine(local_now.date(), wall_time, tzinfo=tz)
    if candidate > local_now:
        candidate = datetime.combine(
            local_now.date() - timedelta(days=1), wall_time, tzinfo=tz
        )
    return candidate.astimezone(timezone.utc)
