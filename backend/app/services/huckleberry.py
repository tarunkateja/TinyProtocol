"""Huckleberry -> TinyProtocol feed sync.

Reads the wife's Huckleberry log via the vendored huckleberry_api client
(reverse-engineered Firebase backend) and lands events as review-first import
items; bottle feeds can auto-log once the family trusts the mapping.

Security: the Huckleberry password is used once at connect time and never
stored — only the Firebase refresh token (rotated on every sync) persists.

The two network seams (`authenticate_and_get_children`, `fetch_intervals`)
are module-level so tests can monkeypatch them without touching Firebase.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from ulid import ULID

from app.models.baby import Baby
from app.models.feed import Feed, LatchComponent, LiquidComponent
from app.models.food import Food
from app.models.huckleberry import HbImport, HbSyncResult
from app.repo import families, family_items, keys, logs
from app.services import recipes as recipe_svc
from app.services.nutrition import NutritionError, compute_components

log = logging.getLogger(__name__)

OZ_TO_ML = 29.5735
# Look back far enough to catch backdated entries and late edits; the sync
# runs every 30 minutes, so 72h of overlap is generous.
WINDOW_HOURS = 72


def _normalize_hb_key(hb_key: str) -> str:
    """Huckleberry repacks standalone Firestore docs into "multi" container
    docs as they age; keys minted before 2026-07-17 embedded the container doc
    id ("<container>:<entry>", "d:<container>:<entry>"), which changed on
    repack and duplicated every migrated event. The entry key alone (the
    original doc id) is the stable identity — strip any container prefix,
    keeping the d:/m:/p: collection prefix."""
    prefix, rest = "", hb_key
    if rest[:2] in ("d:", "m:", "p:"):
        prefix, rest = rest[:2], rest[2:]
    return prefix + rest.rsplit(":", 1)[-1]


class HuckleberryAuthError(Exception):
    """Credentials rejected (bad password at connect, revoked token at sync)."""


class HuckleberryError(Exception):
    """Anything else the Huckleberry backend threw at us."""


# --------------------------------------------------------------------------- #
# Read-only enforcement: TinyProtocol NEVER writes to Huckleberry. The vendored
# client has write methods (log_bottle, start_sleep, ...); block them all so a
# future refactor can't call one by accident.
# --------------------------------------------------------------------------- #
_HB_WRITE_PREFIXES = (
    "log_", "start_", "pause_", "resume_", "cancel_", "complete_",
    "switch_", "create_",
)


def _make_readonly_client_class():
    from huckleberry_api.api import HuckleberryAPI

    class ReadOnlyHuckleberryAPI(HuckleberryAPI):
        """Huckleberry access is read-only by policy — the wife's log is the
        source of truth and this integration must never touch it."""

    def _blocked(name):
        def method(self, *args, **kwargs):
            raise RuntimeError(f"Blocked write to Huckleberry (read-only sync): {name}")

        return method

    for _name in dir(HuckleberryAPI):
        if _name.startswith(_HB_WRITE_PREFIXES):
            setattr(ReadOnlyHuckleberryAPI, _name, _blocked(_name))
    return ReadOnlyHuckleberryAPI


# --------------------------------------------------------------------------- #
# Network seams (monkeypatched in tests)
# --------------------------------------------------------------------------- #
async def authenticate_and_get_children(
    email: str, password: str, tz_name: str
) -> dict:
    """Fresh login. Returns refresh_token, user_uid and the child list."""
    import aiohttp

    async with aiohttp.ClientSession() as session:
        api = _make_readonly_client_class()(
            email=email, password=password, timezone=tz_name, websession=session
        )
        try:
            await api.authenticate()
        except aiohttp.ClientResponseError as e:
            if e.status in (400, 401, 403):
                raise HuckleberryAuthError("Huckleberry rejected the email/password") from e
            raise HuckleberryError(f"Huckleberry auth failed: {e}") from e
        except aiohttp.ClientError as e:
            raise HuckleberryError(f"Could not reach Huckleberry: {e}") from e

        try:
            user = await api.get_user()
            if user is None:
                raise HuckleberryError("Huckleberry user document not found")
            children = [
                {"uid": c.cid, "name": c.nickname or c.cid} for c in user.childList
            ]
            # Children shared via Huckleberry family sharing live in hbChilds,
            # not childList — a partner's account must still find the baby.
            seen = {c["uid"] for c in children}
            for cid in (user.hbChilds or {}):
                if cid in seen:
                    continue
                name = cid
                try:
                    child_doc = await api.get_child(cid)
                    if child_doc is not None and child_doc.childsName:
                        name = child_doc.childsName
                except Exception:  # noqa: BLE001 — a shared child we can't read is still selectable
                    pass
                children.append({"uid": cid, "name": name})
        finally:
            await _close_firestore(api)
        return {
            "refresh_token": api.refresh_token,
            "user_uid": api.user_uid,
            "children": children,
        }


async def fetch_intervals(conn: dict, tz_name: str, start: datetime, end: datetime) -> tuple[str, list[dict]]:
    """Fetch feed intervals using the stored refresh token.

    Returns (rotated_refresh_token, events) where each event is a plain dict:
    {hb_key, mode, occurred_at, bottle_type, amount_ml, minutes, notes, last_updated}.
    Solids are dropped here — TinyProtocol liquid feeds can't represent them.
    """
    import aiohttp

    async with aiohttp.ClientSession() as session:
        api = _make_readonly_client_class()(
            email=conn["hb_email"], password="", timezone=tz_name, websession=session
        )
        api.refresh_token = conn["refresh_token"]
        api.user_uid = conn["hb_user_uid"]
        try:
            await api.refresh_session_token()
        except aiohttp.ClientResponseError as e:
            if e.status in (400, 401, 403):
                raise HuckleberryAuthError("Huckleberry session expired — reconnect needed") from e
            raise HuckleberryError(f"Huckleberry token refresh failed: {e}") from e
        except aiohttp.ClientError as e:
            raise HuckleberryError(f"Could not reach Huckleberry: {e}") from e

        try:
            feeds = await api.list_feed_intervals_with_ids(conn["child_uid"], start, end)
            diapers = await api.list_diaper_intervals_with_ids(conn["child_uid"], start, end)
            health = await api.list_health_entries_with_ids(conn["child_uid"], start, end)
            pumps = await api.list_pump_intervals_with_ids(conn["child_uid"], start, end)
        except Exception as e:  # GoogleAPICallError, ValidationError, ...
            raise HuckleberryError(f"Huckleberry fetch failed: {e}") from e
        finally:
            await _close_firestore(api)

        events = []
        for hb_key, interval in feeds:
            normalized = _normalize_interval(hb_key, interval)
            if normalized is not None:
                events.append(normalized)
        # Keys are prefixed per collection: Firestore doc ids are only unique
        # within a collection, and feed keys stay unprefixed for back-compat.
        for hb_key, entry in diapers:
            normalized = _normalize_diaper(f"d:{hb_key}", entry)
            if normalized is not None:
                events.append(normalized)
        for hb_key, entry in health:
            normalized = _normalize_medication(f"m:{hb_key}", entry)
            if normalized is not None:
                events.append(normalized)
        for hb_key, entry in pumps:
            normalized = _normalize_pump(f"p:{hb_key}", entry)
            if normalized is not None:
                events.append(normalized)
        assert api.refresh_token is not None
        return api.refresh_token, events


async def _close_firestore(api) -> None:
    client = getattr(api, "_firestore_client", None)
    if client is not None:
        try:
            await client.close()
        except Exception:  # best-effort; the loop is about to go away anyway
            pass


def _normalize_interval(hb_key: str, interval) -> Optional[dict]:
    mode = getattr(interval, "mode", None)
    occurred_at = datetime.fromtimestamp(float(interval.start), tz=timezone.utc)
    if mode == "bottle":
        amount = float(interval.amount)
        amount_ml = round(amount * OZ_TO_ML, 1) if interval.units == "oz" else amount
        return {
            "hb_key": hb_key,
            "mode": "bottle",
            "occurred_at": occurred_at,
            "bottle_type": interval.bottleType,
            "amount_ml": amount_ml,
            "minutes": None,
            "notes": interval.notes,
            "last_updated": float(interval.lastUpdated) if interval.lastUpdated else None,
        }
    if mode == "breast":
        # Huckleberry stores nursing durations in seconds (timer-based).
        seconds = float(interval.leftDuration or 0) + float(interval.rightDuration or 0)
        return {
            "hb_key": hb_key,
            "mode": "breast",
            "occurred_at": occurred_at,
            "bottle_type": None,
            "amount_ml": None,
            "minutes": round(seconds / 60, 1) or None,
            "notes": interval.notes,
            "last_updated": float(interval.lastUpdated) if interval.lastUpdated else None,
        }
    return None  # solids


# TinyProtocol has no "dry" event and potty rows aren't diapers.
_DIAPER_KIND = {"pee": "pee", "poo": "poop", "both": "both"}


def _normalize_diaper(hb_key: str, entry) -> Optional[dict]:
    kind = _DIAPER_KIND.get(getattr(entry, "mode", None) or "")
    if kind is None or getattr(entry, "isPotty", None):
        return None
    return {
        "hb_key": hb_key,
        "mode": "diaper",
        "occurred_at": datetime.fromtimestamp(float(entry.start), tz=timezone.utc),
        "diaper_kind": kind,
        # Poop details live on the diaper row in Huckleberry (color,
        # consistency) — the answer to "how did she poop" is in here.
        "diaper_color": getattr(entry, "color", None) or None,
        "diaper_consistency": getattr(entry, "consistency", None) or None,
        "notes": entry.notes,
        "last_updated": float(entry.lastUpdated) if entry.lastUpdated else None,
    }


# TP doses are mg/ml; convert what we can, keep the rest human-readable.
_ML_PER_UNIT = {"ml": 1.0, "oz": OZ_TO_ML, "tsp": 4.93}


def _normalize_pump(hb_key: str, entry) -> Optional[dict]:
    left = float(entry.leftAmount or 0)
    right = float(entry.rightAmount or 0)
    total = left + right  # "total" mode stores the whole amount on one side
    if total <= 0:
        return None  # a pump session with no ml can't be a pumping event
    if entry.units == "oz":
        total = round(total * OZ_TO_ML, 1)
    if entry.entryMode == "leftright" and left > 0 and right > 0:
        side = "both"
    elif entry.entryMode == "leftright":
        side = "left" if left > 0 else "right"
    else:
        side = None
    duration = float(entry.duration) / 60 if entry.duration else None
    return {
        "hb_key": hb_key,
        "mode": "pumping",
        "occurred_at": datetime.fromtimestamp(float(entry.start), tz=timezone.utc),
        "pumped_ml": round(total, 1),
        "side": side,
        "duration_minutes": round(duration, 1) if duration else None,
        "notes": entry.notes,
        "last_updated": float(entry.lastUpdated) if entry.lastUpdated else None,
    }


def _normalize_medication(hb_key: str, entry) -> Optional[dict]:
    if getattr(entry, "mode", None) != "medication":
        return None  # growth/temperature entries aren't synced (yet)
    name = entry.medication_name or "Medication"
    amount = float(entry.amount) if entry.amount is not None else None
    units = entry.units
    dose_amount = dose_unit = None
    notes = entry.notes
    if amount is not None and units in _ML_PER_UNIT:
        dose_amount = round(amount * _ML_PER_UNIT[units], 2)
        dose_unit = "ml"
    elif amount is not None:  # drops etc. — keep the fact, skip the fake ml
        suffix = f"{amount:g} {units or 'units'}"
        notes = f"{notes} · {suffix}" if notes else suffix
    return {
        "hb_key": hb_key,
        "mode": "medication",
        "occurred_at": datetime.fromtimestamp(float(entry.start), tz=timezone.utc),
        "med_name": name,
        "dose_amount": dose_amount,
        "dose_unit": dose_unit,
        "notes": notes,
        "last_updated": float(entry.lastUpdated) if entry.lastUpdated else None,
    }


# --------------------------------------------------------------------------- #
# Connection + import storage
# --------------------------------------------------------------------------- #
def get_connection(family_id: str, baby_id: str) -> Optional[dict]:
    return family_items.get(family_id, keys.huckleberry_sk(baby_id))


def list_imports(family_id: str, baby_id: str, status: Optional[str] = None) -> list[HbImport]:
    items = family_items.list_by_prefix(family_id, f"HBIMPORT#{baby_id}#")
    imports = [HbImport.model_validate(i) for i in items]
    if status:
        imports = [i for i in imports if i.status == status]
    return sorted(imports, key=lambda i: i.occurred_at, reverse=True)


def get_import(family_id: str, baby_id: str, hb_key: str) -> Optional[dict]:
    return family_items.get(family_id, keys.hb_import_sk(baby_id, hb_key))


def default_mapping(foods: dict[str, Food]) -> dict[str, str]:
    """Best-guess bottleType -> food mapping from the family's food catalog.

    Only liquid (per_100ml) foods qualify. "Formula" maps to the metabolic
    formula by default: in a GA1 household, "formula" in Huckleberry almost
    certainly means the GA1 mix — the parent can remap in Settings.
    """
    liquids = [f for f in foods.values() if f.unit_basis == "per_100ml" and not f.archived]

    def first_of(category: str) -> Optional[Food]:
        return next((f for f in liquids if f.category == category), None)

    mapping: dict = {}
    bm = first_of("breast_milk")
    formula = first_of("metabolic_formula") or first_of("formula")
    if bm:
        mapping["Breast Milk"] = bm.id
    if formula:
        mapping["Formula"] = formula.id
    if bm and formula:
        # Their Huckleberry convention: "Other" = the mixed bottle. Default to
        # the family's real 40+20 recipe as a ratio; editable in Settings.
        mapping["Other"] = [
            {"food_id": bm.id, "parts": 40},
            {"food_id": formula.id, "parts": 20},
        ]
    return mapping


def is_recipe_mapping(target) -> bool:
    return isinstance(target, dict) and target.get("mode") == "recipe"


def mapping_defaults(mapping: dict) -> tuple[Optional[str], Optional[str]]:
    """(breast milk food, batch/formula food) a recipe split falls back to
    when the recipe itself doesn't name foods."""
    bm = mapping.get("Breast Milk")
    formula = mapping.get("Formula")
    return (
        bm if isinstance(bm, str) else None,
        formula if isinstance(formula, str) else None,
    )


