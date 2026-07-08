"""Generic store for family-scoped entities: babies, foods, med presets.

All live under PK=FAMILY#<fid> with an SK prefix per entity type; callers pass
the SK via the builders in repo.keys.
"""

from boto3.dynamodb.conditions import Key

from app.repo import keys
from app.repo.client import from_item, get_table, to_item


def put(family_id: str, sk: str, data: dict) -> None:
    item = {"PK": keys.family_pk(family_id), "SK": sk, **data}
    get_table().put_item(Item=to_item(item))


def get(family_id: str, sk: str) -> dict | None:
    resp = get_table().get_item(Key={"PK": keys.family_pk(family_id), "SK": sk})
    item = resp.get("Item")
    return from_item(item) if item else None


def delete(family_id: str, sk: str) -> None:
    get_table().delete_item(Key={"PK": keys.family_pk(family_id), "SK": sk})


def list_by_prefix(family_id: str, sk_prefix: str) -> list[dict]:
    resp = get_table().query(
        KeyConditionExpression=Key("PK").eq(keys.family_pk(family_id))
        & Key("SK").begins_with(sk_prefix)
    )
    return [from_item(i) for i in resp["Items"]]
