"""Poop/constipation analytics: per-day counts, gaps between poops, time since
the last one, and Huckleberry color/consistency carried onto events."""

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.models.baby import Baby
from app.services.assistant import _run_tool
from app.services.huckleberry import _normalize_diaper
from tests.test_huckleberry import _family_id, _imports, _sync, hb_client, hb_events  # noqa: F401

TZ = ZoneInfo("America/New_York")


def _local(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=TZ).astimezone(timezone.utc)


def _diaper(c, at, kind, **extra):
    resp = c.post(
        f"/v1/babies/{c.baby_id}/events",
        json={"type": "diaper", "occurred_at": at.isoformat(), "diaper_kind": kind, **extra},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_diaper_series_counts_gaps_and_details(auth_client):
    c = auth_client
    # A poop before the range (Jun 1) so the first in-range gap is real.
    _diaper(c, _local(2026, 6, 1, 20), "poop")
    _diaper(c, _local(2026, 6, 3, 8), "pee")
    _diaper(c, _local(2026, 6, 3, 9), "both", diaper_consistency="hard", note="small pebbles")
    _diaper(c, _local(2026, 6, 3, 21), "poop", diaper_color="green", diaper_consistency="loose")
    _diaper(c, _local(2026, 6, 5, 9), "pee")
    _diaper(c, _local(2026, 6, 8, 9), "poop")  # 2d12h gap

    resp = c.get(
        f"/v1/babies/{c.baby_id}/analytics/diapers", params={"from": "2026-06-03", "to": "2026-06-08"}
    )
    assert resp.status_code == 200, resp.text
    s = resp.json()
    by_day = {d["day"]: d for d in s["days"]}
    assert len(s["days"]) == 6
    assert by_day["2026-06-03"] == {"day": "2026-06-03", "changes": 3, "pee": 2, "poop": 2}
    assert by_day["2026-06-04"]["changes"] == 0
    assert by_day["2026-06-08"]["poop"] == 1

    gaps = [(p["gap_hours"], p["consistency"], p["color"], p["note"]) for p in s["poops"]]
    assert gaps == [
        (37.0, "hard", None, "small pebbles"),  # Jun 1 20:00 -> Jun 3 09:00
        (12.0, "loose", "green", None),
        (108.0, None, None, None),  # Jun 3 21:00 -> Jun 8 09:00
    ]
    assert s["longest_gap_hours"] == 108.0
    assert s["longest_gap_ended_at"].startswith("2026-06-08")
    assert s["avg_gap_hours"] == round((37 + 12 + 108) / 3, 1)
    assert s["last_poop_at"].startswith("2026-06-08")
    assert s["hours_since_last_poop"] > 24 * 30  # test runs long after June 2026


def test_diaper_series_range_guard(auth_client):
    c = auth_client
    assert c.get(
        f"/v1/babies/{c.baby_id}/analytics/diapers", params={"from": "2026-06-09", "to": "2026-06-08"}
    ).status_code == 422


def test_assistant_poop_tool(auth_client):
    c = auth_client
    now = datetime.now(timezone.utc)
    _diaper(c, now - timedelta(days=4, hours=2), "poop", diaper_consistency="hard")
    _diaper(c, now - timedelta(hours=26), "poop", note="big one")
    baby = Baby.model_validate(c.get(f"/v1/babies/{c.baby_id}").json())
    out = json.loads(_run_tool("get_poop_history", {"days": 7}, baby, "America/New_York", family_id=_family_id(c)))
    assert out["poops_in_range"] == 2
    assert out["poops"][0]["consistency"] == "hard"
    assert out["poops"][1]["since_previous_poop"] == "3d 0h"
    assert out["average_gap_between_poops_in_range"] == "3d 0h"
    assert out["time_since_last_poop"] in ("1d 2h", "1d 3h")
    assert out["poops"][1]["note"] == "big one"


class _Entry:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_huckleberry_diaper_details_flow_onto_events(hb_client):
    c = hb_client
    norm = _normalize_diaper("d:k1", _Entry(
        mode="poo", start=1_700_000_000, lastUpdated=1.0, notes="after feed",
        color="green", consistency="hard", isPotty=None,
    ))
    assert norm["diaper_color"] == "green" and norm["diaper_consistency"] == "hard"

    c.patch(f"/v1/babies/{c.baby_id}/huckleberry", json={"auto_import": True})
    c.hb_events.append({
        "hb_key": "d:p1", "mode": "diaper", "occurred_at": datetime.now(timezone.utc) - timedelta(hours=3),
        "diaper_kind": "poop", "diaper_color": "yellow", "diaper_consistency": "loose",
        "notes": None, "last_updated": 1000.0,
    })
    assert _sync(c)["auto_imported"] == 1
    imp = _imports(c, "imported")[0]
    ev = c.get(f"/v1/events/{imp['feed_id']}").json()
    assert (ev["diaper_color"], ev["diaper_consistency"]) == ("yellow", "loose")

    # Upstream edit of the consistency mirrors onto the event.
    c.hb_events[0]["diaper_consistency"] = "hard"
    c.hb_events[0]["last_updated"] = 2000.0
    assert _sync(c)["updated"] == 1
    ev = c.get(f"/v1/events/{imp['feed_id']}").json()
    assert ev["diaper_consistency"] == "hard"