def recipe_food_defaults(
    mapping: dict, foods: Optional[dict[str, Food]] = None
) -> tuple[Optional[str], Optional[str]]:
    """mapping_defaults, then the catalog: once "Formula" itself is mapped
    per recipe there is no plain food id in the mapping, so fall back to the
    family's breast milk / metabolic formula liquids (as default_mapping does)."""
    bm, formula = mapping_defaults(mapping)
    if foods and (bm is None or formula is None):
        liquids = [f for f in foods.values() if f.unit_basis == "per_100ml" and not f.archived]

        def first_of(category: str) -> Optional[str]:
            return next((f.id for f in liquids if f.category == category), None)

        bm = bm or first_of("breast_milk")
        formula = formula or first_of("metabolic_formula") or first_of("formula")
    return bm, formula


def load_recipes(family_id: str, baby_id: str) -> list:
    return recipe_svc.list_recipes(family_id, baby_id)


# --------------------------------------------------------------------------- #
# Feed creation / update from imports
# --------------------------------------------------------------------------- #
def _build_components(
    imp: dict,
    mapping: dict[str, str],
    baby: Baby,
    rate_override: Optional[float] = None,
    measured_ml: Optional[float] = None,
    volume_override: Optional[float] = None,
    recipes: Optional[list] = None,
    foods: Optional[dict[str, Food]] = None,
):
    if imp["mode"] == "bottle":
        bottle_type = imp.get("bottle_type") or ""
        target = mapping.get(bottle_type)
        if not target:
            raise NutritionError(
                f"No food mapped for Huckleberry bottle type {bottle_type!r}"
            )
        amount = volume_override or imp["amount_ml"]
        if is_recipe_mapping(target):
            recipe = recipe_svc.recipe_in_effect(recipes or [], imp["occurred_at"])
            if recipe is None:
                raise NutritionError(
                    "No feeding recipe in effect at that time — add one in Settings → Recipe"
                )
            bm_default, batch_default = recipe_food_defaults(mapping, foods)
            try:
                if bottle_type == "Other":
                    # Their convention: "Other" = the prepared mixed bottle.
                    return recipe_svc.mixed_components(recipe, amount, bm_default, batch_default)
                # Any other recipe-mapped type ("Formula") is a standalone
                # top-up: whatever the recipe says top-ups are made of.
                return recipe_svc.topoff_components(recipe, amount, batch_default)
            except ValueError as e:
                raise NutritionError(str(e))
        if isinstance(target, list):
            # Mixed bottle: split the logged total by the configured ratio.
            total_parts = sum(float(p["parts"]) for p in target)
            return [
                LiquidComponent(
                    kind="liquid",
                    food_id=p["food_id"],
                    volume_ml=round(amount * float(p["parts"]) / total_parts, 1),
                )
                for p in target
            ]
        return [LiquidComponent(kind="liquid", food_id=target, volume_ml=amount)]
    food_id = mapping.get("Breast Milk")
    if not food_id:
        raise NutritionError("No food mapped for breast milk")
    rate = rate_override if rate_override is not None else baby.default_latch_rate_ml_per_10min
    return [
        LatchComponent(
            kind="latch",
            food_id=food_id,
            minutes=imp["minutes"] or 1,
            rate_ml_per_10min=rate,
            measured_ml=measured_ml,
        )
    ]


