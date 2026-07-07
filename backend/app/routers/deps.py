"""Shared router helpers: auth'd lookups and query-param parsing."""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app.auth import CurrentUser
from app.models.baby import Baby
from app.models.food import Food
from app.repo import family_items, keys


def get_baby_or_404(user: CurrentUser, baby_id: str) -> Baby:
    item = family_items.get(user.family_id, keys.baby_sk(baby_id))
    if item is None:
        raise HTTPException(404, "Baby not found")
    return Baby.model_validate(item)


def get_foods_map(family_id: str) -> dict[str, Food]:
    # Archived foods stay resolvable so editing an old feed never breaks.
    items = family_items.list_by_prefix(family_id, "FOOD#")
    foods = [Food.model_validate(i) for i in items]
    return {f.id: f for f in foods}


def ensure_utc(dt: datetime) -> datetime:
    """Query-param datetimes may arrive naive; treat naive as UTC."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def window_bounds(from_dt: datetime | None, to_dt: datetime | None) -> tuple[str, str]:
    """Default window: everything up to 'now + a day' (client clocks drift)."""
    start = ensure_utc(from_dt) if from_dt else datetime(1970, 1, 1, tzinfo=timezone.utc)
    end = ensure_utc(to_dt) if to_dt else datetime.now(timezone.utc) + timedelta(days=1)
    return keys.log_sk_bound(start), keys.log_sk_bound(end)
