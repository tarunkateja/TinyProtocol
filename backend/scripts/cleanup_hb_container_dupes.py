"""One-off: remove feeds/events duplicated by Huckleberry container repacking.

Huckleberry repacks aging standalone Firestore docs into batched "multi"
container docs, keeping the original doc id as the entry key. Pre-2026-07-17
sync keys embedded the container doc id, so every repacked event re-imported
under a new key: the sync created a second feed/event and flagged the old
import deleted_upstream (whose feed is deliberately kept for review).

This deletes, for each (deleted_upstream, imported) pair sharing the same
normalized key, the deleted_upstream row's feed/event and the row itself.
The imported row and its feed survive; the next post-fix sync rewrites its
key to normalized form.

Run: .venv/bin/python scripts/cleanup_hb_container_dupes.py [--apply]
"""

import os
import sys
from collections import defaultdict

os.environ.setdefault("TABLE_NAME", "TinyProtocol-dev")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.repo import family_items, logs  # noqa: E402
from app.services.huckleberry import _normalize_hb_key  # noqa: E402

APPLY = "--apply" in sys.argv


def main() -> None:
    imports = family_items.scan_sk_prefix("HBIMPORT#")
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for item in imports:
        norm = _normalize_hb_key(item["hb_key"])
        groups[(item["PK"], norm)].append(item)

    pairs = 0
    unmatched_flagged = 0
    for (pk, norm), rows in sorted(groups.items()):
        if len(rows) == 1:
            if rows[0]["status"] == "deleted_upstream":
                unmatched_flagged += 1
                print(f"KEEP  (no twin, needs human review): {rows[0]['hb_key']} "
                      f"{rows[0].get('occurred_at')} {rows[0].get('mode')}")
            continue
        statuses = {r["status"] for r in rows}
        if len(rows) == 2 and statuses == {"imported", "deleted_upstream"}:
            # Repacked while imported: the old row was flagged deleted_upstream
            # (its feed kept) and the new key re-imported a twin. Keep the
            # re-import, drop the flagged row and its now-duplicate feed.
            keep = next(r for r in rows if r["status"] == "imported")
            drop = next(r for r in rows if r["status"] == "deleted_upstream")
        elif len(rows) == 2 and statuses == {"imported", "dismissed"}:
            # Repacked after the parent dismissed it (transition-era double
            # logging): auto-import logged it anyway under the new key. The
            # parent said no — drop the re-import and its feed, keep dismissed.
            keep = next(r for r in rows if r["status"] == "dismissed")
            drop = next(r for r in rows if r["status"] == "imported")
            if drop["hb_key"] == _normalize_hb_key(drop["hb_key"]):
                print(f"SKIP  (imported row not legacy-keyed): {pk} {norm}")
                continue
        else:
            print(f"SKIP  (unexpected group {statuses}): {pk} {norm}")
            continue
        if keep.get("occurred_at") != drop.get("occurred_at") or keep.get("mode") != drop.get("mode"):
            print(f"SKIP  (pair mismatch): {pk} {norm} "
                  f"{drop.get('occurred_at')}/{drop.get('mode')} vs "
                  f"{keep.get('occurred_at')}/{keep.get('mode')}")
            continue

        family_id = pk.split("#", 1)[1]
        pairs += 1
        label = f"{drop.get('mode')} {drop.get('occurred_at')} ml={drop.get('amount_ml')}"
        feed_id = drop.get("feed_id")
        if feed_id:
            raw = logs.find_log(feed_id, family_id)
            if raw is not None and raw.get("hb_key") != drop["hb_key"]:
                # Parent manually edited this feed (edits strip the hb link) —
                # deleting it would lose their correction. Human decides.
                print(f"SKIP  (manually edited feed {feed_id}): {label}")
                pairs -= 1
                continue
            if raw is None:
                print(f"PAIR  {label}: dup log {feed_id} already gone")
            elif APPLY:
                logs.delete_log(raw["PK"], raw["SK"])
                print(f"PAIR  {label}: deleted dup log {feed_id}")
            else:
                print(f"PAIR  {label}: would delete dup log {feed_id} ({raw['SK']})")
        else:
            print(f"PAIR  {label}: no feed on deleted_upstream row")
        if APPLY:
            family_items.delete(family_id, drop["SK"])
            print(f"      removed import row {drop['hb_key']}")
        else:
            print(f"      would remove import row {drop['hb_key']}")

    print(f"\n{pairs} duplicate pairs, {unmatched_flagged} unmatched deleted_upstream rows"
          f" ({'APPLIED' if APPLY else 'dry run — pass --apply'})")


if __name__ == "__main__":
    main()
