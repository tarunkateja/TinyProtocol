from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from ulid import ULID

from app.auth import CurrentUser, get_current_user
from app.models.food import (
    Food,
    FoodIn,
    FoodUpdate,
    MedPreset,
    MedPresetIn,
    MedPresetUpdate,
)
from app.repo import family_items, keys

router = APIRouter(tags=["foods"])


# --------------------------------------------------------------------------- #
# Foods
# --------------------------------------------------------------------------- #
@router.get("/foods", response_model=list[Food])
def list_foods(
    include_archived: bool = False, user: CurrentUser = Depends(get_current_user)
):
    items = family_items.list_by_prefix(user.family_id, "FOOD#")
    foods = [Food.model_validate(i) for i in items]
    if not include_archived:
        foods = [f for f in foods if not f.archived]
    return sorted(foods, key=lambda f: (f.category, f.name))


@router.post("/foods", response_model=Food, status_code=201)
def create_food(body: FoodIn, user: CurrentUser = Depends(get_current_user)):
    food = Food(
        id=str(ULID()), created_at=datetime.now(timezone.utc), **body.model_dump()
    )
    family_items.put(user.family_id, keys.food_sk(food.id), food.model_dump(mode="json"))
    return food


@router.patch("/foods/{food_id}", response_model=Food)
def update_food(
    food_id: str, body: FoodUpdate, user: CurrentUser = Depends(get_current_user)
):
    item = family_items.get(user.family_id, keys.food_sk(food_id))
    if item is None:
        raise HTTPException(404, "Food not found")
    food = Food.model_validate(item)
    updated = food.model_copy(update=body.model_dump(exclude_unset=True))
    family_items.put(
        user.family_id, keys.food_sk(food_id), updated.model_dump(mode="json")
    )
    return updated


@router.delete("/foods/{food_id}", response_model=Food)
def archive_food(food_id: str, user: CurrentUser = Depends(get_current_user)):
    """Soft delete: old feeds carry nutrition snapshots, so archiving is safe."""
    return update_food(food_id, FoodUpdate(archived=True), user)


# --------------------------------------------------------------------------- #
# Med presets
# --------------------------------------------------------------------------- #
@router.get("/med-presets", response_model=list[MedPreset])
def list_med_presets(user: CurrentUser = Depends(get_current_user)):
    items = family_items.list_by_prefix(user.family_id, "MEDPRESET#")
    return sorted(
        (MedPreset.model_validate(i) for i in items), key=lambda p: p.name
    )


@router.post("/med-presets", response_model=MedPreset, status_code=201)
def create_med_preset(body: MedPresetIn, user: CurrentUser = Depends(get_current_user)):
    preset = MedPreset(
        id=str(ULID()), created_at=datetime.now(timezone.utc), **body.model_dump()
    )
    family_items.put(
        user.family_id, keys.med_preset_sk(preset.id), preset.model_dump(mode="json")
    )
    return preset


@router.patch("/med-presets/{preset_id}", response_model=MedPreset)
def update_med_preset(
    preset_id: str, body: MedPresetUpdate, user: CurrentUser = Depends(get_current_user)
):
    item = family_items.get(user.family_id, keys.med_preset_sk(preset_id))
    if item is None:
        raise HTTPException(404, "Med preset not found")
    preset = MedPreset.model_validate(item)
    updated = preset.model_copy(update=body.model_dump(exclude_unset=True))
    family_items.put(
        user.family_id, keys.med_preset_sk(preset_id), updated.model_dump(mode="json")
    )
    return updated
