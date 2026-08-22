"""One-off: seed Tara's real feeding-recipe history from the parents' account
of plan changes (2026-08-21), then switch the Huckleberry "Other" mapping to
"split by recipe". Dry-run by default; --apply writes.

Usage (from backend/, with AWS creds for the dev table):
    .venv/bin/python scripts/seed_recipes.py --family <fid> --baby <bid> [--apply]
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("TABLE_NAME", "TinyProtocol-dev")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

from app.models.recipe import RecipeIn  # noqa: E402
from app.repo import family_items, keys  # noqa: E402
from app.services import recipes as svc  # noqa: E402

CHI = ZoneInfo("America/Chicago")


def chi(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=CHI).astimezone(timezone.utc)


ANAMIX = {"name": "GA-1 Anamix Early Years", "grams": 30}
PROPHREE = {"name": "Pro-Phree", "grams": 20}

RECIPES = [
    RecipeIn(
        label="Original mix (40 + 20)",
        effective_at=chi(2026, 5, 22),
        breast_milk_ml=40, batch_ml=20, feeds_per_day=8,
        source="Lurie metabolic team (initial plan)",
        notes="Prepared Anamix formula; batch recipe from that period not recorded here.",
    ),
    RecipeIn(
        label="Post-vaccination interim (55 + 20)",
        effective_at=chi(2026, 7, 30),
        breast_milk_ml=55, batch_ml=20, feeds_per_day=8,
        batch_final_volume_ml=160,
        notes="Interim plan after the 7/28 vaccines; batch was ~23 g powder to 160 ml. "
              "Per-day plans Jul 27-31 preceded this — confirm/edit dates if needed.",
    ),
    RecipeIn(
        label="Dietician plan (55 + 25 = 80)",
        effective_at=chi(2026, 8, 4),
        breast_milk_ml=55, batch_ml=25, feeds_per_day=8,
        powders=[ANAMIX, PROPHREE], batch_final_volume_ml=310,
        source="Madison Smith (dietician) via MyChart, Aug 4",
        notes="Weight gain low → 80 ml feeds, top-offs from the same batch, work toward 90 ml.",
    ),
    RecipeIn(
        label="Concentrated batch (→ 280 ml)",
        effective_at=chi(2026, 8, 17),
        breast_milk_ml=55, batch_ml=25, feeds_per_day=8,
        powders=[ANAMIX, PROPHREE], batch_final_volume_ml=280,
        source="Dietician, ~Aug 17",
        notes="Same powders, less water; feed composition unchanged.",
    ),
    RecipeIn(
        label="85 ml feeds (55 + 30)",
        effective_at=chi(2026, 8, 20, 22, 0),
        breast_milk_ml=55, batch_ml=30, feeds_per_day=8,
        powders=[ANAMIX, PROPHREE], batch_final_volume_ml=280,
        source="Dietician — increase to 85 then 90 ml",
        notes="Bottles prepared as 85; discard what she leaves. Next step 55 + 35 = 90. "
              "Hospital (8/19) recipe change incl. Glutarex-1 pending the team's written plan.",
    ),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True)
    ap.add_argument("--baby", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    existing = svc.list_recipes(args.family, args.baby)
    print(f"existing recipes: {len(existing)}")
    for r in RECIPES:
        local = r.effective_at.astimezone(CHI).strftime("%a %Y-%m-%d %H:%M")
        dup = any(e.effective_at == r.effective_at for e in existing)
        print(f"  {'SKIP (exists)' if dup else 'ADD'}  {local}  {r.label}: "
              f"{r.breast_milk_ml:g}+{r.batch_ml:g}={r.breast_milk_ml + r.batch_ml:g} ml"
              f"{'  batch ' + str(r.batch_final_volume_ml) + ' ml' if r.batch_final_volume_ml else ''}")
        if args.apply and not dup:
            svc.create_recipe(args.family, args.baby, r)

    conn = family_items.get(args.family, keys.huckleberry_sk(args.baby))
    if conn is None:
        print("no Huckleberry connection — mapping untouched")
        return
    mapping = dict(conn.get("mapping") or {})
    print(f"HB 'Other' mapping now: {mapping.get('Other')}")
    if isinstance(mapping.get("Other"), dict) and mapping["Other"].get("mode") == "recipe":
        print("  already per-recipe")
    else:
        print("  -> {'mode': 'recipe'}")
        if args.apply:
            mapping["Other"] = {"mode": "recipe"}
            family_items.update_fields(args.family, keys.huckleberry_sk(args.baby), {"mapping": mapping})
    print("APPLIED" if args.apply else "dry run — re-run with --apply")


if __name__ == "__main__":
    main()