def _hb_feed_item(family_id: str, feed: Feed, hb_key: str) -> dict:
    from app.routers.feeds import feed_item

    item = feed_item(family_id, feed)
    # Manual edits via PATCH /feeds rebuild the item without these markers,
    # which deliberately breaks the link: sync stops touching a feed the
    # parent has corrected by hand.
    item["source"] = "huckleberry"
    item["hb_key"] = hb_key
    return item


def create_feed_from_import(
    family_id: str,
    baby: Baby,
    imp: dict,
    foods: dict[str, Food],
    mapping: dict[str, str],
    rate_override: Optional[float] = None,
    measured_ml: Optional[float] = None,
    volume_override: Optional[float] = None,
    recipes: Optional[list] = None,
) -> Feed:
    if recipes is None and is_recipe_mapping(mapping.get(imp.get("bottle_type") or "")):
        recipes = load_recipes(family_id, baby.id)
    components = _build_components(
        imp, mapping, baby,
        rate_override=rate_override,
        measured_ml=measured_ml,
        volume_override=volume_override,
        recipes=recipes,
        foods=foods,
    )
    comps, totals = compute_components(components, foods)
    feed = Feed(
        id=str(ULID()),
        baby_id=baby.id,
        occurred_at=imp["occurred_at"],
        components=comps,
        totals=totals,
        notes=imp.get("notes"),
        created_at=datetime.now(timezone.utc),
    )
    logs.put_log(_hb_feed_item(family_id, feed, imp["hb_key"]))
    return feed


