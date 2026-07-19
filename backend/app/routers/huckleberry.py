"""Huckleberry sync: connect, review-first imports, manual sync.

Connect takes the Huckleberry email/password, trades them for a Firebase
refresh token and stores only the token. Imports land as pending items the
parent confirms (or auto-log for mapped bottle feeds when auto_import is on).
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth import CurrentUser, get_current_user
from app.models.feed import Feed
from app.models.huckleberry import (
    HB_BOTTLE_TYPES,
    HbChild,
    HbChildSelection,
    HbConfirmIn,
    HbConnectIn,
    HbConnectionUpdate,
    HbImport,
    HbMappingEntry,
    HbSplitPart,
    HbStatus,
    HbSyncResult,
)
from app.repo import families, family_items, keys
from app.routers.deps import get_baby_or_404, get_foods_map
from app.services import huckleberry as hb
from app.services.nutrition import NutritionError

router = APIRouter(tags=["huckleberry"])


def _now_iso() -> str:
    return keys.iso_z(datetime.now(timezone.utc))


def _status(user: CurrentUser, baby_id: str) -> HbStatus:
    conn = hb.get_connection(user.family_id, baby_id)
    if conn is None:
        return HbStatus(connected=False)
    foods = get_foods_map(user.family_id)

    def name_of(food_id: str) -> str:
        return foods[food_id].name if food_id in foods else food_id

    mapping: dict[str, HbMappingEntry] = {}
    for bottle_type, target in (conn.get("mapping") or {}).items():
        if isinstance(target, list):
            mapping[bottle_type] = HbMappingEntry(
                split=[
                    HbSplitPart(
                        food_id=p["food_id"],
                        food_name=name_of(p["food_id"]),
                        parts=float(p["parts"]),
                    )
                    for p in target
                ]
            )
        else:
            mapping[bottle_type] = HbMappingEntry(food_id=target, food_name=name_of(target))
    pending = hb.list_imports(user.family_id, baby_id, status="pending")
    deleted = hb.list_imports(user.family_id, baby_id, status="deleted_upstream")
    return HbStatus(
        connected=True,
        hb_email=conn.get("hb_email"),
        child_name=conn.get("child_name"),
        auto_import=bool(conn.get("auto_import")),
        mapping=mapping,
        latch_rate_ml_per_10min=conn.get("latch_rate_ml_per_10min"),
        last_synced_at=conn.get("last_synced_at"),
        status=conn.get("status"),
        last_error=conn.get("last_error") or None,
        pending_count=len(pending) + len(deleted),
    )


@router.post("/babies/{baby_id}/huckleberry/connect", response_model=None)
async def connect(
    baby_id: str, body: HbConnectIn, user: CurrentUser = Depends(get_current_user)
):
    get_baby_or_404(user, baby_id)
    family = families.get_family(user.family_id)
    tz_name = (family or {}).get("timezone", "UTC")

    try:
        auth = await hb.authenticate_and_get_children(body.email, body.password, tz_name)
    except hb.HuckleberryAuthError as e:
        raise HTTPException(401, str(e))
    except hb.HuckleberryError as e:
        raise HTTPException(502, str(e))

    children = auth["children"]
    if not children:
        raise HTTPException(422, "That Huckleberry account has no children on it")

    if body.child_uid:
        child = next((c for c in children if c["uid"] == body.child_uid), None)
        if child is None:
            raise HTTPException(422, "child_uid does not belong to that Huckleberry account")
    elif len(children) == 1:
        child = children[0]
    else:
        return HbChildSelection(children=[HbChild(**c) for c in children])

    foods = get_foods_map(user.family_id)
    family_items.put(
        user.family_id,
        keys.huckleberry_sk(baby_id),
        {
            "item_type": "HBSYNC",
            "baby_id": baby_id,
            "hb_email": body.email,
            "refresh_token": auth["refresh_token"],
            "hb_user_uid": auth["user_uid"],
            "child_uid": child["uid"],
            "child_name": child["name"],
            "mapping": hb.default_mapping(foods),
            "auto_import": False,
            "status": "ok",
            "created_at": _now_iso(),
        },
    )

    # First sync right away so the review screen has something to show.
    try:
        await hb.sync_baby(user.family_id, baby_id)
    except hb.HuckleberryError:
        pass  # connection is saved; the schedule (or Sync now) will retry

    return _status(user, baby_id)


@router.get("/babies/{baby_id}/huckleberry", response_model=HbStatus)
def get_status(baby_id: str, user: CurrentUser = Depends(get_current_user)):
    get_baby_or_404(user, baby_id)
    return _status(user, baby_id)


@router.patch("/babies/{baby_id}/huckleberry", response_model=HbStatus)
def update_connection(
    baby_id: str, body: HbConnectionUpdate, user: CurrentUser = Depends(get_current_user)
):
    get_baby_or_404(user, baby_id)
    conn = hb.get_connection(user.family_id, baby_id)
    if conn is None:
        raise HTTPException(404, "Huckleberry is not connected")

    updates: dict = {}
    if body.auto_import is not None:
        updates["auto_import"] = body.auto_import
    if body.latch_rate_ml_per_10min is not None:
        updates["latch_rate_ml_per_10min"] = body.latch_rate_ml_per_10min
    if body.mapping is not None:
        foods = get_foods_map(user.family_id)

        def check_liquid(food_id: str) -> None:
            food = foods.get(food_id)
            if food is None or food.unit_basis != "per_100ml":
                raise HTTPException(422, f"{food_id} is not a liquid food")

        stored: dict = {}
        for bottle_type, target in body.mapping.items():
            if bottle_type not in HB_BOTTLE_TYPES:
                raise HTTPException(422, f"Unknown Huckleberry bottle type: {bottle_type!r}")
            if isinstance(target, list):
                if not target:
                    raise HTTPException(422, "A split mapping needs at least one part")
                for part in target:
                    check_liquid(part.food_id)
                stored[bottle_type] = [
                    {"food_id": p.food_id, "parts": p.parts} for p in target
                ]
            else:
                check_liquid(target)
                stored[bottle_type] = target
        updates["mapping"] = {**(conn.get("mapping") or {}), **stored}

    if updates:
        family_items.update_fields(user.family_id, keys.huckleberry_sk(baby_id), updates)
    return _status(user, baby_id)


@router.delete("/babies/{baby_id}/huckleberry", status_code=204)
def disconnect(baby_id: str, user: CurrentUser = Depends(get_current_user)):
    get_baby_or_404(user, baby_id)
    if hb.get_connection(user.family_id, baby_id) is None:
        raise HTTPException(404, "Huckleberry is not connected")
    family_items.delete(user.family_id, keys.huckleberry_sk(baby_id))
    # Drop unreviewed items; imported ones stay as the audit trail behind feeds.
    for imp in hb.list_imports(user.family_id, baby_id):
        if imp.status in ("pending", "deleted_upstream"):
            family_items.delete(user.family_id, keys.hb_import_sk(baby_id, imp.hb_key))


@router.post("/babies/{baby_id}/huckleberry/sync", response_model=HbSyncResult)
async def sync_now(baby_id: str, user: CurrentUser = Depends(get_current_user)):
    get_baby_or_404(user, baby_id)
    try:
        return await hb.sync_baby(user.family_id, baby_id)
    except hb.HuckleberryAuthError as e:
        raise HTTPException(401, str(e))
    except hb.HuckleberryError as e:
        raise HTTPException(502, str(e))


class HbImportPage(BaseModel):
    items: list[HbImport]


@router.get("/babies/{baby_id}/huckleberry/imports", response_model=HbImportPage)
def imports(
    baby_id: str,
    status: Optional[str] = Query(None),
    user: CurrentUser = Depends(get_current_user),
):
    get_baby_or_404(user, baby_id)
    return HbImportPage(items=hb.list_imports(user.family_id, baby_id, status=status))


def _get_import_or_404(user: CurrentUser, baby_id: str, hb_key: str) -> dict:
    imp = hb.get_import(user.family_id, baby_id, hb_key)
    if imp is None:
        raise HTTPException(404, "Import not found")
    return imp


@router.post(
    "/babies/{baby_id}/huckleberry/imports/{hb_key}/confirm", response_model=None
)
def confirm_import(
    baby_id: str,
    hb_key: str,
    body: HbConfirmIn,
    user: CurrentUser = Depends(get_current_user),
):
    baby = get_baby_or_404(user, baby_id)
    imp = _get_import_or_404(user, baby_id, hb_key)
    if imp["status"] != "pending":
        raise HTTPException(409, f"Import is {imp['status']}, not pending")

    conn = hb.get_connection(user.family_id, baby_id)
    mapping = (conn or {}).get("mapping") or {}
    foods = get_foods_map(user.family_id)
    # Stored ISO string -> datetime for feed creation.
    imp = {**imp, "occurred_at": datetime.fromisoformat(imp["occurred_at"].replace("Z", "+00:00"))}

    if imp["mode"] in ("diaper", "medication", "pumping"):
        feed = hb.create_event_from_import(user.family_id, baby, imp)
    else:
        rate = body.rate_ml_per_10min
        if rate is None and conn is not None:
            rate = conn.get("latch_rate_ml_per_10min")
        try:
            feed = hb.create_feed_from_import(
                user.family_id, baby, imp, foods, mapping,
                rate_override=rate,
                measured_ml=body.measured_ml,
                volume_override=body.volume_ml,
            )
        except NutritionError as e:
            raise HTTPException(422, str(e))

    family_items.update_fields(
        user.family_id,
        keys.hb_import_sk(baby_id, hb_key),
        {"status": "imported", "feed_id": feed.id, "updated_at": _now_iso()},
    )
    if body.rate_ml_per_10min is not None and conn is not None:
        # Remember the rate they used — prefills the next breast confirm.
        family_items.update_fields(
            user.family_id,
            keys.huckleberry_sk(baby_id),
            {"latch_rate_ml_per_10min": body.rate_ml_per_10min},
        )
    return feed


@router.post("/babies/{baby_id}/huckleberry/imports/{hb_key}/dismiss", status_code=204)
def dismiss_import(
    baby_id: str, hb_key: str, user: CurrentUser = Depends(get_current_user)
):
    get_baby_or_404(user, baby_id)
    imp = _get_import_or_404(user, baby_id, hb_key)
    if imp["status"] == "imported":
        raise HTTPException(409, "Already imported — delete the feed instead")
    family_items.update_fields(
        user.family_id,
        keys.hb_import_sk(baby_id, hb_key),
        {"status": "dismissed", "updated_at": _now_iso()},
    )
