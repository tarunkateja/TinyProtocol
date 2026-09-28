from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import CurrentUser, get_current_user
from app.models.event import Event
from app.models.feed import Feed
from app.models.dietitian import DietitianReport
from app.models.summary import (
    DailyIntakeDay,
    DailyIntakeSeries,
    Summary,
    WeightPoint,
    WeightSeries,
    DiaperSeries,
)
from app.repo import families, keys, logs
from app.routers.deps import get_baby_or_404
from app.services import target_history
from app.services.dietitian import dietitian_report
from app.services.summary import summarize_window
from app.services.tz import day_window, effective_day, since_local

router = APIRouter(tags=["summary"])


def _family(family_id: str) -> dict:
    fam = families.get_family(family_id)
    if fam is None:
        raise HTTPException(404, "Family not found")
    return fam


def _family_tz(family_id: str) -> str:
    return _family(family_id)["timezone"]


@router.get("/babies/{baby_id}/summary", response_model=Summary)
def rolling_summary(
    baby_id: str,
    hours: Optional[int] = Query(None, ge=1, le=24 * 14),
    since_local_time: Optional[time] = Query(
        None, description="Window since this local wall-clock time, e.g. 07:00"
    ),
    from_local: Optional[datetime] = Query(
        None, description="Window start, local naive datetime e.g. 2026-07-09T08:00"
    ),
    to_local: Optional[datetime] = Query(
        None, description="Window end, local naive datetime (defaults to now)"
    ),
    user: CurrentUser = Depends(get_current_user),
):
    """The doctor summary: a rolling window ending now (last N hours, or since
    a local wall-clock time), or an explicit local from/to range."""
    modes = sum(x is not None for x in (hours, since_local_time, from_local))
    if modes > 1:
        raise HTTPException(422, "Pass only one of hours, since_local_time, from_local")
    if to_local is not None and from_local is None:
        raise HTTPException(422, "to_local requires from_local")
    baby = get_baby_or_404(user, baby_id)
    tz_name = _family_tz(user.family_id)
    now = datetime.now(timezone.utc)

    if from_local is not None:
        tz = ZoneInfo(tz_name)
        window_from = from_local.replace(tzinfo=tz).astimezone(timezone.utc)
        window_to = to_local.replace(tzinfo=tz).astimezone(timezone.utc) if to_local else now
        if window_from >= window_to:
            raise HTTPException(422, "from_local must be before to_local")
        if window_to - window_from > timedelta(days=14):
            raise HTTPException(422, "Window is limited to 14 days")
        fmt = "%b %-d, %-I:%M %p"
        label = (
            f"{from_local.strftime(fmt)} → "
            f"{to_local.strftime(fmt) if to_local else 'now'}"
        )
        return summarize_window(baby, window_from, window_to, tz_name, window_label=label)

    if since_local_time is not None:
        window_from = since_local(since_local_time, tz_name, now)
        label = f"since {since_local_time.strftime('%-I:%M %p')}"
    else:
        window_from = now - timedelta(hours=hours or 24)
        label = ""
    return summarize_window(baby, window_from, now, tz_name, window_label=label)


@router.get("/babies/{baby_id}/reports/dietitian", response_model=DietitianReport)
def dietitian_update(
    baby_id: str,
    days: int = Query(3, ge=1, le=14, description="Full family days before today"),
    as_of_local: Optional[datetime] = Query(
        None, description="Build it as of this local time instead of now (reproduce a past message)"
    ),
    notes: bool = Query(True, description="Include the parent's feed notes in parentheses"),
    user: CurrentUser = Depends(get_current_user),
):
    """The ready-to-send feeding-log message for the metabolic dietitian:
    the last N full family days (day_start → day_start), one bullet per
    feed, one total per day, plus today so far. Warnings list what to check
    in the log before sending; they are never part of the text."""
    baby = get_baby_or_404(user, baby_id)
    fam = _family(user.family_id)
    tz_name = fam["timezone"]
    day_start = time.fromisoformat(fam.get("day_start") or "00:00")
    now = None
    if as_of_local is not None:
        now = as_of_local.replace(tzinfo=ZoneInfo(tz_name)).astimezone(timezone.utc)
    return dietitian_report(
        user.family_id, baby, tz_name, day_start, days, now=now, include_notes=notes
    )


