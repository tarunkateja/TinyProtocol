"""Feeding recipes with history, and the re-split tool that re-applies the
recipe in effect to already-imported Huckleberry mixed bottles."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import CurrentUser, get_current_user
from app.models.feed import Feed
from app.models.recipe import Recipe, RecipeIn, RecipeUpdate, ResplitChange, ResplitResult
from app.repo import keys, logs
from app.routers.deps import ensure_utc, get_baby_or_404, get_foods_map
from app.services import huckleberry as hb
from app.services import recipes as svc
from app.services.nutrition import NutritionError, compute_components

router = APIRouter(prefix="/babies/{baby_id}/recipes", tags=["recipes"])

MAX_RESPLIT_DAYS = 62


def _check_foods(user: CurrentUser, body) -> None:
    foods = get_foods_map(user.family_id)
    for fid in (body.breast_milk_food_id, body.batch_food_id, body.topoff_food_id):
        if fid and (fid not in foods or foods[fid].unit_basis != "per_100ml"):
            raise HTTPException(422, f"{fid} is not a liquid food")
    for p in (body.powders or []) + (body.topoff_powders or []):
        if p.food_id and p.food_id not in foods:
            raise HTTPException(422, f"{p.food_id} is not a food")


@router.get("", response_model=list[Recipe])
def list_recipes(baby_id: str, user: CurrentUser = Depends(get_current_user)):
    baby = get_baby_or_404(user, baby_id)
    return svc.list_recipes(user.family_id, baby.id)


@router.get("/current", response_model=Optional[Recipe])
def current_recipe(
    baby_id: str,
    at: Optional[datetime] = Query(None),
    user: CurrentUser = Depends(get_current_user),
):
    """The recipe in effect at `at` (default now); null when none applies."""
    baby = get_baby_or_404(user, baby_id)
    when = ensure_utc(at) if at else datetime.now(timezone.utc)
    return svc.recipe_in_effect(svc.list_recipes(user.family_id, baby.id), when)


@router.post("", response_model=Recipe, status_code=201)
def create_recipe(
    baby_id: str, body: RecipeIn, user: CurrentUser = Depends(get_current_user)
):
    baby = get_baby_or_404(user, baby_id)
    _check_foods(user, body)
    if any(r.effective_at == body.effective_at for r in svc.list_recipes(user.family_id, baby.id)):
        raise HTTPException(409, "A recipe already starts at that exact time")
    return svc.create_recipe(user.family_id, baby.id, body)


def _get_or_404(user: CurrentUser, baby_id: str, recipe_id: str) -> Recipe:
    recipe = svc.get_recipe(user.family_id, baby_id, recipe_id)
    if recipe is None:
        raise HTTPException(404, "Recipe not found")
    return recipe


@router.patch("/{recipe_id}", response_model=Recipe)
def update_recipe(
    baby_id: str,
    recipe_id: str,
    body: RecipeUpdate,
    user: CurrentUser = Depends(get_current_user),
):
    baby = get_baby_or_404(user, baby_id)
    existing = _get_or_404(user, baby.id, recipe_id)
    _check_foods(user, body)
    try:
        return svc.update_recipe(user.family_id, baby.id, existing, body)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.delete("/{recipe_id}", status_code=204)
def delete_recipe(
    baby_id: str, recipe_id: str, user: CurrentUser = Depends(get_current_user)
):
    baby = get_baby_or_404(user, baby_id)
    svc.delete_recipe(user.family_id, baby.id, _get_or_404(user, baby.id, recipe_id))


@router.post("/resplit", response_model=ResplitResult)
def resplit(
    baby_id: str,
    from_dt: datetime = Query(..., alias="from"),
    to_dt: datetime = Query(..., alias="to"),
    apply: bool = Query(False),
    user: CurrentUser = Depends(get_current_user),
):
    """Re-apply the recipe in effect to imported Huckleberry bottles of every
    recipe-mapped type in a window: mixed bottles get the breast milk / batch
    split, top-ups get the recipe's top-up food. Totals never change.
    Preview by default; apply=true writes. Feeds the parent edited by hand
    (hb link broken) are never touched."""
    baby = get_baby_or_404(user, baby_id)
    start, end = ensure_utc(from_dt), ensure_utc(to_dt)
    if end <= start or end - start > timedelta(days=MAX_RESPLIT_DAYS):
        raise HTTPException(422, f"Window must be 0–{MAX_RESPLIT_DAYS} days")

    conn = hb.get_connection(user.family_id, baby.id) or {}
    mapping = conn.get("mapping") or {}
    recipe_types = {bt for bt, t in mapping.items() if hb.is_recipe_mapping(t)}
    if not recipe_types:
        raise HTTPException(
            422, "No Huckleberry bottle type is mapped to 'per recipe' yet"
        )
    recipes = svc.list_recipes(user.family_id, baby.id)
    foods = get_foods_map(user.family_id)
    bm_default, batch_default = hb.recipe_food_defaults(mapping, foods)
    imports = {
        i.hb_key: i
        for i in hb.list_imports(user.family_id, baby.id, status="imported")
        if i.mode == "bottle" and i.bottle_type in recipe_types
    }

    result = ResplitResult(applied=apply, changes=[])
    raws = logs.query_all_logs(
        baby.id, keys.log_sk_bound(start), keys.log_sk_bound(end), log_type=keys.LOG_TYPE_FEED
    )
    for raw in raws:
        hb_key = raw.get("hb_key")
        if raw.get("source") != "huckleberry" or not hb_key:
            continue
        imp = imports.get(hb._normalize_hb_key(hb_key)) or imports.get(hb_key)
        if imp is None:
            continue  # not a recipe-mapped bottle (or edited by hand → unlinked)
        feed = Feed.model_validate(raw)
        if not all(c.kind == "liquid" for c in feed.components):
            result.skipped_unlinked += 1
            continue
        recipe = svc.recipe_in_effect(recipes, feed.occurred_at)
        if recipe is None:
            result.skipped_no_recipe += 1
            continue
        total = round(sum(c.volume_ml for c in feed.components), 1)
        try:
            if imp.bottle_type == "Other":
                new_components = svc.mixed_components(recipe, total, bm_default, batch_default)
            else:
                new_components = svc.topoff_components(recipe, total, batch_default)
            comps, totals = compute_components(new_components, foods)
        except (ValueError, NutritionError) as e:
            raise HTTPException(422, str(e))
        before = {c.food_name: c.volume_ml for c in feed.components}
        after = {c["food_name"]: c["volume_ml"] for c in comps}
        if before == after:
            result.unchanged += 1
            continue
        result.changes.append(
            ResplitChange(
                feed_id=feed.id,
                occurred_at=feed.occurred_at,
                total_ml=total,
                recipe_label=recipe.label,
                before=before,
                after=after,
            )
        )
        if apply:
            updated = Feed(
                id=feed.id,
                baby_id=feed.baby_id,
                occurred_at=feed.occurred_at,
                components=comps,
                totals=totals,
                notes=feed.notes,
                created_at=feed.created_at,
            )
            logs.replace_log(raw["PK"], raw["SK"], hb._hb_feed_item(user.family_id, updated, hb_key))
    return result
