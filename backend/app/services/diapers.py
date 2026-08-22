"""Diaper analytics — the constipation questions: how many poops a day, how
long between them, how long since the last one, and what each looked like.

Read-only over the event log. Gaps are measured against the previous poop
even when it falls before the requested range (we look back 45 days), so the
first poop of the window still reports a real gap.
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from app.models.event import Event
from app.models.summary import DiaperDay, DiaperSeries, PoopEvent
from app.repo import keys, logs
from app.services.tz import day_window, effective_day

LOOKBACK_DAYS = 45


def _is_poop(ev: Event) -> bool:
    return ev.type == "diaper" and ev.diaper_kind in ("poop", "both")


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def diaper_series(
    baby_id: str,
    from_day: date,
    to_day: date,
    tz_name: str,
    day_start: time = time.min,
    now: Optional[datetime] = None,
) -> DiaperSeries:
    now = now or datetime.now(timezone.utc)
    window_from, _ = day_window(from_day, tz_name, day_start)
    _, window_to = day_window(to_day, tz_name, day_start)
    lookback_from = window_from - timedelta(days=LOOKBACK_DAYS)

    items = logs.query_all_logs(
        baby_id,
        keys.log_sk_bound(lookback_from),
        keys.log_sk_bound(max(window_to, now)),
        log_type=keys.LOG_TYPE_EVENT,
    )
    events = [Event.model_validate(i) for i in items]
    diapers = sorted(
        (e for e in events if e.type == "diaper"), key=lambda e: _aware(e.occurred_at)
    )

    n_days = (to_day - from_day).days + 1
    buckets = {
        from_day + timedelta(days=i): DiaperDay(day=from_day + timedelta(days=i))
        for i in range(n_days)
    }
    for ev in diapers:
        b = buckets.get(effective_day(_aware(ev.occurred_at), tz_name, day_start))
        if b is None:
            continue
        b.changes += 1
        if ev.diaper_kind in ("pee", "both"):
            b.pee += 1
        if ev.diaper_kind in ("poop", "both"):
            b.poop += 1

    poops_all: list[PoopEvent] = []
    prev: Optional[datetime] = None
    for ev in diapers:
        if not _is_poop(ev):
            continue
        at = _aware(ev.occurred_at)
        gap = round((at - prev).total_seconds() / 3600, 1) if prev else None
        poops_all.append(
            PoopEvent(
                id=ev.id, occurred_at=at, diaper_kind=ev.diaper_kind or "poop",
                color=ev.diaper_color, consistency=ev.diaper_consistency,
                note=ev.note, gap_hours=gap,
            )
        )
        prev = at

    in_range = [p for p in poops_all if window_from <= p.occurred_at < window_to]
    up_to_now = [p for p in poops_all if p.occurred_at <= now]
    last = up_to_now[-1] if up_to_now else None
    gaps = [p.gap_hours for p in in_range if p.gap_hours is not None]
    longest = max((p for p in in_range if p.gap_hours is not None), key=lambda p: p.gap_hours, default=None)

    return DiaperSeries(
        baby_id=baby_id,
        from_day=from_day,
        to_day=to_day,
        days=[buckets[d] for d in sorted(buckets)],
        poops=in_range,
        last_poop_at=last.occurred_at if last else None,
        hours_since_last_poop=(
            round((now - last.occurred_at).total_seconds() / 3600, 1) if last else None
        ),
        longest_gap_hours=longest.gap_hours if longest else None,
        longest_gap_ended_at=longest.occurred_at if longest else None,
        avg_gap_hours=round(sum(gaps) / len(gaps), 1) if gaps else None,
    )
