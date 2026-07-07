from datetime import datetime
from typing import Annotated, Literal, Optional, Union

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.auth import CurrentUser, get_current_user
from app.models.event import Event
from app.models.feed import Feed
from app.repo import keys, logs
from app.routers.deps import get_baby_or_404, window_bounds

router = APIRouter(tags=["timeline"])

TimelineEntry = Annotated[Union[Feed, Event], Field(discriminator="item_type")]


class TimelinePage(BaseModel):
    items: list[TimelineEntry]
    next_cursor: Optional[str] = None


@router.get("/babies/{baby_id}/timeline", response_model=TimelinePage)
def timeline(
    baby_id: str,
    from_dt: Optional[datetime] = Query(None, alias="from"),
    to_dt: Optional[datetime] = Query(None, alias="to"),
    cursor: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    type: Optional[Literal["feed", "event"]] = None,
    user: CurrentUser = Depends(get_current_user),
):
    """Feeds and events interleaved, newest first — the Today screen."""
    get_baby_or_404(user, baby_id)
    lo, hi = window_bounds(from_dt, to_dt)
    log_type = {"feed": keys.LOG_TYPE_FEED, "event": keys.LOG_TYPE_EVENT}.get(type)
    items, next_cursor = logs.query_logs(
        baby_id, lo, hi, limit=limit, cursor=cursor, log_type=log_type
    )
    parsed = [
        Feed.model_validate(i)
        if i.get("item_type") == keys.LOG_TYPE_FEED
        else Event.model_validate(i)
        for i in items
    ]
    return TimelinePage(items=parsed, next_cursor=next_cursor)