def create_event_from_import(family_id: str, baby: Baby, imp: dict) -> "Event":
    """Diaper/medication imports become timeline events, not feeds."""
    from app.models.event import Event
    from app.routers.events import event_item

    if imp["mode"] == "diaper":
        fields = {
            "type": "diaper",
            "diaper_kind": imp["diaper_kind"],
            "diaper_color": imp.get("diaper_color"),
            "diaper_consistency": imp.get("diaper_consistency"),
        }
    elif imp["mode"] == "pumping":
        fields = {
            "type": "pumping",
            "pumped_ml": imp["pumped_ml"],
            "side": imp.get("side"),
            "duration_minutes": imp.get("duration_minutes"),
        }
    else:
        fields = {
            "type": "medication",
            "med_name": imp.get("med_name") or "Medication",
            "dose_amount": imp.get("dose_amount"),
            "dose_unit": imp.get("dose_unit"),
        }
    event = Event(
        id=str(ULID()),
        baby_id=baby.id,
        occurred_at=imp["occurred_at"],
        note=imp.get("notes"),
        created_at=datetime.now(timezone.utc),
        **fields,
    )
    item = event_item(family_id, event)
    item["source"] = "huckleberry"
    item["hb_key"] = imp["hb_key"]
    logs.put_log(item)
    return event


