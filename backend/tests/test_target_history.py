"""Targets are effective-dated: editing them must not rewrite past days."""

from datetime import date, datetime, time, timedelta, timezone

from app.models.baby import Baby, Targets
from app.services import target_history
from app.services.tz import effective_day

OLD_TARGETS = {
    "lysine_mg_per_day": 420,
    "natural_protein_g_per_day": 6.0,
    "volume_targets": [
        {"category": "breast_milk", "direction": "max", "ml_per_day": 400},
        {"category": "metabolic_formula", "direction": "min", "ml_per_day": 120},
    ],
}
NEW_TARGETS = {
    "lysine_mg_per_day": 420,
    "natural_protein_g_per_day": 6.0,
    "volume_targets": [
        {"category": "metabolic_formula", "direction": "max", "ml_per_day": 120},
    ],
}


def _family_id(c) -> str:
    resp = c.post(
        "/v1/auth/login",
        json={"email": "dad@example.com", "password": "hunter2hunter2"},
    )
    return resp.json()["user"]["family_id"]


def test_past_days_keep_the_targets_in_effect_then(auth_client):
    c = auth_client
    baby_id = c.baby_id
    today = date.today()
    yesterday = today - timedelta(days=1)

    # The old targets have been in effect since before yesterday; a feed was
    # logged then; today the dietician changed the plan and targets were edited.
    target_history._put_snapshot(
        _family_id(c), baby_id, "0001-01-01", Targets.model_validate(OLD_TARGETS)
    )
    bm = c.foods["Breast milk"]
    resp = c.post(
        f"/v1/babies/{baby_id}/feeds",
        json={
            "occurred_at": (
                datetime.now(timezone.utc) - timedelta(days=1)
            ).isoformat(),
            "components": [{"kind": "liquid", "food_id": bm["id"], "volume_ml": 150}],
        },
    )
    assert resp.status_code == 201, resp.text
    assert c.patch(f"/v1/babies/{baby_id}", json={"targets": NEW_TARGETS}).status_code == 200

    # Yesterday is judged against the OLD volume targets...
    day = c.get(f"/v1/babies/{baby_id}/days/{yesterday.isoformat()}").json()
    vts = {(t["category"], t["direction"]): t for t in day["volume_targets"]}
    assert set(vts) == {("breast_milk", "max"), ("metabolic_formula", "min")}
    assert vts[("breast_milk", "max")]["target_ml"] == 400

    # ...while today uses the new ones.
    day = c.get(f"/v1/babies/{baby_id}/days/{today.isoformat()}").json()
    vts = {(t["category"], t["direction"]): t for t in day["volume_targets"]}
    assert set(vts) == {("metabolic_formula", "max")}
    assert vts[("metabolic_formula", "max")]["target_ml"] == 120


def test_first_change_backfills_a_baseline(auth_client):
    c = auth_client
    baby_id = c.baby_id
    # The registration targets (no volume targets) were never snapshotted;
    # the first edit must preserve them for all earlier days.
    assert c.patch(f"/v1/babies/{baby_id}", json={"targets": NEW_TARGETS}).status_code == 200
    long_ago = c.get(f"/v1/babies/{baby_id}/days/2026-01-01").json()
    assert long_ago["volume_targets"] == []
    assert long_ago["targets"]["lysine_mg_per_day"] == 420


def test_noop_target_update_writes_no_history(auth_client, monkeypatch):
    c = auth_client
    baby = Baby.model_validate(c.get(f"/v1/babies/{c.baby_id}").json())
    assert (
        c.patch(
            f"/v1/babies/{c.baby_id}",
            json={"targets": baby.targets.model_dump(mode="json")},
        ).status_code
        == 200
    )
    from app.repo import family_items

    # The route is the only writer, so an unchanged PATCH must leave no items.
    snaps = family_items.list_by_prefix(_family_id(c), f"TARGETHIST#{c.baby_id}#")
    assert snaps == []


def test_backdated_target_change_and_history_endpoints(auth_client):
    c = auth_client
    baby_id = c.baby_id
    today = date.today()
    two_days_ago = today - timedelta(days=2)

    # "The dietician told us two days ago" — backdate the change.
    r = c.patch(
        f"/v1/babies/{baby_id}",
        json={
            "targets": NEW_TARGETS,
            "targets_effective_from": two_days_ago.isoformat(),
        },
    )
    assert r.status_code == 200, r.text

    # Yesterday already uses the new plan; before the change, the old one.
    day = c.get(
        f"/v1/babies/{baby_id}/days/{(today - timedelta(days=1)).isoformat()}"
    ).json()
    assert [(t["category"], t["direction"]) for t in day["volume_targets"]] == [
        ("metabolic_formula", "max")
    ]
    day = c.get(
        f"/v1/babies/{baby_id}/days/{(today - timedelta(days=3)).isoformat()}"
    ).json()
    assert day["volume_targets"] == []  # registration targets, no volume goals

    # History lists both periods; deleting the backdated one 404s twice.
    hist = c.get(f"/v1/babies/{baby_id}/target-history").json()
    assert [h["effective_date"] for h in hist] == [
        "0001-01-01",
        two_days_ago.isoformat(),
    ]
    assert (
        c.delete(
            f"/v1/babies/{baby_id}/target-history/{two_days_ago.isoformat()}"
        ).status_code
        == 204
    )
    assert (
        c.delete(
            f"/v1/babies/{baby_id}/target-history/{two_days_ago.isoformat()}"
        ).status_code
        == 404
    )


def test_future_effective_date_is_clamped_to_today(auth_client):
    c = auth_client
    baby_id = c.baby_id
    r = c.patch(
        f"/v1/babies/{baby_id}",
        json={
            "targets": NEW_TARGETS,
            "targets_effective_from": (date.today() + timedelta(days=30)).isoformat(),
        },
    )
    assert r.status_code == 200, r.text
    hist = c.get(f"/v1/babies/{baby_id}/target-history").json()
    assert hist[-1]["effective_date"] <= date.today().isoformat()


def test_effective_day_respects_day_start():
    # 3 AM local with an 8 AM day start still belongs to the previous day.
    now = datetime(2026, 7, 10, 8, 0, tzinfo=timezone.utc)  # 3 AM Chicago (CDT)
    assert effective_day(now, "America/Chicago", time(8, 0)) == date(2026, 7, 9)
    assert effective_day(now, "America/Chicago", time.min) == date(2026, 7, 10)
