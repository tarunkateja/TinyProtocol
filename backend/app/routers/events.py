from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from ulid import ULID

from app.auth import CurrentUser, get_current_user
from app.models.event import Event, EventIn, EventUpdate
from app.repo import keys, logs
from app.routers.deps import get_baby_or_404, window_bounds

router = APIRouter(tags=["events"])


class EventPage(BaseModel):
    items: list[Event]
    next_cursor: Optional[str] = None


def event_item(family_id: str, event: Event) -> dict:
    return {
        "PK": keys.baby_pk(event.baby_id),
        "SK": keys.log_sk(event.occurred_at, keys.LOG_TYPE_EVENT, event.id),
        "GSI1PK": keys.gsi1_log_pk(event.id),
        "GSI1SK": keys.GSI1_STATIC_SK,
        "family_id": family_id,
        **event.model_dump(mode="json"),
    }


@router.post("/babies/{baby_id}/events", response_model=Event, status_code=201)
def create_event(
    baby_id: str, body: EventIn, user: CurrentUser = Depends(get_current_user)
):
    get_baby_or_404(user, baby_id)
    event = Event(
        id=str(ULID()),
        baby_id=baby_id,
        created_at=datetime.now(timezone.utc),
        **body.model_dump(),
    )
    logs.put_log(event_item(user.family_id, event))
    return event


@router.get("/babies/{baby_id}/events", response_model=EventPage)
def list_events(
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
        baby_id, lo, hi, limit=limit, cursor=cursor, log_type=keys.LOG_TYPE_EVENT
    )
    return EventPage(
        items=[Event.model_validate(i) for i in items], next_cursor=next_cursor
    )


def _find_event(event_id: str, user: CurrentUser) -> tuple[dict, Event]:
    item = logs.find_log(event_id, user.family_id)
    if item is None or item.get("item_type") != keys.LOG_TYPE_EVENT:
        raise HTTPException(404, "Event not found")
    return item, Event.model_validate(item)


@router.get("/events/{event_id}", response_model=Event)
def get_event(event_id: str, user: CurrentUser = Depends(get_current_user)):
    return _find_event(event_id, user)[1]


@router.patch("/events/{event_id}", response_model=Event)
def update_event(
    event_id: str, body: EventUpdate, user: CurrentUser = Depends(get_current_user)
):
    raw, event = _find_event(event_id, user)
    # Re-validate the merged event so per-type field rules hold on PATCH too.
    updated = Event.model_validate(
        {**event.model_dump(), **body.model_dump(exclude_unset=True)}
    )
    logs.replace_log(raw["PK"], raw["SK"], event_item(user.family_id, updated))
    return updated


@router.delete("/events/{event_id}", status_code=204)
def delete_event(event_id: str, user: CurrentUser = Depends(get_current_user)):
    raw, _ = _find_event(event_id, user)
    logs.delete_log(raw["PK"], raw["SK"])
