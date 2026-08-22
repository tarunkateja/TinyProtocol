"""One-off: pull poop color/consistency from Huckleberry for diapers that were
imported before the sync captured those fields (2026-08-22). Read-only toward
Huckleberry; updates TinyProtocol diaper events in place (hb-linked only).

The fetch rotates the Firebase refresh token — it is persisted back to the
connection item immediately, or the 30-minute sync Lambda's token goes stale.

Usage: .venv/bin/python scripts/backfill_diaper_details.py --family F --baby B --days 60 [--apply]
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("TABLE_NAME", "TinyProtocol-dev")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

from app.repo import families, family_items, keys, logs  # noqa: E402
from app.services import huckleberry as hb  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True)
    ap.add_argument("--baby", required=True)
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    conn = family_items.get(args.family, keys.huckleberry_sk(args.baby))
    assert conn, "no Huckleberry connection"
    tz_name = (families.get_family(args.family) or {}).get("timezone", "UTC")
    now = datetime.now(timezone.utc)
    token, events = await hb.fetch_intervals(conn, tz_name, now - timedelta(days=args.days), now + timedelta(hours=1))
    # Persist the rotated token FIRST — before anything else can fail.
    family_items.update_fields(args.family, keys.huckleberry_sk(args.baby), {"refresh_token": token})
    print(f"fetched {len(events)} events; refresh token persisted")

    diapers = {e["hb_key"]: e for e in events if e["mode"] == "diaper"}
    rows = [i for i in family_items.list_by_prefix(args.family, f"HBIMPORT#{args.baby}#")
            if i.get("mode") == "diaper" and i.get("status") == "imported"]
    print(f"{len(diapers)} diapers upstream, {len(rows)} imported diaper rows")
    changed = skipped = 0
    for row in rows:
        ev = diapers.get(row["hb_key"]) or diapers.get(hb._normalize_hb_key(row["hb_key"]))
        if ev is None:
            continue
        color, cons = ev.get("diaper_color"), ev.get("diaper_consistency")
        if not color and not cons:
            continue
        raw = logs.find_log(row["feed_id"], args.family)
        if raw is None or hb._normalize_hb_key(raw.get("hb_key") or "") != hb._normalize_hb_key(row["hb_key"]):
            skipped += 1
            continue
        if raw.get("diaper_color") == color and raw.get("diaper_consistency") == cons:
            continue
        when = ev["occurred_at"].astimezone(__import__("zoneinfo").ZoneInfo(tz_name)).strftime("%a %m/%d %I:%M%p")
        print(f"  {when} {raw.get('diaper_kind')}: color={color} consistency={cons}")
        changed += 1
        if args.apply:
            raw["diaper_color"], raw["diaper_consistency"] = color, cons
            logs.put_log(raw)
            fields = {k: v for k, v in {"diaper_color": color, "diaper_consistency": cons}.items() if v}
            family_items.update_fields(args.family, keys.hb_import_sk(args.baby, row["hb_key"]), fields)
    print(f"{'APPLIED' if args.apply else 'dry run'}: {changed} events {'updated' if args.apply else 'would update'}, {skipped} skipped (unlinked)")


if __name__ == "__main__":
    asyncio.run(main())
