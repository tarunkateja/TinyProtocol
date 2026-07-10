from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import CurrentUser, get_current_user
from app.models.summary import Summary
from app.repo import families
from app.routers.deps import get_baby_or_404
from app.services import target_history
from app.services.summary import summarize_window
from app.services.tz import day_window, since_local

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
    user: CurrentUser = Depends(get_current_user),
):
    """The doctor summary: a rolling window ending now — either the last N
    hours (default 24) or since a local wall-clock time like 07:00."""
    if hours is not None and since_local_time is not None:
        raise HTTPException(422, "Pass either hours or since_local_time, not both")
    baby = get_baby_or_404(user, baby_id)
    tz_name = _family_tz(user.family_id)
    now = datetime.now(timezone.utc)

    if since_local_time is not None:
        window_from = since_local(since_local_time, tz_name, now)
        label = f"since {since_local_time.strftime('%-I:%M %p')}"
    else:
        window_from = now - timedelta(hours=hours or 24)
        label = ""
    return summarize_window(baby, window_from, now, tz_name, window_label=label)


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