def _maybe_update_imported_event(
    family_id: str, baby: Baby, existing: dict, event: dict
) -> bool:
    """Upstream edit of an imported diaper/medication: mirror onto the event
    while it's still hb-linked (manual edits break the link, same as feeds)."""
    from app.models.event import Event
    from app.routers.events import event_item

    log_id = existing.get("feed_id")
    if not log_id:
        return False
    raw = logs.find_log(log_id, family_id)
    # Compare normalized: events created before the key-stability fix carry a
    # container-prefixed hb_key that never gets rewritten.
    if raw is None or _normalize_hb_key(raw.get("hb_key") or "") != _normalize_hb_key(
        existing["hb_key"]
    ):
        return False
    old = Event.model_validate(raw)
    updated = old.model_copy(
        update={
            "occurred_at": event["occurred_at"],
            "diaper_kind": event.get("diaper_kind") or old.diaper_kind,
            "diaper_color": event.get("diaper_color"),
            "diaper_consistency": event.get("diaper_consistency"),
            "pumped_ml": event.get("pumped_ml") or old.pumped_ml,
            "side": event.get("side") or old.side,
            "duration_minutes": event.get("duration_minutes") or old.duration_minutes,
            "med_name": event.get("med_name") or old.med_name,
            "dose_amount": event.get("dose_amount"),
            "dose_unit": event.get("dose_unit"),
            "note": event.get("notes") or old.note,
        }
    )
    item = event_item(family_id, updated)
    item["source"] = "huckleberry"
    item["hb_key"] = existing["hb_key"]
    logs.replace_log(raw["PK"], raw["SK"], item)
    return True


