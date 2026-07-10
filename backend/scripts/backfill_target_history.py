"""One-off: backfill target history for Tara after the 2026-07-10 plan change.

The dietician changed the plan (labs improved): max 120 ml/day GA1 formula,
remaining intake as breast milk. The targets were edited in the app before
effective-dated history existed, so past days were showing the new targets.
This writes the previous plan (max 400 breast milk / min 120 GA1 formula) as
the baseline and the current plan as effective 2026-07-10.

Run: .venv/bin/python scripts/backfill_target_history.py [--apply]
"""

import sys

import boto3

TABLE = "TinyProtocol-dev"
FAMILY_PK = "FAMILY#01KWZKR4DHJWDK8WER3VX9K2KX"
BABY_ID = "01KWZKR62PTV1BD2XB2GB0323K"
NEW_EFFECTIVE = "2026-07-10"

OLD_TARGETS = {
    "lysine_mg_per_day": None,
    "natural_protein_g_per_day": None,
    "lysine_mg_per_kg": None,
    "natural_protein_g_per_kg": None,
    "volume_targets": [
        {"category": "breast_milk", "direction": "max", "ml_per_day": 400},
        {"category": "metabolic_formula", "direction": "min", "ml_per_day": 120},
    ],
}


def main(apply: bool) -> None:
    from datetime import datetime, timezone

    table = boto3.resource("dynamodb", region_name="us-east-1").Table(TABLE)

    baby = table.get_item(Key={"PK": FAMILY_PK, "SK": f"BABY#{BABY_ID}"}).get("Item")
    assert baby and baby["name"] == "Tara", "expected Tara's baby item"
    current_targets = baby["targets"]
    print("current (new) targets:", current_targets)

    existing = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("PK").eq(FAMILY_PK)
        & boto3.dynamodb.conditions.Key("SK").begins_with(f"TARGETHIST#{BABY_ID}#")
    )["Items"]
    if existing:
        print(f"history already exists ({len(existing)} snapshots) — aborting")
        return

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    snapshots = [
        ("0001-01-01", _clean(OLD_TARGETS)),
        (NEW_EFFECTIVE, current_targets),
    ]
    for effective_date, targets in snapshots:
        item = {
            "PK": FAMILY_PK,
            "SK": f"TARGETHIST#{BABY_ID}#{effective_date}",
            "baby_id": BABY_ID,
            "effective_date": effective_date,
            "targets": targets,
            "recorded_at": now,
        }
        print(("WRITE " if apply else "DRY-RUN ") + item["SK"], "->", targets)
        if apply:
            table.put_item(Item=item)
    print("done" if apply else "dry run only — rerun with --apply")


def _clean(targets: dict) -> dict:
    """Match Targets.model_dump(mode='json') shape: keep None fields out the
    way the app's put path stores them (to_item strips None)."""
    from decimal import Decimal

    out = {}
    for k, v in targets.items():
        if v is None:
            continue
        if isinstance(v, list):
            out[k] = [
                {kk: Decimal(str(vv)) if isinstance(vv, (int, float)) else vv
                 for kk, vv in t.items()}
                for t in v
            ]
        else:
            out[k] = Decimal(str(v)) if isinstance(v, (int, float)) else v
    return out


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
