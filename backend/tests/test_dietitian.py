"""The dietitian update: the exact MyChart message format — family days,
one bullet per feed, no split, one total per day, this-morning section —
plus the pre-send warnings."""

import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.models.baby import Baby
from app.services.assistant import _run_tool
from tests.test_huckleberry import _bottle, _sync, hb_client, hb_events  # noqa: F401

TZ = ZoneInfo("America/New_York")


def _local(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=TZ).astimezone(timezone.utc).isoformat()


def _feed(c, at, *components, notes=None):
    body = {"occurred_at": at, "components": list(components)}
    if notes:
        body["notes"] = notes
    resp = c.post(f"/v1/babies/{c.baby_id}/feeds", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _liquid(food, ml):
    return {"kind": "liquid", "food_id": food["id"], "volume_ml": ml}


def _setup_plan(c):
    """8 AM family day; 55 + 35 = 90 ml bottles with Pro-Phree top-ups."""
    assert c.patch("/v1/family", json={"day_start": "08:00"}).status_code == 200
    bm = c.foods["Breast milk"]
    ga1 = c.foods["GA1 metabolic formula (prepared)"]
    resp = c.post("/v1/foods", json={
        "name": "Pro-Phree top-up (prepared)", "category": "metabolic_formula",
        "unit_basis": "per_100ml", "natural_protein_g_per_unit": 0, "lysine_mg_per_unit": 0,
    })
    assert resp.status_code == 201, resp.text
    prophree = resp.json()
    resp = c.post(f"/v1/babies/{c.baby_id}/recipes", json={
        "label": "90s", "effective_at": _local(2026, 9, 1, 8),
        "breast_milk_ml": 55, "batch_ml": 35,
        "powders": [{"name": "Glutarex-1", "grams": 30}, {"name": "Pro-Phree", "grams": 17}],
        "batch_final_volume_ml": 280, "feeds_per_day": 8,
        "breast_milk_food_id": bm["id"], "batch_food_id": ga1["id"],
        "topoff_powders": [{"name": "Pro-Phree", "grams": 9}], "topoff_water_ml": 60,
        "topoff_food_id": prophree["id"],
    })
    assert resp.status_code == 201, resp.text
    return bm, ga1, prophree


def test_dietitian_update_text(auth_client):
    c = auth_client
    bm, ga1, prophree = _setup_plan(c)

    # Friday 9/25 (8 AM 9/25 → 8 AM 9/26)
    _feed(c, _local(2026, 9, 25, 9), _liquid(bm, 55), _liquid(ga1, 35), notes="large spit up")
    _feed(c, _local(2026, 9, 25, 12, 10), _liquid(bm, 55), _liquid(ga1, 45))  # bottle + top-off
    _feed(c, _local(2026, 9, 25, 15, 5), _liquid(prophree, 20))
    _feed(c, _local(2026, 9, 25, 18), _liquid(bm, 42.8), _liquid(ga1, 27.2))  # partial bottle
    _feed(c, _local(2026, 9, 25, 18), _liquid(bm, 20))  # same minute → one bullet
    _feed(c, _local(2026, 9, 26, 2), _liquid(bm, 90))  # still Friday; looks mislabeled
    resp = c.post(f"/v1/babies/{c.baby_id}/events", json={
        "occurred_at": _local(2026, 9, 25, 8, 30), "type": "weight", "weight_g": 5270,
    })
    assert resp.status_code == 201, resp.text
    # Saturday 9/26: nothing. Sunday 9/27 morning: one feed before "send time".
    _feed(c, _local(2026, 9, 27, 8, 10), _liquid(bm, 55), _liquid(ga1, 35))

    r = c.get(
        f"/v1/babies/{c.baby_id}/reports/dietitian",
        params={"days": 2, "as_of_local": "2026-09-27T09:50:00"},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["text"] == "\n".join([
        "Friday 9/25",
        "  - 9:00 AM — 90 ml prepared mix (large spit up)",
        "  - 12:10 PM — 100 ml (90 ml prepared mix + 10 ml top-off)",
        "  - 3:05 PM — 20 ml Pro-Phree top-up",
        "  - 6:00 PM — 70 ml prepared mix + 20 ml breast milk",
        "  - 2:00 AM — 90 ml breast milk",
        "Total: 390 ml (262.8 ml breast milk).",
        "Weight: 5.27 kg",
        "",
        "Saturday 9/26",
        "  - nothing logged",
        "",
        "This morning",
        "  - 8:10 AM — 90 ml prepared mix",
    ])

    fri, sat, today = body["sections"]
    assert fri["feed_count"] == 6 and fri["total_ml"] == 390
    assert fri["breast_milk_ml"] == 262.8
    assert fri["batch_ml"] == 35 + 45 + 27.2 and fri["topup_ml"] == 20
    assert len(fri["lines"]) == 5 and len(fri["lines"][3]["feed_ids"]) == 2
    assert sat["feed_count"] == 0
    assert today["partial"] is True and today["label"] == "This morning"

    r = c.get(
        f"/v1/babies/{c.baby_id}/reports/dietitian",
        params={"days": 2, "as_of_local": "2026-09-27T09:50:00", "notes": "false"},
    )
    assert "  - 9:00 AM — 90 ml prepared mix\n" in r.json()["text"]
    assert "spit up" not in r.json()["text"]

    msgs = [w["message"] for w in body["warnings"]]
    assert any("12:10 PM: 100 ml logged vs the 90 ml bottle" in m for m in msgs)
    assert any("2:00 AM: 90 ml breast-milk-only bottle" in m for m in msgs)
    assert any(m == "Saturday 9/26: no feeds logged" for m in msgs)
    assert len(msgs) == 3


def test_afternoon_partial_label_and_day_count(auth_client):
    c = auth_client
    bm, ga1, _ = _setup_plan(c)
    _feed(c, _local(2026, 9, 27, 13), _liquid(bm, 55), _liquid(ga1, 35))
    r = c.get(
        f"/v1/babies/{c.baby_id}/reports/dietitian",
        params={"days": 1, "as_of_local": "2026-09-27T15:00:00"},
    )
    body = r.json()
    assert [s["label"] for s in body["sections"]] == ["Saturday 9/26", "Sunday 9/27 (so far)"]
    # A partial day never gets a Total line.
    assert "Total:" not in body["sections"][1]["text"]
    # Before 8 AM the family day is still Saturday; it has nothing logged yet
    # (the 1 PM feed is in the future), so the partial section is left out.
    r = c.get(
        f"/v1/babies/{c.baby_id}/reports/dietitian",
        params={"days": 1, "as_of_local": "2026-09-27T07:30:00"},
    )
    assert [s["label"] for s in r.json()["sections"]] == ["Friday 9/25"]
    assert c.get(f"/v1/babies/{c.baby_id}/reports/dietitian", params={"days": 15}).status_code == 422


def test_pending_huckleberry_import_is_a_warning(hb_client):
    c = hb_client
    c.hb_events.append(_bottle("k1", hours_ago=2, bottle_type="Formula", amount_ml=65.0))
    _sync(c)  # review-first: the bottle is pending, not a feed yet
    body = c.get(f"/v1/babies/{c.baby_id}/reports/dietitian", params={"days": 1}).json()
    msgs = [w["message"] for w in body["warnings"]]
    assert any("65 ml Formula still pending in Huckleberry review" in m for m in msgs)


def test_assistant_tool_returns_the_same_text(auth_client):
    c = auth_client
    bm, ga1, _ = _setup_plan(c)
    _feed(c, _local(2026, 9, 26, 9), _liquid(bm, 55), _liquid(ga1, 35))
    baby = Baby.model_validate(c.get(f"/v1/babies/{c.baby_id}").json())
    family_id = c.get("/v1/family").json()["id"]
    from datetime import time

    out = json.loads(_run_tool(
        "get_dietitian_update", {"days": 400}, baby, "America/New_York",
        day_start=time(8, 0), family_id=family_id,
    ))
    assert out["days"] == 14  # clamped
    assert "Saturday 9/26\n  - 9:00 AM — 90 ml prepared mix\nTotal: 90 ml (55 ml breast milk)." in out["text"]
    assert isinstance(out["warnings"], list)
