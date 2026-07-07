from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import CurrentUser, get_current_user
from app.models.event import Event
from app.models.feed import Feed
from app.models.summary import Summary
from app.repo import families, keys, logs
from app.routers.deps import get_baby_or_404
from app.services.summary import build_summary
from app.services.tz import day_window

router = APIRouter(tags=["summary"])


def _family_tz(family_id: str) -> str:
    fam = families.get_family(family_id)
    if fam is None:
        raise HTTPException(404, "Family not found")
    return fam["timezone"]


def _summarize(user, baby_id, window_from, window_to, tz_name, day=None) -> Summary:
    baby = get_baby_or_404(user, baby_id)
    items = logs.query_all_logs(
        baby_id, keys.log_sk_bound(window_from), keys.log_sk_bound(window_to)
    )
    feeds = [
        Feed.model_validate(i) for i in items if i.get("item_type") == keys.LOG_TYPE_FEED
    ]
    events = [
        Event.model_validate(i)
        for i in items
        if i.get("item_type") == keys.LOG_TYPE_EVENT
    ]
    return build_summary(baby, feeds, events, window_from, window_to, tz_name, day=day)


@router.get("/babies/{baby_id}/summary", response_model=Summary)
def rolling_summary(
    baby_id: str,
    hours: int = Query(24, ge=1, le=24 * 14),
    user: CurrentUser = Depends(get_current_user),
):
    """The doctor summary: a rolling window ending now (default last 24h)."""
    tz_name = _family_tz(user.family_id)
    now = datetime.now(timezone.utc)
    return _summarize(user, baby_id, now - timedelta(hours=hours), now, tz_name)


@router.get("/babies/{baby_id}/days/{day}", response_model=Summary)
def day_summary(
    baby_id: str, day: date, user: CurrentUser = Depends(get_current_user)
):
    """Totals vs targets for one local calendar day (family timezone)."""
    tz_name = _family_tz(user.family_id)
    window_from, window_to = day_window(day, tz_name)
    return _summarize(user, baby_id, window_from, window_to, tz_name, day=day)
