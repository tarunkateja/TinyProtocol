from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from ulid import ULID

from app.auth import CurrentUser, get_current_user
from app.models.preset import FeedPreset, FeedPresetIn
from app.repo import family_items, keys
from app.routers.deps import get_foods_map

router = APIRouter(tags=["feed-presets"])


@router.get("/feed-presets", response_model=list[FeedPreset])
def list_presets(user: CurrentUser = Depends(get_current_user)):
    items = family_items.list_by_prefix(user.family_id, "FEEDPRESET#")
    return sorted(
        (FeedPreset.model_validate(i) for i in items), key=lambda p: p.created_at
    )


@router.post("/feed-presets", response_model=FeedPreset, status_code=201)
def create_preset(body: FeedPresetIn, user: CurrentUser = Depends(get_current_user)):
    foods = get_foods_map(user.family_id)
    for comp in body.components:
        if comp.food_id not in foods:
            raise HTTPException(422, f"Unknown food: {comp.food_id}")
    preset = FeedPreset(
        id=str(ULID()), created_at=datetime.now(timezone.utc), **body.model_dump()
    )
    family_items.put(
        user.family_id, keys.feed_preset_sk(preset.id), preset.model_dump(mode="json")
    )
    return preset


@router.delete("/feed-presets/{preset_id}", status_code=204)
def delete_preset(preset_id: str, user: CurrentUser = Depends(get_current_user)):
    if family_items.get(user.family_id, keys.feed_preset_sk(preset_id)) is None:
        raise HTTPException(404, "Preset not found")
    family_items.delete(user.family_id, keys.feed_preset_sk(preset_id))