@router.get("/babies/{baby_id}/analytics/daily", response_model=DailyIntakeSeries)
def daily_intake(
    baby_id: str,
    from_day: date = Query(alias="from"),
    to_day: date = Query(alias="to"),
    user: CurrentUser = Depends(get_current_user),
):
    """Per-day intake by source (ml) for the trends chart. Read-only: feeds
    are bucketed by the local day they already belong to; nothing is written."""
    if from_day > to_day:
        raise HTTPException(422, "from must be on or before to")
    if (to_day - from_day).days > 92:
        raise HTTPException(422, "Range is limited to 92 days")
    baby = get_baby_or_404(user, baby_id)
    fam = _family(user.family_id)
    tz_name = fam["timezone"]
    day_start = time.fromisoformat(fam.get("day_start") or "00:00")

    window_from, _ = day_window(from_day, tz_name, day_start)
    _, window_to = day_window(to_day, tz_name, day_start)
    items = logs.query_all_logs(
        baby.id,
        keys.log_sk_bound(window_from),
        keys.log_sk_bound(window_to),
        log_type=keys.LOG_TYPE_FEED,
    )

    n_days = (to_day - from_day).days + 1
    buckets = {
        from_day + timedelta(days=i): DailyIntakeDay(day=from_day + timedelta(days=i))
        for i in range(n_days)
    }
    for item in items:
        feed = Feed.model_validate(item)
        occurred = feed.occurred_at
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=timezone.utc)
        b = buckets.get(effective_day(occurred, tz_name, day_start))
        if b is None:
            continue
        t = feed.totals
        b.feed_count += 1
        b.total_ml = round(b.total_ml + t.total_ml, 1)
        b.breast_milk_ml = round(b.breast_milk_ml + t.breast_milk_ml, 1)
        b.formula_ml = round(b.formula_ml + t.formula_ml, 1)
        b.metabolic_formula_ml = round(
            b.metabolic_formula_ml + t.metabolic_formula_ml, 1
        )
        b.other_ml = round(b.other_ml + t.other_ml, 1)

    return DailyIntakeSeries(
        baby_id=baby.id,
        from_day=from_day,
        to_day=to_day,
        days=[buckets[d] for d in sorted(buckets)],
    )


@router.get("/babies/{baby_id}/analytics/diapers", response_model=DiaperSeries)
def diaper_history(
    baby_id: str,
    from_day: date = Query(alias="from"),
    to_day: date = Query(alias="to"),
    user: CurrentUser = Depends(get_current_user),
):
    """Per-day diaper counts + every poop with the gap since the previous
    one (constipation view). Read-only."""
    if from_day > to_day:
        raise HTTPException(422, "from must be on or before to")
    if (to_day - from_day).days > 92:
        raise HTTPException(422, "Range is limited to 92 days")
    baby = get_baby_or_404(user, baby_id)
    fam = _family(user.family_id)
    from app.services.diapers import diaper_series

    return diaper_series(
        baby.id, from_day, to_day, fam["timezone"],
        time.fromisoformat(fam.get("day_start") or "00:00"),
    )


@router.get("/babies/{baby_id}/analytics/weights", response_model=WeightSeries)
def weight_history(baby_id: str, user: CurrentUser = Depends(get_current_user)):
    """Every weight check-in ever logged, oldest first, plus birth context.
    Read-only: nothing is written or altered."""
    baby = get_baby_or_404(user, baby_id)
    now = datetime.now(timezone.utc)
    items = logs.query_all_logs(
        baby.id,
        keys.log_sk_bound(datetime(2020, 1, 1, tzinfo=timezone.utc)),
        keys.log_sk_bound(now + timedelta(days=1)),
        log_type=keys.LOG_TYPE_EVENT,
    )
    weights = [
        WeightPoint(id=e.id, occurred_at=e.occurred_at, weight_g=e.weight_g)
        for e in (Event.model_validate(i) for i in items)
        if e.type == "weight" and e.weight_g
    ]
    weights.sort(key=lambda w: w.occurred_at.isoformat())
    return WeightSeries(
        baby_id=baby.id,
        date_of_birth=baby.date_of_birth,
        birth_weight_g=baby.birth_weight_g,
        weights=weights,
    )


@router.get("/babies/{baby_id}/days/{day}", response_model=Summary)
def day_summary(
    baby_id: str, day: date, user: CurrentUser = Depends(get_current_user)
):
    """Totals vs targets for one local day (family timezone + day-start)."""
    baby = get_baby_or_404(user, baby_id)
    fam = _family(user.family_id)
    tz_name = fam["timezone"]
    day_start = time.fromisoformat(fam.get("day_start") or "00:00")
    window_from, window_to = day_window(day, tz_name, day_start)
    # Past days are judged against the targets in effect on THAT day.
    baby = baby.model_copy(
        update={"targets": target_history.targets_for_day(user.family_id, baby, day)}
    )
    return summarize_window(baby, window_from, window_to, tz_name, day=day)
