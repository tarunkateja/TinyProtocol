"""Daily intake series for the trends chart (read-only aggregation)."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/New_York")  # the auth_client family's timezone


def _local_iso(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=TZ).astimezone(timezone.utc).isoformat()


def test_daily_intake_series(auth_client):
    c = auth_client
    baby_id = c.baby_id
    bm = c.foods["Breast milk"]
    ga1 = c.foods["GA1 metabolic formula (prepared)"]

    # June 1: their real 40+20 bottle mix, twice. June 2: nothing. June 3: a latch.
    for hh in (9, 15):
        resp = c.post(
            f"/v1/babies/{baby_id}/feeds",
            json={
                "occurred_at": _local_iso(2026, 6, 1, hh),
                "components": [
                    {"kind": "liquid", "food_id": bm["id"], "volume_ml": 40},
                    {"kind": "liquid", "food_id": ga1["id"], "volume_ml": 20},
                ],
            },
        )
        assert resp.status_code == 201, resp.text
    resp = c.post(
        f"/v1/babies/{baby_id}/feeds",
        json={
            "occurred_at": _local_iso(2026, 6, 3, 12),
            "components": [
                {
                    "kind": "latch",
                    "food_id": bm["id"],
                    "minutes": 10,
                    "rate_ml_per_10min": 25,
                }
            ],
        },
    )
    assert resp.status_code == 201, resp.text

    r = c.get(f"/v1/babies/{baby_id}/analytics/daily?from=2026-06-01&to=2026-06-03")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [d["day"] for d in body["days"]] == [
        "2026-06-01",
        "2026-06-02",
        "2026-06-03",
    ]
    d1, d2, d3 = body["days"]
    assert d1["feed_count"] == 2
    assert d1["breast_milk_ml"] == 80
    assert d1["metabolic_formula_ml"] == 40
    assert d1["total_ml"] == 120
    # Empty days zero-fill so the chart has a bar slot for every day.
    assert d2["feed_count"] == 0 and d2["total_ml"] == 0
    # Latch estimates count as breast milk (10 min × 25 ml/10min).
    assert d3["breast_milk_ml"] == 25 and d3["total_ml"] == 25


def test_daily_intake_respects_day_start(auth_client):
    c = auth_client
    baby_id = c.baby_id
    bm = c.foods["Breast milk"]
    assert c.patch("/v1/family", json={"day_start": "08:00"}).status_code == 200

    # 3 AM on June 5 belongs to the June 4 family-day.
    resp = c.post(
        f"/v1/babies/{baby_id}/feeds",
        json={
            "occurred_at": _local_iso(2026, 6, 5, 3),
            "components": [
                {"kind": "liquid", "food_id": bm["id"], "volume_ml": 30}
            ],
        },
    )
    assert resp.status_code == 201, resp.text

    r = c.get(f"/v1/babies/{baby_id}/analytics/daily?from=2026-06-04&to=2026-06-05")
    days = {d["day"]: d for d in r.json()["days"]}
    assert days["2026-06-04"]["breast_milk_ml"] == 30
    assert days["2026-06-05"]["total_ml"] == 0


def test_daily_intake_validation(auth_client):
    c = auth_client
    baby_id = c.baby_id
    assert (
        c.get(
            f"/v1/babies/{baby_id}/analytics/daily?from=2026-06-03&to=2026-06-01"
        ).status_code
        == 422
    )
    assert (
        c.get(
            f"/v1/babies/{baby_id}/analytics/daily?from=2026-01-01&to=2026-06-01"
        ).status_code
        == 422
    )


def test_weight_history(auth_client):
    c = auth_client
    baby_id = c.baby_id
    assert (
        c.patch(
            f"/v1/babies/{baby_id}",
            json={"date_of_birth": "2026-05-22", "birth_weight_g": 3200},
        ).status_code
        == 200
    )
    # Logged out of order on purpose — the series must come back ascending.
    for day, grams in [(10, 4100), (1, 3600)]:
        resp = c.post(
            f"/v1/babies/{baby_id}/events",
            json={
                "occurred_at": _local_iso(2026, 6, day, 9),
                "type": "weight",
                "weight_g": grams,
            },
        )
        assert resp.status_code == 201, resp.text

    r = c.get(f"/v1/babies/{baby_id}/analytics/weights")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["date_of_birth"] == "2026-05-22"
    assert body["birth_weight_g"] == 3200
    assert [w["weight_g"] for w in body["weights"]] == [3600, 4100]