def _maybe_update_imported_feed(
    family_id: str,
    baby: Baby,
    existing: dict,
    event: dict,
    foods: dict[str, Food],
    mapping: Optional[dict] = None,
    recipes: Optional[list] = None,
) -> bool:
    """Upstream edit of an already-imported event: mirror it onto the feed,
    but only while the feed is still hb-linked and simple (one component)."""
    feed_id = existing.get("feed_id")
    if not feed_id:
        return False
    raw = logs.find_log(feed_id, family_id)
    # Normalized comparison: feeds created before the key-stability fix carry
    # a container-prefixed hb_key that never gets rewritten.
    if raw is None or _normalize_hb_key(raw.get("hb_key") or "") != _normalize_hb_key(
        existing["hb_key"]
    ):
        return False  # deleted or manually edited — hands off
    feed = Feed.model_validate(raw)

    target = (mapping or {}).get(event.get("bottle_type") or "")
    if event["mode"] == "bottle" and is_recipe_mapping(target):
        # Recipe-mapped bottle: re-resolve against the recipe in effect at
        # the (possibly edited) time — a 75 → 85 correction is a full bottle,
        # not a scaled partial one.
        try:
            new_components = _build_components(
                event, mapping, baby, recipes=recipes, foods=foods
            )
        except NutritionError:
            return False
    elif event["mode"] == "bottle" and all(c.kind == "liquid" for c in feed.components):
        # Scale every component so a split feed keeps its ratio when the
        # total is corrected upstream (60 -> 75 keeps 2:1 at 50 + 25).
        old_total = sum(c.volume_ml for c in feed.components)
        if not old_total:
            return False
        factor = event["amount_ml"] / old_total
        new_components = [
            LiquidComponent(
                kind="liquid", food_id=c.food_id, volume_ml=round(c.volume_ml * factor, 1)
            )
            for c in feed.components
        ]
    elif (
        event["mode"] == "breast"
        and len(feed.components) == 1
        and feed.components[0].kind == "latch"
    ):
        comp = feed.components[0]
        new_components = [
            LatchComponent(
                kind="latch",
                food_id=comp.food_id,
                minutes=event["minutes"] or 1,
                rate_ml_per_10min=comp.rate_ml_per_10min,
                measured_ml=comp.measured_ml,
            )
        ]
    else:
        return False

    comps, totals = compute_components(new_components, foods)
    updated = Feed(
        id=feed.id,
        baby_id=feed.baby_id,
        occurred_at=event["occurred_at"],
        components=comps,
        totals=totals,
        notes=event.get("notes") or feed.notes,
        created_at=feed.created_at,
    )
    logs.replace_log(raw["PK"], raw["SK"], _hb_feed_item(family_id, updated, existing["hb_key"]))
    return True


def _auto_log(
    family_id: str,
    baby: Baby,
    event: dict,
    foods: dict,
    mapping: dict,
    conn: dict,
    recipes: Optional[list] = None,
) -> Optional[str]:
    """Create the feed/event for an auto-imported item; None = leave pending."""
    mode = event["mode"]
    if mode == "bottle":
        if not mapping.get(event.get("bottle_type") or ""):
            return None  # unmapped type — a human decides
        return create_feed_from_import(
            family_id, baby, event, foods, mapping, recipes=recipes
        ).id
    if mode == "breast":
        if not mapping.get("Breast Milk"):
            return None
        # Estimated from the family's configured rate; the feed is marked
        # estimated and stays editable like any other.
        rate = conn.get("latch_rate_ml_per_10min")
        return create_feed_from_import(
            family_id, baby, event, foods, mapping, rate_override=rate
        ).id
    if mode in ("diaper", "medication", "pumping"):
        return create_event_from_import(family_id, baby, event).id
    return None


