"""One-off v2 backfill for families that registered before this deploy:
- add source_name/source_url to seeded foods (matched by name, only if missing)
- insert the new "GA1 metabolic formula (prepared)" food where absent

Run from backend/: TABLE_NAME=TinyProtocol-dev .venv/bin/python scripts/backfill_v2.py
"""

from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr
from ulid import ULID

from app.config import settings
from app.models.food import Food
from app.repo import keys
from app.repo.client import to_item
from app.services.seed import DEFAULT_FOODS

table = boto3.resource("dynamodb").Table(settings.table_name)
seed_by_name = {f.name: f for f in DEFAULT_FOODS}

items, resp = [], {}
while True:
    kwargs = {"FilterExpression": Attr("SK").begins_with("FOOD#")}
    if resp.get("LastEvaluatedKey"):
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    resp = table.scan(**kwargs)
    items.extend(resp["Items"])
    if "LastEvaluatedKey" not in resp:
        break

families: dict[str, set[str]] = {}
updated = 0
for item in items:
    families.setdefault(item["PK"], set()).add(item["name"])
    seed = seed_by_name.get(item["name"])
    if seed and seed.source_name and not item.get("source_name"):
        item["source_name"] = seed.source_name
        if seed.source_url:
            item["source_url"] = seed.source_url
        item["description"] = seed.description
        table.put_item(Item=item)
        updated += 1

prepared = seed_by_name["GA1 metabolic formula (prepared)"]
inserted = 0
for family_pk, names in families.items():
    if prepared.name in names:
        continue
    food = Food(
        id=str(ULID()), created_at=datetime.now(timezone.utc), **prepared.model_dump()
    )
    table.put_item(
        Item=to_item(
            {
                "PK": family_pk,
                "SK": keys.food_sk(food.id),
                **food.model_dump(mode="json"),
            }
        )
    )
    inserted += 1

print(f"families seen: {len(families)}, foods updated: {updated}, prepared-GA1 inserted: {inserted}")
