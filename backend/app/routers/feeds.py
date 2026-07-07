from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from ulid import ULID

from app.auth import CurrentUser, get_current_user
from app.models.feed import Feed, FeedIn, FeedUpdate
from app.repo import keys, logs
from app.routers.deps import get_baby_or_404, get_foods_map, window_bounds
from app.services.nutrition import NutritionError, compute_components

router = APIRouter(tags=["feeds"])


class FeedPage(BaseModel):
    items: list[Feed]
    next_cursor: Optional[str] = None


def feed_item(family_id: str, feed: Feed) -> dict:
    return {
        "PK": keys.baby_pk(feed.baby_id),
        "SK": keys.log_sk(feed.occurred_at, keys.LOG_TYPE_FEED, feed.id),
        "GSI1PK": keys.gsi1_log_pk(feed.id),
        "GSI1SK": keys.GSI1_STATIC_SK,
        "family_id": family_id,
        **feed.model_dump(mode="json"),
    }


def _compute_or_422(components, foods):
    try:
        return compute_components(components, foods)
    except NutritionError as e:
        raise HTTPException(422, str(e))


@router.post("/babies/{baby_id}/feeds", response_model=Feed, status_code=201)
def create_feed(
    baby_id: str, body: FeedIn, user: CurrentUser = Depends(get_current_user)
):
    get_baby_or_404(user, baby_id)
    comps, totals = _compute_or_422(body.components, get_foods_map(user.family_id))
    feed = Feed(
        id=str(ULID()),
        baby_id=baby_id,
        occurred_at=body.occurred_at,
        components=comps,
        totals=totals,
        notes=body.notes,
        created_at=datetime.now(timezone.utc),
    )
    logs.put_log(feed_item(user.family_id, feed))
    return feed


@router.get("/babies/{baby_id}/feeds", response_model=FeedPage)
def list_feeds(
    baby_id: str,
    from_dt: Optional[datetime] = Query(None, alias="from"),
    to_dt: Optional[datetime] = Query(None, alias="to"),
    cursor: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    user: CurrentUser = Depends(get_current_user),
):
    get_baby_or_404(user, baby_id)
    lo, hi = window_bounds(from_dt, to_dt)
    items, next_cursor = logs.query_logs(
        baby_id, lo, hi, limit=limit, cursor=cursor, log_type=keys.LOG_TYPE_FEED
    )
    return FeedPage(
        items=[Feed.model_validate(i) for i in items], next_cursor=next_cursor
    )


def _find_feed(feed_id: str, user: CurrentUser) -> tuple[dict, Feed]:
    item = logs.find_log(feed_id, user.family_id)
    if item is None or item.get("item_type") != keys.LOG_TYPE_FEED:
        raise HTTPException(404, "Feed not found")
    return item, Feed.model_validate(item)


@router.get("/feeds/{feed_id}", response_model=Feed)
def get_feed(feed_id: str, user: CurrentUser = Depends(get_current_user)):
    return _find_feed(feed_id, user)[1]


@router.patch("/feeds/{feed_id}", response_model=Feed)
def update_feed(
    feed_id: str, body: FeedUpdate, user: CurrentUser = Depends(get_current_user)
):
    raw, feed = _find_feed(feed_id, user)
    updates = body.model_dump(exclude_unset=True)

    if body.components is not None:
        comps, totals = _compute_or_422(
            body.components, get_foods_map(user.family_id)
        )
    else:
        comps, totals = feed.components, feed.totals

    updated = Feed(
        id=feed.id,
        baby_id=feed.baby_id,
        occurred_at=body.occurred_at or feed.occurred_at,
        components=comps,
        totals=totals,
        notes=updates.get("notes", feed.notes),
        created_at=feed.created_at,
    )
    # Time is part of the SK — replace_log moves the item transactionally if needed.
    logs.replace_log(raw["PK"], raw["SK"], feed_item(user.family_id, updated))
    return updated


@router.delete("/feeds/{feed_id}", status_code=204)
def delete_feed(feed_id: str, user: CurrentUser = Depends(get_current_user)):
    raw, _ = _find_feed(feed_id, user)
    logs.delete_log(raw["PK"], raw["SK"])
