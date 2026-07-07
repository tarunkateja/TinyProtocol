"""End-to-end happy path through the API against a moto-mocked table."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def test_full_family_flow(auth_client):
    c = auth_client
    baby_id = c.baby_id
    now = datetime.now(timezone.utc)

    bm = c.foods["Breast milk"]
    metabolic = c.foods["GA1 metabolic formula (powder)"]

    # --- Mixed bottle: 60ml breast milk + 1 scoop metabolic formula ---
    resp = c.post(
        f"/v1/babies/{baby_id}/feeds",
        json={
            "occurred_at": _iso(now - timedelta(hours=3)),
            "components": [
                {"kind": "liquid", "food_id": bm["id"], "volume_ml": 60},
                {"kind": "powder", "food_id": metabolic["id"], "scoops": 1},
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    mixed = resp.json()
    assert mixed["totals"]["total_ml"] == 60
    assert mixed["totals"]["lysine_mg"] == 42
    assert mixed["totals"]["metabolic_formula_scoops"] == 1

    # --- Latch feed: 20 min @ 25 ml/10min -> 50 ml estimated ---
    resp = c.post(
        f"/v1/babies/{baby_id}/feeds",
        json={
            "occurred_at": _iso(now - timedelta(hours=2)),
            "components": [
                {
                    "kind": "latch", "food_id": bm["id"],
                    "minutes": 20, "rate_ml_per_10min": 25,
                }
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    latch = resp.json()
    assert latch["totals"]["total_ml"] == 50
    assert latch["components"][0]["is_estimated"] is True

    # --- Levocarnitine + a large spit-up ---
    resp = c.post(
        f"/v1/babies/{baby_id}/events",
        json={
            "occurred_at": _iso(now - timedelta(hours=2, minutes=30)),
            "type": "medication", "med_name": "Levocarnitine",
            "dose_amount": 5, "dose_unit": "ml",
        },
    )
    assert resp.status_code == 201, resp.text
    resp = c.post(
        f"/v1/babies/{baby_id}/events",
        json={
            "occurred_at": _iso(now - timedelta(hours=1)),
            "type": "spit_up", "severity": "large",
            "related_feed_id": latch["id"],
        },
    )
    assert resp.status_code == 201, resp.text

    # --- Timeline: 4 entries, newest first, feeds+events interleaved ---
    timeline = c.get(f"/v1/babies/{baby_id}/timeline").json()
    assert [i["item_type"] for i in timeline["items"]] == [
        "EVENT", "FEED", "EVENT", "FEED"
    ]

    # --- 24h summary math ---
    s = c.get(f"/v1/babies/{baby_id}/summary?hours=24").json()
    assert s["feed_count"] == 2
    assert s["total_ml"] == 110
    assert s["breast_milk"]["pumped_ml"] == 60
    assert s["breast_milk"]["latch_estimated_ml"] == 50
    assert s["natural_protein_g"] == 1.1
    assert s["lysine_mg"] == 77  # 42 + 35
    assert s["pct_of_lysine_target"] == round(100 * 77 / 420, 1)
    assert len(s["meds"]) == 1 and s["meds"][0]["med_name"] == "Levocarnitine"
    assert len(s["spit_ups"]) == 1
    assert "Lysine: 77 mg of 420 mg target" in s["summary_text"]

    # --- Day summary buckets by the family's timezone ---
    local_today = now.astimezone(ZoneInfo("America/New_York")).date()
    # All logs are 1-3h old; some may fall on yesterday local time — just
    # check the endpoint works and reports the day.
    d = c.get(f"/v1/babies/{baby_id}/days/{local_today}").json()
    assert d["day"] == str(local_today)

    # --- Edit the mixed feed's time (SK move) — nothing lost or duplicated ---
    resp = c.patch(
        f"/v1/feeds/{mixed['id']}",
        json={"occurred_at": _iso(now - timedelta(hours=5))},
    )
    assert resp.status_code == 200, resp.text
    feeds = c.get(f"/v1/babies/{baby_id}/feeds").json()["items"]
    assert len(feeds) == 2
    assert feeds[-1]["id"] == mixed["id"]  # now the oldest
    assert c.get(f"/v1/feeds/{mixed['id']}").json()["totals"]["total_ml"] == 60

    # --- Edit components — nutrition recomputed ---
    resp = c.patch(
        f"/v1/feeds/{mixed['id']}",
        json={
            "components": [
                {"kind": "liquid", "food_id": bm["id"], "volume_ml": 100},
            ]
        },
    )
    assert resp.json()["totals"]["lysine_mg"] == 70

    # --- Delete the spit-up event ---
    event_id = timeline["items"][0]["id"]
    assert c.delete(f"/v1/events/{event_id}").status_code == 204
    timeline = c.get(f"/v1/babies/{baby_id}/timeline").json()
    assert len(timeline["items"]) == 3


def test_invite_and_second_parent(auth_client):
    c = auth_client
    invite = c.post("/v1/auth/invites").json()

    # The wife joins with the code (fresh client without the dad's token).
    resp = c.post(
        "/v1/auth/join",
        json={
            "email": "mom@example.com", "password": "hunter2hunter2",
            "name": "Mom", "invite_code": invite["code"],
        },
        headers={"Authorization": ""},
    )
    assert resp.status_code == 201, resp.text
    mom_token = resp.json()["access_token"]

    # She sees the same baby and family.
    resp = c.get("/v1/babies", headers={"Authorization": f"Bearer {mom_token}"})
    assert [b["id"] for b in resp.json()] == [c.baby_id]
    me = c.get("/v1/me", headers={"Authorization": f"Bearer {mom_token}"}).json()
    assert len(me["family"]["members"]) == 2

    # The code is single-use.
    resp = c.post(
        "/v1/auth/join",
        json={
            "email": "other@example.com", "password": "hunter2hunter2",
            "name": "X", "invite_code": invite["code"],
        },
        headers={"Authorization": ""},
    )
    assert resp.status_code == 400


def test_auth_required_and_family_isolation(client):
    assert client.get("/v1/babies").status_code == 401

    # Two separate families can't see each other's babies.
    a = client.post(
        "/v1/auth/register",
        json={
            "email": "a@example.com", "password": "hunter2hunter2", "name": "A",
            "baby": {"name": "BabyA"},
        },
    ).json()
    b = client.post(
        "/v1/auth/register",
        json={"email": "b@example.com", "password": "hunter2hunter2", "name": "B"},
    ).json()

    babies_a = client.get(
        "/v1/babies", headers={"Authorization": f"Bearer {a['access_token']}"}
    ).json()
    resp = client.get(
        f"/v1/babies/{babies_a[0]['id']}",
        headers={"Authorization": f"Bearer {b['access_token']}"},
    )
    assert resp.status_code == 404
