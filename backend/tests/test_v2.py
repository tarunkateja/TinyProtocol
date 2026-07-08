"""v2 features: pumping/diaper events, volume targets, since-windows, presets."""

from datetime import datetime, timedelta, timezone

from app.services.tz import since_local
from datetime import time as dtime
from zoneinfo import ZoneInfo


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def test_pumping_and_diaper_in_summary(auth_client):
    c = auth_client
    baby_id = c.baby_id
    now = datetime.now(timezone.utc)
    bm = c.foods["Breast milk"]
    ga1_prepared = c.foods["GA1 metabolic formula (prepared)"]

    # Their real mix: 40 ml breast milk + 20 ml prepared GA1 formula.
    resp = c.post(
        f"/v1/babies/{baby_id}/feeds",
        json={
            "occurred_at": _iso(now - timedelta(hours=1)),
            "components": [
                {"kind": "liquid", "food_id": bm["id"], "volume_ml": 40},
                {"kind": "liquid", "food_id": ga1_prepared["id"], "volume_ml": 20},
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["totals"]["metabolic_formula_ml"] == 20

    # Pumping 120 ml and two diapers.
    resp = c.post(
        f"/v1/babies/{baby_id}/events",
        json={
            "occurred_at": _iso(now - timedelta(hours=2)),
            "type": "pumping", "pumped_ml": 120, "side": "both",
            "duration_minutes": 18,
        },
    )
    assert resp.status_code == 201, resp.text
    for kind in ("both", "pee"):
        assert (
            c.post(
                f"/v1/babies/{baby_id}/events",
                json={
                    "occurred_at": _iso(now - timedelta(minutes=30)),
                    "type": "diaper", "diaper_kind": kind,
                },
            ).status_code
            == 201
        )

    # Set their real volume targets: max 400 breast milk, min 120 GA1.
    resp = c.patch(
        f"/v1/babies/{baby_id}",
        json={
            "targets": {
                "lysine_mg_per_day": 420,
                "volume_targets": [
                    {"category": "breast_milk", "direction": "max", "ml_per_day": 400},
                    {"category": "metabolic_formula", "direction": "min", "ml_per_day": 120},
                ],
            }
        },
    )
    assert resp.status_code == 200, resp.text

    s = c.get(f"/v1/babies/{baby_id}/summary?hours=24").json()
    assert s["pumped_output_ml"] == 120
    assert s["pumping_sessions"] == 1
    assert s["pumped_vs_fed"] == {"pumped_ml": 120, "fed_ml": 40, "net_ml": 80}
    assert s["diapers"] == {"pee": 2, "poop": 1, "changes": 2}

    vt = {(v["category"], v["direction"]): v for v in s["volume_targets"]}
    bm_eval = vt[("breast_milk", "max")]
    assert bm_eval["actual_ml"] == 40 and bm_eval["status"] == "met"
    ga1_eval = vt[("metabolic_formula", "min")]
    assert ga1_eval["actual_ml"] == 20 and ga1_eval["status"] == "under"

    assert "Pumped: 120 ml" in s["summary_text"]
    assert "Diapers: 2 (pee 2 · poop 1)" in s["summary_text"]
    assert "100 to go" in s["summary_text"]  # GA1 min: 20 of 120


def test_event_validation(auth_client):
    c = auth_client
    now = _iso(datetime.now(timezone.utc))
    r = c.post(
        f"/v1/babies/{c.baby_id}/events", json={"occurred_at": now, "type": "pumping"}
    )
    assert r.status_code == 422  # pumped_ml required
    r = c.post(
        f"/v1/babies/{c.baby_id}/events", json={"occurred_at": now, "type": "diaper"}
    )
    assert r.status_code == 422  # diaper_kind required


def test_volume_target_validation(auth_client):
    c = auth_client
    r = c.patch(
        f"/v1/babies/{c.baby_id}",
        json={
            "targets": {
                "volume_targets": [
                    {"category": "breast_milk", "direction": "max", "ml_per_day": 400},
                    {"category": "breast_milk", "direction": "max", "ml_per_day": 300},
                ]
            }
        },
    )
    assert r.status_code == 422  # duplicate (category, direction)
    r = c.patch(
        f"/v1/babies/{c.baby_id}",
        json={
            "targets": {
                "volume_targets": [
                    {"category": "formula", "direction": "min", "ml_per_day": 400},
                    {"category": "formula", "direction": "max", "ml_per_day": 300},
                ]
            }
        },
    )
    assert r.status_code == 422  # min > max


def test_since_local():
    tz = "America/New_York"
    # At 10:00 local, "since 07:00" starts 3h ago today.
    now = datetime(2026, 7, 7, 14, 0, tzinfo=timezone.utc)  # 10:00 EDT
    start = since_local(dtime(7, 0), tz, now)
    assert start == datetime(2026, 7, 7, 11, 0, tzinfo=timezone.utc)
    # At 06:00 local, "since 07:00" means yesterday 07:00.
    now = datetime(2026, 7, 7, 10, 0, tzinfo=timezone.utc)  # 06:00 EDT
    start = since_local(dtime(7, 0), tz, now)
    assert start.astimezone(ZoneInfo(tz)).day == 6


def test_summary_since_endpoint(auth_client):
    c = auth_client
    s = c.get(f"/v1/babies/{c.baby_id}/summary?since_local_time=07:00")
    assert s.status_code == 200
    assert s.json()["window_label"] == "since 7:00 AM"
    r = c.get(f"/v1/babies/{c.baby_id}/summary?since_local_time=07:00&hours=12")
    assert r.status_code == 422


def test_feed_presets_crud(auth_client):
    c = auth_client
    bm = c.foods["Breast milk"]
    ga1 = c.foods["GA1 metabolic formula (prepared)"]

    r = c.post(
        "/v1/feed-presets",
        json={
            "name": "40 BM + 20 GA1",
            "components": [
                {"kind": "liquid", "food_id": bm["id"], "volume_ml": 40},
                {"kind": "liquid", "food_id": ga1["id"], "volume_ml": 20},
            ],
        },
    )
    assert r.status_code == 201, r.text
    preset_id = r.json()["id"]

    r = c.post(
        "/v1/feed-presets",
        json={
            "name": "bad",
            "components": [{"kind": "liquid", "food_id": "nope", "volume_ml": 10}],
        },
    )
    assert r.status_code == 422  # unknown food rejected at save time

    presets = c.get("/v1/feed-presets").json()
    assert [p["name"] for p in presets] == ["40 BM + 20 GA1"]
    assert c.delete(f"/v1/feed-presets/{preset_id}").status_code == 204
    assert c.get("/v1/feed-presets").json() == []


def test_food_sources_seeded(auth_client):
    foods = {f["name"]: f for f in auth_client.get("/v1/foods").json()}
    bm = foods["Breast milk"]
    assert "USDA FoodData Central" in bm["source_name"]
    assert bm["source_url"].startswith("https://fdc.nal.usda.gov")
    assert "GA1 metabolic formula (prepared)" in foods


def test_family_day_start_shifts_day_window(auth_client):
    c = auth_client
    r = c.patch("/v1/family", json={"day_start": "08:00"})
    assert r.status_code == 200 and r.json()["day_start"] == "08:00"
    # The day bucket now starts at 8am local (EDT = UTC-4 in July).
    s = c.get(f"/v1/babies/{c.baby_id}/days/2026-07-07").json()
    assert s["window_from"].startswith("2026-07-07T12:00:00")
    assert c.patch("/v1/family", json={"day_start": "8am"}).status_code == 422
