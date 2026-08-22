"""Feeding recipes: effective-dated history, the bottle split rule, and the
Huckleberry "per recipe" mapping that makes plan changes a Settings edit."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.recipe import Recipe
from app.services import recipes as svc
from app.services.assistant import _run_tool
from app.models.baby import Baby
from tests.test_huckleberry import _bottle, _family_id, _imports, _sync, hb_client, hb_events  # noqa: F401

T0 = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _recipe(**over) -> Recipe:
    base = dict(
        id="r1", created_at=T0, label="plan", effective_at=T0,
        breast_milk_ml=55, batch_ml=30,
    )
    return Recipe(**{**base, **over})


# --------------------------------------------------------------------------- #
# Split rule
# --------------------------------------------------------------------------- #
def test_split_partial_full_and_topoff():
    r = _recipe()  # 55 + 30 = 85 prepared
    assert svc.split_bottle(r, 85) == (55, 30)  # the whole bottle
    assert svc.split_bottle(r, 75) == (48.5, 26.5)  # partial: proportional
    assert svc.split_bottle(r, 110) == (55, 55)  # bottle + 25 ml top-off from batch
    bm, batch = svc.split_bottle(r, 50)
    assert bm + batch == 50


def test_split_single_ingredient_recipes():
    assert svc.split_bottle(_recipe(breast_milk_ml=0, batch_ml=80), 60) == (0, 60)
    assert svc.split_bottle(_recipe(breast_milk_ml=80, batch_ml=0), 60) == (60, 0)


def test_recipe_in_effect_picks_newest_at_or_before():
    a = _recipe(id="a", effective_at=T0)
    b = _recipe(id="b", effective_at=T0 + timedelta(days=10))
    assert svc.recipe_in_effect([a, b], T0 - timedelta(hours=1)) is None
    assert svc.recipe_in_effect([a, b], T0).id == "a"
    assert svc.recipe_in_effect([a, b], T0 + timedelta(days=10)).id == "b"
    assert svc.recipe_in_effect([a, b], T0 + timedelta(days=99)).id == "b"


# --------------------------------------------------------------------------- #
# CRUD + history
# --------------------------------------------------------------------------- #
def _post_recipe(c, **body):
    base = {
        "label": "Plan", "effective_at": T0.isoformat(),
        "breast_milk_ml": 55, "batch_ml": 25,
        "powders": [{"name": "Anamix", "grams": 30}, {"name": "Pro-Phree", "grams": 20}],
        "batch_final_volume_ml": 310,
    }
    resp = c.post(f"/v1/babies/{c.baby_id}/recipes", json={**base, **body})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_recipe_history_is_chronological_and_editable(auth_client):
    c = auth_client
    later = _post_recipe(c, label="85s", effective_at=(T0 + timedelta(days=16)).isoformat(), batch_ml=30)
    first = _post_recipe(c, label="80s")
    assert first["prepared_ml"] == 80 and first["feeds_per_batch"] == 12.4

    rows = c.get(f"/v1/babies/{c.baby_id}/recipes").json()
    assert [r["label"] for r in rows] == ["80s", "85s"]

    # Same start time twice is a mistake, not a second recipe.
    resp = c.post(f"/v1/babies/{c.baby_id}/recipes", json={
        "label": "dup", "effective_at": T0.isoformat(), "breast_milk_ml": 1, "batch_ml": 1,
    })
    assert resp.status_code == 409

    # current?at= resolves the right period.
    at = (T0 + timedelta(days=3)).isoformat()
    assert c.get(f"/v1/babies/{c.baby_id}/recipes/current", params={"at": at}).json()["label"] == "80s"
    assert c.get(f"/v1/babies/{c.baby_id}/recipes/current").json()["label"] == "85s"
    before = (T0 - timedelta(days=1)).isoformat()
    assert c.get(f"/v1/babies/{c.baby_id}/recipes/current", params={"at": before}).json() is None

    # Moving a recipe's start moves it in history (SK changes).
    resp = c.patch(
        f"/v1/babies/{c.baby_id}/recipes/{later['id']}",
        json={"effective_at": (T0 - timedelta(days=5)).isoformat(), "batch_final_volume_ml": 280},
    )
    assert resp.status_code == 200, resp.text
    rows = c.get(f"/v1/babies/{c.baby_id}/recipes").json()
    assert [r["label"] for r in rows] == ["85s", "80s"]
    assert rows[0]["batch_final_volume_ml"] == 280 and len(rows) == 2

    assert c.delete(f"/v1/babies/{c.baby_id}/recipes/{first['id']}").status_code == 204
    assert [r["label"] for r in c.get(f"/v1/babies/{c.baby_id}/recipes").json()] == ["85s"]


def test_recipe_needs_some_volume(auth_client):
    c = auth_client
    resp = c.post(f"/v1/babies/{c.baby_id}/recipes", json={
        "label": "empty", "effective_at": T0.isoformat(), "breast_milk_ml": 0, "batch_ml": 0,
    })
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# Huckleberry "per recipe" mapping
# --------------------------------------------------------------------------- #
def _enable_recipe_mode(c):
    resp = c.patch(
        f"/v1/babies/{c.baby_id}/huckleberry",
        json={"mapping": {"Other": {"mode": "recipe"}}, "auto_import": True},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _feed_split(c, feed_id):
    feed = c.get(f"/v1/feeds/{feed_id}").json()
    return {comp["food_name"]: comp["volume_ml"] for comp in feed["components"]}


def test_recipe_mode_splits_by_the_recipe_in_effect(hb_client):
    c = hb_client
    now = datetime.now(timezone.utc)
    # 80 ml bottles (55+25) until 30h ago, then 85 ml bottles (55+30).
    _post_recipe(c, label="80s", effective_at=(now - timedelta(days=30)).isoformat())
    _post_recipe(c, label="85s", effective_at=(now - timedelta(hours=30)).isoformat(), batch_ml=30)
    status = _enable_recipe_mode(c)
    assert status["mapping"]["Other"]["recipe"] is True
    assert "55 bm + 30 batch = 85 ml/feed" in status["mapping"]["Other"]["recipe_summary"]

    c.hb_events.extend([
        _bottle("old-full", 40, bottle_type="Other", amount_ml=80.0),
        _bottle("old-part", 38, bottle_type="Other", amount_ml=60.0),
        _bottle("new-full", 20, bottle_type="Other", amount_ml=85.0),
        _bottle("new-part", 10, bottle_type="Other", amount_ml=75.0),
        _bottle("new-topoff", 5, bottle_type="Other", amount_ml=110.0),
        _bottle("plain", 4, bottle_type="Formula", amount_ml=30.0),
    ])
    result = _sync(c)
    assert result["auto_imported"] == 6
    by_key = {i["hb_key"]: i for i in _imports(c, "imported")}
    assert _feed_split(c, by_key["old-full"]["feed_id"]) == {
        "Breast milk": 55, "GA1 metabolic formula (prepared)": 25,
    }
    assert _feed_split(c, by_key["old-part"]["feed_id"]) == {
        "Breast milk": 41.3, "GA1 metabolic formula (prepared)": 18.7,
    }
    assert _feed_split(c, by_key["new-full"]["feed_id"]) == {
        "Breast milk": 55, "GA1 metabolic formula (prepared)": 30,
    }
    assert _feed_split(c, by_key["new-part"]["feed_id"]) == {
        "Breast milk": 48.5, "GA1 metabolic formula (prepared)": 26.5,
    }
    assert _feed_split(c, by_key["new-topoff"]["feed_id"]) == {
        "Breast milk": 55, "GA1 metabolic formula (prepared)": 55,
    }
    assert _feed_split(c, by_key["plain"]["feed_id"]) == {"GA1 metabolic formula (prepared)": 30}

    # Upstream correction 75 -> 85 re-resolves as a full bottle (not scaled).
    ev = next(e for e in c.hb_events if e["hb_key"] == "new-part")
    ev["amount_ml"] = 85.0
    ev["last_updated"] = 2000.0
    assert _sync(c)["updated"] == 1
    assert _feed_split(c, by_key["new-part"]["feed_id"]) == {
        "Breast milk": 55, "GA1 metabolic formula (prepared)": 30,
    }


def test_recipe_mode_without_a_recipe_leaves_the_bottle_pending(hb_client):
    c = hb_client
    _enable_recipe_mode(c)
    c.hb_events.append(_bottle("mix", 2, bottle_type="Other", amount_ml=80.0))
    result = _sync(c)
    assert result["auto_imported"] == 0 and result["new_pending"] == 1
    pending = _imports(c, "pending")
    assert pending[0]["hb_key"] == "mix"
    resp = c.post(f"/v1/babies/{c.baby_id}/huckleberry/imports/mix/confirm", json={})
    assert resp.status_code == 422 and "recipe" in resp.json()["detail"].lower()


def test_resplit_reapplies_the_recipe_and_skips_hand_edits(hb_client):
    c = hb_client
    now = datetime.now(timezone.utc)
    # Era 1: the old fixed 55:25 ratio mapping imported everything.
    c.patch(f"/v1/babies/{c.baby_id}/huckleberry", json={"auto_import": True})
    foods = c.foods
    c.patch(f"/v1/babies/{c.baby_id}/huckleberry", json={"mapping": {"Other": [
        {"food_id": foods["Breast milk"]["id"], "parts": 55},
        {"food_id": foods["GA1 metabolic formula (prepared)"]["id"], "parts": 25},
    ]}})
    c.hb_events.extend([
        _bottle("a", 30, bottle_type="Other", amount_ml=80.0),   # 55/25 either way
        _bottle("b", 20, bottle_type="Other", amount_ml=85.0),   # 58.4/26.6 -> 55/30
        _bottle("c", 10, bottle_type="Other", amount_ml=75.0),   # 51.6/23.4 -> 48.5/26.5
        _bottle("d", 8, bottle_type="Other", amount_ml=85.0),    # will be hand-edited
        _bottle("e", 50, bottle_type="Other", amount_ml=70.0),   # before any recipe
    ])
    _sync(c)
    by_key = {i["hb_key"]: i for i in _imports(c, "imported")}
    assert _feed_split(c, by_key["b"]["feed_id"])["Breast milk"] == 58.4

    # Parent corrects one feed by hand — the hb link breaks, re-split must not touch it.
    resp = c.patch(f"/v1/feeds/{by_key['d']['feed_id']}", json={"notes": "checked"})
    assert resp.status_code == 200

    # Era 2: recipes + per-recipe mapping.
    _post_recipe(c, label="80s", effective_at=(now - timedelta(hours=40)).isoformat())
    _post_recipe(c, label="85s", effective_at=(now - timedelta(hours=25)).isoformat(), batch_ml=30)
    _enable_recipe_mode(c)

    params = {
        "from": (now - timedelta(days=3)).isoformat(),
        "to": (now + timedelta(hours=1)).isoformat(),
    }
    preview = c.post(f"/v1/babies/{c.baby_id}/recipes/resplit", params=params).json()
    assert preview["applied"] is False
    assert preview["unchanged"] == 1  # "a"
    assert preview["skipped_no_recipe"] == 1  # "e"
    changed = {ch["feed_id"]: ch for ch in preview["changes"]}
    assert set(changed) == {by_key["b"]["feed_id"], by_key["c"]["feed_id"]}
    assert changed[by_key["b"]["feed_id"]]["after"] == {
        "Breast milk": 55, "GA1 metabolic formula (prepared)": 30,
    }
    assert changed[by_key["b"]["feed_id"]]["recipe_label"] == "85s"
    # Preview wrote nothing.
    assert _feed_split(c, by_key["b"]["feed_id"])["Breast milk"] == 58.4

    applied = c.post(
        f"/v1/babies/{c.baby_id}/recipes/resplit", params={**params, "apply": "true"}
    ).json()
    assert applied["applied"] is True and len(applied["changes"]) == 2
    assert _feed_split(c, by_key["b"]["feed_id"]) == {
        "Breast milk": 55, "GA1 metabolic formula (prepared)": 30,
    }
    assert _feed_split(c, by_key["c"]["feed_id"]) == {
        "Breast milk": 48.5, "GA1 metabolic formula (prepared)": 26.5,
    }
    assert _feed_split(c, by_key["d"]["feed_id"])["Breast milk"] == 58.4  # untouched
    feed_b = c.get(f"/v1/feeds/{by_key['b']['feed_id']}").json()
    assert feed_b["totals"]["total_ml"] == 85

    # Second run: nothing left to do, and the feeds stay hb-linked for future syncs.
    again = c.post(f"/v1/babies/{c.baby_id}/recipes/resplit", params=params).json()
    assert again["changes"] == [] and again["unchanged"] == 3


def test_assistant_recipe_history_tool(auth_client):
    c = auth_client
    _post_recipe(c, label="80s", source="Madison via MyChart")
    _post_recipe(c, label="85s", effective_at=(T0 + timedelta(days=16, hours=22)).isoformat(), batch_ml=30)
    baby = Baby.model_validate(c.get(f"/v1/babies/{c.baby_id}").json())
    import json

    out = json.loads(_run_tool(
        "get_recipe_history", {}, baby, "America/Chicago", family_id=_family_id(c)
    ))
    assert [r["label"] for r in out["recipes"]] == ["80s", "85s"]
    assert out["recipes"][0]["effective_until"] == "2026-08-17 17:00"
    assert out["recipes"][0]["source"] == "Madison via MyChart"
    assert out["current"]["per_feed"] == {"breast_milk_ml": 55, "batch_formula_ml": 30, "prepared_ml": 85}
    assert out["current"]["batch"]["feeds_per_batch"] == 10.3