# --------------------------------------------------------------------------- #
# The sync itself
# --------------------------------------------------------------------------- #
def _import_fields(event: dict, status: str, mapping: dict[str, str], now_iso: str) -> dict:
    return {
        "item_type": "HBIMPORT",
        "hb_key": event["hb_key"],
        "status": status,
        "mode": event["mode"],
        "occurred_at": keys.iso_z(event["occurred_at"]),
        "bottle_type": event.get("bottle_type"),
        "amount_ml": event.get("amount_ml"),
        "minutes": event.get("minutes"),
        "diaper_kind": event.get("diaper_kind"),
        "diaper_color": event.get("diaper_color"),
        "diaper_consistency": event.get("diaper_consistency"),
        "pumped_ml": event.get("pumped_ml"),
        "side": event.get("side"),
        "duration_minutes": event.get("duration_minutes"),
        "med_name": event.get("med_name"),
        "dose_amount": event.get("dose_amount"),
        "dose_unit": event.get("dose_unit"),
        "notes": event.get("notes"),
        "hb_last_updated": event.get("last_updated"),
        "food_id": _single_food(mapping.get(event.get("bottle_type") or "Breast Milk")),
        "updated_at": now_iso,
    }


def _single_food(target) -> Optional[str]:
    """Display-only food id for an import row; splits have no single food."""
    return target if isinstance(target, str) else None


def _event_changed(existing: dict, event: dict) -> bool:
    return (
        existing.get("occurred_at") != keys.iso_z(event["occurred_at"])
        or existing.get("amount_ml") != event.get("amount_ml")
        or existing.get("minutes") != event.get("minutes")
        or existing.get("bottle_type") != event.get("bottle_type")
        or existing.get("diaper_kind") != event.get("diaper_kind")
        or (existing.get("diaper_color") or None) != (event.get("diaper_color") or None)
        or (existing.get("diaper_consistency") or None) != (event.get("diaper_consistency") or None)
        or existing.get("pumped_ml") != event.get("pumped_ml")
        or existing.get("med_name") != event.get("med_name")
        or existing.get("dose_amount") != event.get("dose_amount")
        or (existing.get("notes") or None) != (event.get("notes") or None)
    )


