"""One-off: re-estimate historical latch feeds from 20 -> 15 ml/10min.

Only touches latch components that are ESTIMATED (not weighed) AND still at
the old default rate of 20 — deliberate custom rates and measured feeds are
left alone. Nutrition snapshots scale linearly with effective ml (same food,
per-100ml), so totals are adjusted by exact deltas. Also sets every baby's
default_latch_rate_ml_per_10min from 20 to 15.

Run: TABLE_NAME=TinyProtocol-dev .venv/bin/python scripts/relatch_15.py
"""

import boto3
from boto3.dynamodb.conditions import Attr
from app.config import settings
from app.repo.client import from_item, to_item

OLD, NEW = 20.0, 15.0
table = boto3.resource("dynamodb").Table(settings.table_name)


def scan_all(filter_expr):
    items, resp = [], {}
    while True:
        kwargs = {"FilterExpression": filter_expr}
        if resp.get("LastEvaluatedKey"):
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        resp = table.scan(**kwargs)
        items.extend(resp["Items"])
        if "LastEvaluatedKey" not in resp:
            return items


feeds = scan_all(Attr("item_type").eq("FEED"))
updated = skipped_custom = skipped_weighed = 0
for raw in feeds:
    item = from_item(raw)
    changed = False
    for comp in item.get("components", []):
        if comp.get("kind") != "latch":
            continue
        if not comp.get("is_estimated"):
            skipped_weighed += 1
            continue
        if float(comp.get("rate_ml_per_10min", 0)) != OLD:
            skipped_custom += 1
            continue
        scale = NEW / OLD
        old_ml = float(comp["effective_ml"])
        new_ml = round(old_ml * scale, 1)
        d_ml = round(new_ml - old_ml, 1)
        d_p = round(float(comp["natural_protein_g"]) * (scale - 1), 3)
        d_l = round(float(comp["lysine_mg"]) * (scale - 1), 2)

        comp["rate_ml_per_10min"] = NEW
        comp["effective_ml"] = new_ml
        comp["natural_protein_g"] = round(float(comp["natural_protein_g"]) + d_p, 3)
        comp["lysine_mg"] = round(float(comp["lysine_mg"]) + d_l, 2)

        t = item["totals"]
        t["total_ml"] = round(float(t["total_ml"]) + d_ml, 1)
        t["breast_milk_ml"] = round(float(t["breast_milk_ml"]) + d_ml, 1)
        t["natural_protein_g"] = round(float(t["natural_protein_g"]) + d_p, 3)
        t["lysine_mg"] = round(float(t["lysine_mg"]) + d_l, 2)
        changed = True
    if changed:
        table.put_item(Item=to_item(item))
        updated += 1

babies = scan_all(Attr("SK").begins_with("BABY#"))
baby_updates = 0
for raw in babies:
    item = from_item(raw)
    if float(item.get("default_latch_rate_ml_per_10min", 0)) == OLD:
        item["default_latch_rate_ml_per_10min"] = NEW
        table.put_item(Item=to_item(item))
        baby_updates += 1

print(
    f"feeds updated: {updated} · skipped (weighed): {skipped_weighed} · "
    f"skipped (custom rate): {skipped_custom} · baby defaults updated: {baby_updates}"
)
