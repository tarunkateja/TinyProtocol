"""Feeding recipes: storage, "which recipe was in effect at time T", and the
bottle split rule that turns a logged volume into breast milk + batch ml.

Storage: FAMILY#<fid> / RECIPE#<baby_id>#<utc-iso effective_at>. The SK
encodes the effective time so a prefix query is already chronological;
changing effective_at moves the item (delete + put).
"""

import math
from datetime import datetime, timezone
from typing import Optional

from ulid import ULID

from app.models.feed import LiquidComponent
from app.models.recipe import Recipe, RecipeIn, RecipeUpdate
from app.repo import family_items, keys


def _prefix(baby_id: str) -> str:
    return f"RECIPE#{baby_id}#"


def list_recipes(family_id: str, baby_id: str) -> list[Recipe]:
    items = family_items.list_by_prefix(family_id, _prefix(baby_id))
    recipes = [Recipe.model_validate(i) for i in items]
    recipes.sort(key=lambda r: r.effective_at)
    return recipes


def get_recipe(family_id: str, baby_id: str, recipe_id: str) -> Optional[Recipe]:
    return next((r for r in list_recipes(family_id, baby_id) if r.id == recipe_id), None)


def _store(family_id: str, baby_id: str, recipe: Recipe) -> None:
    data = recipe.model_dump(mode="json", exclude={"prepared_ml", "feeds_per_batch"})
    data["item_type"] = "RECIPE"
    data["baby_id"] = baby_id
    family_items.put(family_id, keys.recipe_sk(baby_id, recipe.effective_at), data)


def create_recipe(family_id: str, baby_id: str, body: RecipeIn) -> Recipe:
    recipe = Recipe(id=str(ULID()), created_at=datetime.now(timezone.utc), **body.model_dump())
    _store(family_id, baby_id, recipe)
    return recipe


def update_recipe(
    family_id: str, baby_id: str, existing: Recipe, body: RecipeUpdate
) -> Recipe:
    merged = RecipeIn.model_validate(
        {**existing.model_dump(exclude={"id", "created_at", "prepared_ml", "feeds_per_batch"}),
         **body.model_dump(exclude_unset=True)}
    )
    updated = Recipe(id=existing.id, created_at=existing.created_at, **merged.model_dump())
    if updated.effective_at != existing.effective_at:
        family_items.delete(family_id, keys.recipe_sk(baby_id, existing.effective_at))
    _store(family_id, baby_id, updated)
    return updated


def delete_recipe(family_id: str, baby_id: str, recipe: Recipe) -> None:
    family_items.delete(family_id, keys.recipe_sk(baby_id, recipe.effective_at))


def recipe_in_effect(recipes: list[Recipe], at: datetime) -> Optional[Recipe]:
    """The newest recipe whose effective_at is at or before `at` (recipes
    must be sorted ascending, as list_recipes returns them)."""
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    current = None
    for r in recipes:
        if r.effective_at <= at:
            current = r
        else:
            break
    return current


def _round1(x: float) -> float:
    """Round half-up to 0.1 ml (Python's round() is half-even: 41.25 -> 41.2,
    but every existing split in the log says 41.3)."""
    return math.floor(x * 10 + 0.5) / 10


def split_bottle(recipe: Recipe, volume_ml: float) -> tuple[float, float]:
    """(breast_milk_ml, batch_ml) for a logged mixed-bottle volume.

    Proportional to the prepared bottle while V <= prepared (a partial feed),
    breast milk capped at the bottle's share once V exceeds it (a top-off
    from the batch logged in the same entry). Sum is exactly volume_ml.
    """
    prepared = recipe.breast_milk_ml + recipe.batch_ml
    if prepared <= 0:
        return 0.0, _round1(volume_ml)
    bm = _round1(min(recipe.breast_milk_ml, volume_ml * recipe.breast_milk_ml / prepared))
    return bm, _round1(volume_ml - bm)


def mixed_components(
    recipe: Recipe,
    volume_ml: float,
    breast_milk_food_id: Optional[str],
    batch_food_id: Optional[str],
) -> list[LiquidComponent]:
    """Feed components for a mixed bottle of `volume_ml` under `recipe`.
    Food ids on the recipe win; the caller passes the mapping's defaults."""
    bm_food = recipe.breast_milk_food_id or breast_milk_food_id
    batch_food = recipe.batch_food_id or batch_food_id
    bm_ml, batch_ml = split_bottle(recipe, volume_ml)
    comps: list[LiquidComponent] = []
    if bm_ml > 0:
        if not bm_food:
            raise ValueError("No breast milk food to split the mixed bottle into")
        comps.append(LiquidComponent(kind="liquid", food_id=bm_food, volume_ml=bm_ml))
    if batch_ml > 0:
        if not batch_food:
            raise ValueError("No formula food to split the mixed bottle into")
        comps.append(LiquidComponent(kind="liquid", food_id=batch_food, volume_ml=batch_ml))
    return comps


def describe(recipe: Recipe) -> str:
    """One line for UI/assistant: '55 + 30 = 85 ml/feed · 30 g Anamix + 20 g Pro-Phree → 280 ml'."""
    bottle = f"{recipe.breast_milk_ml:g} bm + {recipe.batch_ml:g} batch = {recipe.prepared_ml:g} ml/feed"
    if recipe.powders:
        powders = " + ".join(f"{p.grams:g} g {p.name}" for p in recipe.powders)
        if recipe.batch_final_volume_ml:
            powders += f" → {recipe.batch_final_volume_ml:g} ml"
        return f"{bottle} · {powders}"
    return bottle