async def sync_baby(family_id: str, baby_id: str) -> HbSyncResult:
    """One sync pass for one baby. Raises HuckleberryAuthError/HuckleberryError
    only after recording the failure on the connection item."""
    conn = get_connection(family_id, baby_id)
    if conn is None:
        raise HuckleberryError("Huckleberry is not connected for this baby")

    family = families.get_family(family_id)
    tz_name = (family or {}).get("timezone", "UTC")
    now = datetime.now(timezone.utc)
    start, end = now - timedelta(hours=WINDOW_HOURS), now + timedelta(hours=1)

    try:
        new_refresh_token, events = await fetch_intervals(conn, tz_name, start, end)
    except (HuckleberryAuthError, HuckleberryError) as e:
        family_items.update_fields(
            family_id,
            keys.huckleberry_sk(baby_id),
            {
                "status": "auth_failed" if isinstance(e, HuckleberryAuthError) else "error",
                # Short, human-readable — pydantic dumps don't belong in the UI.
                "last_error": str(e).split("\n")[0][:200],
            },
        )
        raise

    baby_item = family_items.get(family_id, keys.baby_sk(baby_id))
    baby = Baby.model_validate(baby_item)
    foods = {
        f.id: f
        for f in (
            Food.model_validate(i)
            for i in family_items.list_by_prefix(family_id, "FOOD#")
        )
    }
    mapping: dict = conn.get("mapping") or {}
    auto_import = bool(conn.get("auto_import"))
    recipes = load_recipes(family_id, baby_id) if any(
        is_recipe_mapping(t) for t in mapping.values()
    ) else []

    existing_items = family_items.list_by_prefix(family_id, f"HBIMPORT#{baby_id}#")
    # Self-heal imports stored under legacy container-prefixed keys: rewrite
    # them to the normalized key so fetched events match instead of
    # re-importing. On a collision (a pre-fix duplicate pair still in the
    # table), the normalized row keeps the key and the legacy row is left
    # alone — resolving that duplicate is a human/cleanup-script decision.
    canonical_keys = {i["hb_key"] for i in existing_items}
    by_key = {}
    for item in existing_items:
        norm = _normalize_hb_key(item["hb_key"])
        if norm != item["hb_key"]:
            if norm in canonical_keys or norm in by_key:
                continue
            family_items.delete(family_id, keys.hb_import_sk(baby_id, item["hb_key"]))
            item = {**item, "hb_key": norm, "SK": keys.hb_import_sk(baby_id, norm)}
            family_items.put(family_id, keys.hb_import_sk(baby_id, norm), item)
        by_key[norm] = item

    result = HbSyncResult(fetched=len(events))
    now_iso = keys.iso_z(now)
    seen_keys = set()

    for event in events:
        seen_keys.add(event["hb_key"])
        existing = by_key.get(event["hb_key"])
        sk = keys.hb_import_sk(baby_id, event["hb_key"])

        if existing is None:
            fields = _import_fields(event, "pending", mapping, now_iso)
            fields["baby_id"] = baby_id
            fields["created_at"] = now_iso
            if auto_import:
                try:
                    log_id = _auto_log(
                        family_id, baby, event, foods, mapping, conn, recipes=recipes
                    )
                except NutritionError as e:
                    log.warning("Auto-import failed, leaving pending: %s", e)
                    log_id = None
                if log_id:
                    fields["status"] = "imported"
                    fields["feed_id"] = log_id
                    result.auto_imported += 1
                else:
                    result.new_pending += 1
            else:
                result.new_pending += 1
            family_items.put(family_id, sk, fields)
            continue

        if not _event_changed(existing, event):
            continue

        if existing["status"] == "pending":
            fields = _import_fields(event, "pending", mapping, now_iso)
            fields["baby_id"] = baby_id
            fields["created_at"] = existing.get("created_at", now_iso)
            family_items.put(family_id, sk, fields)
            result.updated += 1
        elif existing["status"] == "imported":
            if event["mode"] in ("diaper", "medication", "pumping"):
                updated_ok = _maybe_update_imported_event(family_id, baby, existing, event)
            else:
                updated_ok = _maybe_update_imported_feed(
                    family_id, baby, existing, event, foods, mapping=mapping, recipes=recipes
                )
            if updated_ok:
                fields = _import_fields(event, "imported", mapping, now_iso)
                fields["baby_id"] = baby_id
                fields["created_at"] = existing.get("created_at", now_iso)
                fields["feed_id"] = existing["feed_id"]
                family_items.put(family_id, sk, fields)
                result.updated += 1
        # dismissed / deleted_upstream: parent said no — stay quiet.

    # Deletion detection: an import whose event should be inside the fetch
    # window but wasn't returned was deleted (or moved far away) upstream.
    window_lo = keys.iso_z(start)
    for hb_key, existing in by_key.items():
        if hb_key in seen_keys or existing.get("occurred_at", "") < window_lo:
            continue
        sk = keys.hb_import_sk(baby_id, hb_key)
        if existing["status"] == "pending":
            family_items.delete(family_id, sk)  # never logged; nothing to review
            result.deleted_upstream += 1
        elif existing["status"] == "imported":
            family_items.update_fields(
                family_id, sk, {"status": "deleted_upstream", "updated_at": now_iso}
            )
            result.deleted_upstream += 1

    family_items.update_fields(
        family_id,
        keys.huckleberry_sk(baby_id),
        {
            "refresh_token": new_refresh_token,
            "last_synced_at": now_iso,
            "status": "ok",
            "last_error": "",
        },
    )
    return result


def sync_all_connections() -> list[dict]:
    """Scheduled entrypoint: every connected baby across all families."""
    connections = family_items.scan_sk_prefix("HUCKLEBERRY#")
    results = []
    for conn in connections:
        family_id = conn["PK"].split("#", 1)[1]
        baby_id = conn["SK"].split("#", 1)[1]
        try:
            result = asyncio.run(sync_baby(family_id, baby_id))
            results.append({"family_id": family_id, "baby_id": baby_id, **result.model_dump()})
        except Exception as e:
            log.exception("Huckleberry sync failed for baby %s", baby_id)
            results.append({"family_id": family_id, "baby_id": baby_id, "error": str(e)})
    return results
