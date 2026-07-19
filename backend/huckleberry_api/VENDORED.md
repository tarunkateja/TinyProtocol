# Vendored: huckleberry-api 0.4.3

Source: https://github.com/Woyken/py-huckleberry-api (MIT), `src/huckleberry_api` at v0.4.3.

Vendored because PyPI declares `requires-python >=3.14` and our Lambda runtime is
python3.12. Local changes, kept deliberately minimal:

1. `api.py` — parenthesized a multi-exception `except` clause (PEP 758 syntax is
   3.14-only) in `_raise_for_status_with_details`.
2. `api.py` — added `_list_intervals_with_ids` + `list_feed_intervals_with_ids`,
   `list_diaper_intervals_with_ids`, `list_health_entries_with_ids` (returns Firestore doc ids so
   TinyProtocol's sync can dedup idempotently; upstream discards them). For
   entries inside "multi" container docs the key is the entry key ALONE, never
   the container doc id: Huckleberry repacks aging standalone docs into
   containers (keeping the doc id as the entry key), so a container-qualified
   key changes on repack and duplicates every migrated event. Unlike
   upstream, it validates each interval individually and skips malformed rows
   (real accounts contain e.g. bottles saved without an amount) instead of
   failing the whole fetch.

When upgrading, re-apply both changes (or drop this vendor copy entirely once we
run on Python >= 3.14 and upstream exposes interval ids).
