"""Huckleberry sync: connect, review-first imports, idempotent re-sync.

The two network seams (authenticate_and_get_children / fetch_intervals) are
monkeypatched — no Firebase in tests. `hb_events` is the fake upstream store:
tests mutate it and re-sync to simulate edits/deletes in the Huckleberry app.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services import huckleberry as hb


def _utc(hours_ago: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours_ago)


def _bottle(key, hours_ago, bottle_type="Formula", amount_ml=60.0, notes=None):
    return {
        "hb_key": key,
        "mode": "bottle",
        "occurred_at": _utc(hours_ago),
        "bottle_type": bottle_type,
        "amount_ml": amount_ml,
        "minutes": None,
        "notes": notes,
        "last_updated": 1000.0,
    }


def _breast(key, hours_ago, minutes=15.0):
    return {
        "hb_key": key,
        "mode": "breast",
        "occurred_at": _utc(hours_ago),
        "bottle_type": None,
        "amount_ml": None,
        "minutes": minutes,
        "notes": None,
        "last_updated": 1000.0,
    }


@pytest.fixture()
def hb_events(monkeypatch):
    """Fake Huckleberry backend: a mutable list of normalized events."""
    events: list[dict] = []

    async def fake_auth(email, password, tz_name):
        if password == "wrong":
            raise hb.HuckleberryAuthError("Huckleberry rejected the email/password")
        return {
            "refresh_token": "rt-initial",
            "user_uid": "hb-user-1",
            "children": [{"uid": "child-1", "name": "Tara"}],
        }

    async def fake_fetch(conn, tz_name, start, end):
        assert conn["refresh_token"], "sync must use the stored refresh token"
        window = [e for e in events if start <= e["occurred_at"] < end]
        return "rt-rotated", window

    monkeypatch.setattr(hb, "authenticate_and_get_children", fake_auth)
    monkeypatch.setattr(hb, "fetch_intervals", fake_fetch)
    return events


@pytest.fixture()
def hb_client(auth_client, hb_events):
    """auth_client with a connected Huckleberry account."""
    c = auth_client
    resp = c.post(
        f"/v1/babies/{c.baby_id}/huckleberry/connect",
        json={"email": "mom@example.com", "password": "hunter2"},
    )
    assert resp.status_code == 200, resp.text
    c.hb_events = hb_events
    return c


def _sync(c):
    resp = c.post(f"/v1/babies/{c.baby_id}/huckleberry/sync")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _imports(c, status=None):
    url = f"/v1/babies/{c.baby_id}/huckleberry/imports"
    if status:
        url += f"?status={status}"
    return c.get(url).json()["items"]


# --------------------------------------------------------------------------- #
# Connect
# --------------------------------------------------------------------------- #
def test_connect_stores_token_not_password(hb_client):
    c = hb_client
    status = c.get(f"/v1/babies/{c.baby_id}/huckleberry").json()
    assert status["connected"] is True
    assert status["child_name"] == "Tara"
    assert status["auto_import"] is False

    # Default mapping picked the family's liquid foods by category.
    assert status["mapping"]["Breast Milk"]["food_name"] == "Breast milk"
    assert status["mapping"]["Formula"]["food_name"] == "GA1 metabolic formula (prepared)"

    # Connect immediately runs a first sync, which rotates the token.
    conn = hb.get_connection(_family_id(c), c.baby_id)
    assert conn["refresh_token"] == "rt-rotated"
    assert not any("password" in k for k in conn)


def _family_id(c) -> str:
    return c.get("/v1/family").json()["id"]


def test_connect_bad_password(auth_client, hb_events):
    c = auth_client
    resp = c.post(
        f"/v1/babies/{c.baby_id}/huckleberry/connect",
        json={"email": "mom@example.com", "password": "wrong"},
    )
    assert resp.status_code == 401


def test_connect_multiple_children_requires_choice(auth_client, hb_events, monkeypatch):
    async def two_kids(email, password, tz_name):
        return {
            "refresh_token": "rt-initial",
            "user_uid": "hb-user-1",
            "children": [
                {"uid": "child-1", "name": "Tara"},
                {"uid": "child-2", "name": "Sib"},
            ],
        }

    monkeypatch.setattr(hb, "authenticate_and_get_children", two_kids)
    c = auth_client
    resp = c.post(
        f"/v1/babies/{c.baby_id}/huckleberry/connect",
        json={"email": "mom@example.com", "password": "hunter2"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["needs_child_selection"] is True
    assert {ch["name"] for ch in body["children"]} == {"Tara", "Sib"}
    # Nothing stored until a child is picked.
    assert c.get(f"/v1/babies/{c.baby_id}/huckleberry").json()["connected"] is False

    resp = c.post(
        f"/v1/babies/{c.baby_id}/huckleberry/connect",
        json={"email": "mom@example.com", "password": "hunter2", "child_uid": "child-2"},
    )
    assert resp.status_code == 200
    assert resp.json()["child_name"] == "Sib"


# --------------------------------------------------------------------------- #
# Sync -> pending imports
# --------------------------------------------------------------------------- #
def test_sync_creates_pending_and_is_idempotent(hb_client):
    c = hb_client
    c.hb_events.extend([_bottle("evt-1", 2), _breast("evt-2", 5)])

    result = _sync(c)
    assert result["new_pending"] == 2
    assert result["auto_imported"] == 0

    # Second sync: same events, nothing new.
    result = _sync(c)
    assert result["new_pending"] == 0
    assert result["updated"] == 0

    pending = _imports(c, "pending")
    assert len(pending) == 2
    bottle = next(i for i in pending if i["mode"] == "bottle")
    assert bottle["amount_ml"] == 60.0
    assert bottle["bottle_type"] == "Formula"
    # No feeds were logged yet — review-first.
    feeds = c.get(f"/v1/babies/{c.baby_id}/feeds").json()["items"]
    assert feeds == []

    # Rotated refresh token was persisted.
    conn = hb.get_connection(_family_id(c), c.baby_id)
    assert conn["refresh_token"] == "rt-rotated"
    assert conn["status"] == "ok"


def test_confirm_bottle_creates_feed_with_nutrition(hb_client):
    c = hb_client
    c.hb_events.append(_bottle("evt-1", 2, bottle_type="Formula", amount_ml=60.0))
    _sync(c)

    resp = c.post(f"/v1/babies/{c.baby_id}/huckleberry/imports/evt-1/confirm", json={})
    assert resp.status_code == 200, resp.text
    feed = resp.json()
    ga1 = c.foods["GA1 metabolic formula (prepared)"]
    assert feed["components"][0]["food_id"] == ga1["id"]
    assert feed["totals"]["total_ml"] == 60.0
    assert feed["totals"]["metabolic_formula_ml"] == 60.0
    expected_lysine = round(0.6 * ga1["lysine_mg_per_unit"], 2)
    assert feed["totals"]["lysine_mg"] == expected_lysine

    assert _imports(c, "pending") == []
    assert _imports(c, "imported")[0]["feed_id"] == feed["id"]

    # Confirming twice is a conflict.
    resp = c.post(f"/v1/babies/{c.baby_id}/huckleberry/imports/evt-1/confirm", json={})
    assert resp.status_code == 409


def test_confirm_breast_uses_rate(hb_client):
    c = hb_client
    c.hb_events.append(_breast("evt-b", 3, minutes=20))
    _sync(c)

    resp = c.post(
        f"/v1/babies/{c.baby_id}/huckleberry/imports/evt-b/confirm",
        json={"rate_ml_per_10min": 30},
    )
    assert resp.status_code == 200, resp.text
    feed = resp.json()
    comp = feed["components"][0]
    assert comp["kind"] == "latch"
    assert comp["is_estimated"] is True
    assert comp["effective_ml"] == 60.0  # 20 min * 30 ml/10min

    # The rate they typed becomes the prefill for next time.
    status = c.get(f"/v1/babies/{c.baby_id}/huckleberry").json()
    assert status["latch_rate_ml_per_10min"] == 30


def test_dismiss(hb_client):
    c = hb_client
    c.hb_events.append(_bottle("evt-1", 2))
    _sync(c)
    resp = c.post(f"/v1/babies/{c.baby_id}/huckleberry/imports/evt-1/dismiss")
    assert resp.status_code == 204
    assert _imports(c, "pending") == []
    assert _imports(c, "dismissed")[0]["hb_key"] == "evt-1"

    # A dismissed event is never resurrected by later syncs.
    result = _sync(c)
    assert result["new_pending"] == 0


# --------------------------------------------------------------------------- #
# Auto-import
# --------------------------------------------------------------------------- #
def test_auto_import_bottles_and_breast(hb_client):
    c = hb_client
    resp = c.patch(f"/v1/babies/{c.baby_id}/huckleberry", json={"auto_import": True})
    assert resp.status_code == 200

    c.hb_events.extend([_bottle("evt-1", 2, amount_ml=50.0), _breast("evt-2", 4)])
    result = _sync(c)
    assert result["auto_imported"] == 2
    assert result["new_pending"] == 0

    feeds = c.get(f"/v1/babies/{c.baby_id}/feeds").json()["items"]
    assert len(feeds) == 2
    latch = next(f for f in feeds if f["components"][0]["kind"] == "latch")
    # No sync rate configured -> the baby's default latch rate (25 in conftest),
    # 15 min * 25 ml/10min = 37.5 ml, marked estimated.
    assert latch["components"][0]["effective_ml"] == 37.5
    assert latch["components"][0]["is_estimated"] is True


def test_unmapped_bottle_type_stays_pending_even_on_auto(hb_client):
    c = hb_client
    c.patch(f"/v1/babies/{c.baby_id}/huckleberry", json={"auto_import": True})
    c.hb_events.append(_bottle("evt-1", 2, bottle_type="Goat Milk"))
    result = _sync(c)
    assert result["auto_imported"] == 0
    assert result["new_pending"] == 1


# --------------------------------------------------------------------------- #
# Upstream edits and deletes
# --------------------------------------------------------------------------- #
def test_upstream_edit_updates_pending(hb_client):
    c = hb_client
    c.hb_events.append(_bottle("evt-1", 2, amount_ml=60.0))
    _sync(c)

    c.hb_events[0]["amount_ml"] = 80.0
    result = _sync(c)
    assert result["updated"] == 1
    assert _imports(c, "pending")[0]["amount_ml"] == 80.0


def test_upstream_edit_updates_imported_feed(hb_client):
    c = hb_client
    c.hb_events.append(_bottle("evt-1", 2, amount_ml=60.0))
    _sync(c)
    c.post(f"/v1/babies/{c.baby_id}/huckleberry/imports/evt-1/confirm", json={})

    c.hb_events[0]["amount_ml"] = 75.0
    result = _sync(c)
    assert result["updated"] == 1

    feeds = c.get(f"/v1/babies/{c.baby_id}/feeds").json()["items"]
    assert feeds[0]["totals"]["total_ml"] == 75.0
    assert _imports(c, "imported")[0]["amount_ml"] == 75.0


def test_manually_edited_feed_is_left_alone(hb_client):
    c = hb_client
    c.hb_events.append(_bottle("evt-1", 2, amount_ml=60.0))
    _sync(c)
    feed = c.post(
        f"/v1/babies/{c.baby_id}/huckleberry/imports/evt-1/confirm", json={}
    ).json()

    # Parent corrects the feed by hand — PATCH rebuilds it without hb markers.
    bm = c.foods["Breast milk"]
    resp = c.patch(
        f"/v1/feeds/{feed['id']}",
        json={"components": [{"kind": "liquid", "food_id": bm["id"], "volume_ml": 45}]},
    )
    assert resp.status_code == 200

    c.hb_events[0]["amount_ml"] = 99.0
    result = _sync(c)
    assert result["updated"] == 0  # link broken on purpose

    feeds = c.get(f"/v1/babies/{c.baby_id}/feeds").json()["items"]
    assert feeds[0]["totals"]["total_ml"] == 45.0


def test_upstream_delete_of_pending_removes_it(hb_client):
    c = hb_client
    c.hb_events.append(_bottle("evt-1", 2))
    _sync(c)
    assert len(_imports(c, "pending")) == 1

    c.hb_events.clear()
    result = _sync(c)
    assert result["deleted_upstream"] == 1
    assert _imports(c) == []


def test_upstream_delete_of_imported_flags_for_review(hb_client):
    c = hb_client
    c.hb_events.append(_bottle("evt-1", 2))
    _sync(c)
    feed = c.post(
        f"/v1/babies/{c.baby_id}/huckleberry/imports/evt-1/confirm", json={}
    ).json()

    c.hb_events.clear()
    result = _sync(c)
    assert result["deleted_upstream"] == 1
    flagged = _imports(c, "deleted_upstream")
    assert flagged[0]["feed_id"] == feed["id"]
    # The feed itself is NOT auto-deleted — that's the parent's call.
    feeds = c.get(f"/v1/babies/{c.baby_id}/feeds").json()["items"]
    assert len(feeds) == 1

    # Review flow: delete the feed, then dismiss the flag.
    assert c.delete(f"/v1/feeds/{feed['id']}").status_code == 204
    assert (
        c.post(f"/v1/babies/{c.baby_id}/huckleberry/imports/evt-1/dismiss").status_code
        == 204
    )


# --------------------------------------------------------------------------- #
# Mapping + disconnect
# --------------------------------------------------------------------------- #
def test_remap_bottle_type(hb_client):
    c = hb_client
    bm = c.foods["Breast milk"]
    resp = c.patch(
        f"/v1/babies/{c.baby_id}/huckleberry",
        json={"mapping": {"Formula": bm["id"]}},
    )
    assert resp.status_code == 200
    assert resp.json()["mapping"]["Formula"]["food_name"] == "Breast milk"

    # Powder foods are not valid liquid targets.
    powder = next(
        f for f in c.foods.values() if f["unit_basis"] == "per_scoop"
    )
    resp = c.patch(
        f"/v1/babies/{c.baby_id}/huckleberry",
        json={"mapping": {"Formula": powder["id"]}},
    )
    assert resp.status_code == 422


def test_disconnect_clears_pending_keeps_imported(hb_client):
    c = hb_client
    c.hb_events.extend([_bottle("evt-1", 2), _bottle("evt-2", 4)])
    _sync(c)
    c.post(f"/v1/babies/{c.baby_id}/huckleberry/imports/evt-1/confirm", json={})

    resp = c.delete(f"/v1/babies/{c.baby_id}/huckleberry")
    assert resp.status_code == 204
    assert c.get(f"/v1/babies/{c.baby_id}/huckleberry").json()["connected"] is False
    remaining = _imports(c)
    assert [i["status"] for i in remaining] == ["imported"]

    # Sync now 502s (no connection).
    assert c.post(f"/v1/babies/{c.baby_id}/huckleberry/sync").status_code == 502


# --------------------------------------------------------------------------- #
# Mixed-bottle split mappings ("Other" = 40 BM + 20 GA1)
# --------------------------------------------------------------------------- #
def test_default_mapping_includes_other_split(hb_client):
    c = hb_client
    status = c.get(f"/v1/babies/{c.baby_id}/huckleberry").json()
    split = status["mapping"]["Other"]["split"]
    assert [p["parts"] for p in split] == [40, 20]
    assert split[0]["food_name"] == "Breast milk"
    assert split[1]["food_name"] == "GA1 metabolic formula (prepared)"


def test_confirm_other_bottle_splits_proportionally(hb_client):
    c = hb_client
    # 45 ml of the 40+20 mix -> 30 BM + 15 GA1.
    c.hb_events.append(_bottle("evt-mix", 2, bottle_type="Other", amount_ml=45.0))
    _sync(c)

    resp = c.post(f"/v1/babies/{c.baby_id}/huckleberry/imports/evt-mix/confirm", json={})
    assert resp.status_code == 200, resp.text
    feed = resp.json()
    by_food = {comp["food_name"]: comp["volume_ml"] for comp in feed["components"]}
    assert by_food == {"Breast milk": 30.0, "GA1 metabolic formula (prepared)": 15.0}
    assert feed["totals"]["total_ml"] == 45.0
    assert feed["totals"]["breast_milk_ml"] == 30.0
    assert feed["totals"]["metabolic_formula_ml"] == 15.0


def test_auto_import_split_bottle(hb_client):
    c = hb_client
    c.patch(f"/v1/babies/{c.baby_id}/huckleberry", json={"auto_import": True})
    c.hb_events.append(_bottle("evt-mix", 2, bottle_type="Other", amount_ml=60.0))
    result = _sync(c)
    assert result["auto_imported"] == 1
    feeds = c.get(f"/v1/babies/{c.baby_id}/feeds").json()["items"]
    assert feeds[0]["totals"]["breast_milk_ml"] == 40.0
    assert feeds[0]["totals"]["metabolic_formula_ml"] == 20.0


def test_upstream_edit_scales_split_feed(hb_client):
    c = hb_client
    c.hb_events.append(_bottle("evt-mix", 2, bottle_type="Other", amount_ml=60.0))
    _sync(c)
    c.post(f"/v1/babies/{c.baby_id}/huckleberry/imports/evt-mix/confirm", json={})

    c.hb_events[0]["amount_ml"] = 30.0  # she corrects: only half was taken
    result = _sync(c)
    assert result["updated"] == 1
    feeds = c.get(f"/v1/babies/{c.baby_id}/feeds").json()["items"]
    assert feeds[0]["totals"]["breast_milk_ml"] == 20.0
    assert feeds[0]["totals"]["metabolic_formula_ml"] == 10.0


def test_remap_other_to_custom_split(hb_client):
    c = hb_client
    bm = c.foods["Breast milk"]
    ga1 = c.foods["GA1 metabolic formula (prepared)"]
    resp = c.patch(
        f"/v1/babies/{c.baby_id}/huckleberry",
        json={"mapping": {"Other": [
            {"food_id": bm["id"], "parts": 50},
            {"food_id": ga1["id"], "parts": 25},
        ]}},
    )
    assert resp.status_code == 200
    split = resp.json()["mapping"]["Other"]["split"]
    assert [p["parts"] for p in split] == [50, 25]

    # Powder foods are rejected inside splits too.
    powder = next(f for f in c.foods.values() if f["unit_basis"] == "per_scoop")
    resp = c.patch(
        f"/v1/babies/{c.baby_id}/huckleberry",
        json={"mapping": {"Other": [{"food_id": powder["id"], "parts": 1}]}},
    )
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# Read-only guarantee: writes to Huckleberry are structurally blocked
# --------------------------------------------------------------------------- #
def test_readonly_client_blocks_every_write():
    cls = hb._make_readonly_client_class()
    api = cls.__new__(cls)  # no network setup needed to check the guard
    blocked = [
        name
        for name in dir(cls)
        if name.startswith(hb._HB_WRITE_PREFIXES)
    ]
    # The vendored client does have write methods — they must all be guarded.
    assert "log_bottle" in blocked and "log_sleep" in blocked
    for name in blocked:
        with pytest.raises(RuntimeError, match="read-only"):
            getattr(api, name)()


# --------------------------------------------------------------------------- #
# Diapers, medication, and auto-logged nursing
# --------------------------------------------------------------------------- #
def _diaper(key, hours_ago, kind="poop"):
    return {
        "hb_key": key,
        "mode": "diaper",
        "occurred_at": _utc(hours_ago),
        "diaper_kind": kind,
        "notes": None,
        "last_updated": 1000.0,
    }


def _med(key, hours_ago, name="Levocarnitine", dose_amount=2.5, dose_unit="ml"):
    return {
        "hb_key": key,
        "mode": "medication",
        "occurred_at": _utc(hours_ago),
        "med_name": name,
        "dose_amount": dose_amount,
        "dose_unit": dose_unit,
        "notes": None,
        "last_updated": 1000.0,
    }


def _events_list(c):
    return c.get(f"/v1/babies/{c.baby_id}/events").json()["items"]


def test_diaper_and_med_confirm_create_events(hb_client):
    c = hb_client
    c.hb_events.extend([_diaper("d:1", 2), _med("m:1", 3)])
    result = _sync(c)
    assert result["new_pending"] == 2

    resp = c.post(f"/v1/babies/{c.baby_id}/huckleberry/imports/d:1/confirm", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["type"] == "diaper"
    assert resp.json()["diaper_kind"] == "poop"

    resp = c.post(f"/v1/babies/{c.baby_id}/huckleberry/imports/m:1/confirm", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["med_name"] == "Levocarnitine"
    assert resp.json()["dose_amount"] == 2.5

    types = sorted(e["type"] for e in _events_list(c))
    assert types == ["diaper", "medication"]


def test_auto_import_covers_all_modes(hb_client):
    c = hb_client
    c.patch(f"/v1/babies/{c.baby_id}/huckleberry", json={
        "auto_import": True, "latch_rate_ml_per_10min": 15,
    })
    c.hb_events.extend([
        _bottle("evt-1", 1, bottle_type="Other", amount_ml=60.0),
        _breast("evt-2", 2, minutes=10),
        _diaper("d:1", 3, kind="pee"),
        _med("m:1", 4),
    ])
    result = _sync(c)
    assert result["auto_imported"] == 4
    assert result["new_pending"] == 0

    feeds = c.get(f"/v1/babies/{c.baby_id}/feeds").json()["items"]
    assert len(feeds) == 2
    latch = next(f for f in feeds if f["components"][0]["kind"] == "latch")
    # 10 min at the configured 15 ml/10min -> 15 ml, marked estimated.
    assert latch["components"][0]["effective_ml"] == 15.0
    assert latch["components"][0]["is_estimated"] is True

    events = _events_list(c)
    assert sorted(e["type"] for e in events) == ["diaper", "medication"]


def test_upstream_edit_updates_imported_event(hb_client):
    c = hb_client
    c.patch(f"/v1/babies/{c.baby_id}/huckleberry", json={"auto_import": True})
    c.hb_events.append(_diaper("d:1", 2, kind="pee"))
    _sync(c)

    c.hb_events[0]["diaper_kind"] = "both"  # she corrects it in Huckleberry
    result = _sync(c)
    assert result["updated"] == 1
    events = _events_list(c)
    assert events[0]["diaper_kind"] == "both"


def test_upstream_delete_of_imported_event_flags(hb_client):
    c = hb_client
    c.patch(f"/v1/babies/{c.baby_id}/huckleberry", json={"auto_import": True})
    c.hb_events.append(_med("m:1", 2))
    _sync(c)
    assert len(_events_list(c)) == 1

    c.hb_events.clear()
    result = _sync(c)
    assert result["deleted_upstream"] == 1
    flagged = _imports(c, "deleted_upstream")
    assert flagged[0]["mode"] == "medication"
    # Event still there — parent decides via the review card.
    assert len(_events_list(c)) == 1


# --------------------------------------------------------------------------- #
# Pumping
# --------------------------------------------------------------------------- #
def _pump(key, hours_ago, pumped_ml=55.0, side="both", duration_minutes=20.0):
    return {
        "hb_key": key,
        "mode": "pumping",
        "occurred_at": _utc(hours_ago),
        "pumped_ml": pumped_ml,
        "side": side,
        "duration_minutes": duration_minutes,
        "notes": None,
        "last_updated": 1000.0,
    }


def test_pumping_auto_import_and_edit(hb_client):
    c = hb_client
    c.patch(f"/v1/babies/{c.baby_id}/huckleberry", json={"auto_import": True})
    c.hb_events.append(_pump("p:1", 2))
    result = _sync(c)
    assert result["auto_imported"] == 1

    events = c.get(f"/v1/babies/{c.baby_id}/events").json()["items"]
    assert events[0]["type"] == "pumping"
    assert events[0]["pumped_ml"] == 55.0
    assert events[0]["side"] == "both"
    assert events[0]["duration_minutes"] == 20.0

    # Upstream correction mirrors onto the event.
    c.hb_events[0]["pumped_ml"] = 60.0
    result = _sync(c)
    assert result["updated"] == 1
    events = c.get(f"/v1/babies/{c.baby_id}/events").json()["items"]
    assert events[0]["pumped_ml"] == 60.0


def test_pumping_confirm_when_review_first(hb_client):
    c = hb_client
    c.hb_events.append(_pump("p:1", 3, pumped_ml=40.0, side="left", duration_minutes=None))
    _sync(c)
    resp = c.post(f"/v1/babies/{c.baby_id}/huckleberry/imports/p:1/confirm", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["type"] == "pumping"
    assert resp.json()["pumped_ml"] == 40.0


# --------------------------------------------------------------------------- #
# Firestore container repacking: Huckleberry moves aging standalone docs into
# batched "multi" containers, keeping the original doc id as the entry key.
# Keys minted before 2026-07-17 embedded the container doc id, so every
# repacked event re-imported as new — duplicating each feed. The client now
# keys on the entry key alone; the sync self-heals rows stored under legacy
# container-prefixed keys.
# --------------------------------------------------------------------------- #
def test_normalize_hb_key():
    assert hb._normalize_hb_key("1784-abc") == "1784-abc"
    assert hb._normalize_hb_key("CONT123:1784-abc") == "1784-abc"
    assert hb._normalize_hb_key("d:1784-abc") == "d:1784-abc"
    assert hb._normalize_hb_key("d:CONT123:1784-abc") == "d:1784-abc"
    assert hb._normalize_hb_key("p:CONT123:1784-abc") == "p:1784-abc"
    assert hb._normalize_hb_key("m:CONT123:1784-abc") == "m:1784-abc"


def test_legacy_container_key_heals_instead_of_duplicating(hb_client):
    c = hb_client
    # State as the pre-fix sync left it: import row keyed with the container
    # doc prefix, feed carrying that same legacy hb_key.
    c.hb_events.append(_bottle("CONT123:evt-1", 2, amount_ml=60.0))
    _sync(c)
    resp = c.post(
        f"/v1/babies/{c.baby_id}/huckleberry/imports/CONT123:evt-1/confirm", json={}
    )
    assert resp.status_code == 200, resp.text

    # The fixed client reports the stable entry key from now on.
    c.hb_events[0]["hb_key"] = "evt-1"
    result = _sync(c)
    assert result["new_pending"] == 0
    assert result["auto_imported"] == 0
    assert result["deleted_upstream"] == 0

    imports = _imports(c)
    assert len(imports) == 1
    assert imports[0]["hb_key"] == "evt-1"
    assert imports[0]["status"] == "imported"
    feeds = c.get(f"/v1/babies/{c.baby_id}/feeds").json()["items"]
    assert len(feeds) == 1

    # The healed row is still hb-linked: upstream edits keep mirroring even
    # though the feed still carries the legacy container-prefixed hb_key.
    c.hb_events[0]["amount_ml"] = 75.0
    result = _sync(c)
    assert result["updated"] == 1
    feeds = c.get(f"/v1/babies/{c.baby_id}/feeds").json()["items"]
    assert feeds[0]["totals"]["total_ml"] == 75.0


def test_legacy_container_key_heals_prefixed_modes(hb_client):
    c = hb_client
    c.patch(f"/v1/babies/{c.baby_id}/huckleberry", json={"auto_import": True})
    c.hb_events.append(_diaper("d:CONT9:evt-7", 2))
    result = _sync(c)
    assert result["auto_imported"] == 1

    c.hb_events[0]["hb_key"] = "d:evt-7"
    result = _sync(c)
    assert result["auto_imported"] == 0
    assert result["deleted_upstream"] == 0
    assert len(_events_list(c)) == 1
    assert _imports(c)[0]["hb_key"] == "d:evt-7"


def test_prefix_dup_pair_collision_stays_quiet(hb_client):
    c = hb_client
    c.patch(f"/v1/babies/{c.baby_id}/huckleberry", json={"auto_import": True})
    # Reproduce the damage the bug already did: the same event imported twice
    # (bare key flagged deleted_upstream, prefixed key imported).
    c.hb_events.append(_bottle("evt-1", 2, amount_ml=60.0))
    _sync(c)
    c.hb_events[0]["hb_key"] = "CONT123:evt-1"
    _sync(c)
    assert {i["status"] for i in _imports(c)} == {"deleted_upstream", "imported"}
    feeds = c.get(f"/v1/babies/{c.baby_id}/feeds").json()["items"]
    assert len(feeds) == 2  # the pre-existing damage

    # Post-fix syncs must not compound it: no third import, no third feed.
    c.hb_events[0]["hb_key"] = "evt-1"
    result = _sync(c)
    assert result["auto_imported"] == 0
    assert result["new_pending"] == 0
    assert len(c.get(f"/v1/babies/{c.baby_id}/feeds").json()["items"]) == 2
    assert len(_imports(c)) == 2
