"""Feeds + events: the per-baby timeline (SK = LOG#<utc-iso>#<TYPE>#<id>)."""

import base64
import json

from boto3.dynamodb.conditions import Key

from app.repo import keys
from app.repo.client import from_item, get_client, get_table, to_item
from app.config import settings


def put_log(item: dict) -> None:
    get_table().put_item(Item=to_item(item))


def find_log(log_id: str, family_id: str) -> dict | None:
    """Resolve a feed/event by id via GSI1, scoped to the caller's family."""
    resp = get_table().query(
        IndexName=keys.GSI1_NAME,
        KeyConditionExpression=Key("GSI1PK").eq(keys.gsi1_log_pk(log_id)),
    )
    items = resp.get("Items", [])
    if not items:
        return None
    item = from_item(items[0])
    if item.get("family_id") != family_id:
        return None
    return item


def delete_log(pk: str, sk: str) -> None:
    get_table().delete_item(Key={"PK": pk, "SK": sk})


def replace_log(old_pk: str, old_sk: str, new_item: dict) -> None:
    """Overwrite in place, or transactionally move when the key changed
    (a feed's time is part of its SK)."""
    if new_item["PK"] == old_pk and new_item["SK"] == old_sk:
        put_log(new_item)
        return
    # The resource-level client auto-serializes plain Python values (boto3's
    # document-type injector) — do NOT pass pre-serialized AttributeValues.
    get_client().transact_write_items(
        TransactItems=[
            {
                "Delete": {
                    "TableName": settings.table_name,
                    "Key": {"PK": old_pk, "SK": old_sk},
                    "ConditionExpression": "attribute_exists(PK)",
                }
            },
            {
                "Put": {
                    "TableName": settings.table_name,
                    "Item": to_item(new_item),
                    "ConditionExpression": "attribute_not_exists(PK)",
                }
            },
        ]
    )


def query_logs(
    baby_id: str,
    from_iso_bound: str,
    to_iso_bound: str,
    *,
    newest_first: bool = True,
    limit: int = 50,
    cursor: str | None = None,
    log_type: str | None = None,
) -> tuple[list[dict], str | None]:
    """One Query over the timeline; feeds and events interleave chronologically.

    Bounds are SK strings from keys.log_sk_bound(); the upper bound gets a
    high-sentinel suffix so items at the exact end instant are included.
    """
    kwargs: dict = {
        "KeyConditionExpression": Key("PK").eq(keys.baby_pk(baby_id))
        & Key("SK").between(from_iso_bound, to_iso_bound + "￿"),
        "ScanIndexForward": not newest_first,
        "Limit": min(limit, 200),
    }
    if log_type:
        from boto3.dynamodb.conditions import Attr

        kwargs["FilterExpression"] = Attr("item_type").eq(log_type)
    if cursor:
        kwargs["ExclusiveStartKey"] = json.loads(
            base64.urlsafe_b64decode(cursor.encode()).decode()
        )

    resp = get_table().query(**kwargs)
    items = [from_item(i) for i in resp["Items"]]
    next_cursor = None
    if "LastEvaluatedKey" in resp:
        next_cursor = base64.urlsafe_b64encode(
            json.dumps(from_item(resp["LastEvaluatedKey"])).encode()
        ).decode()
    return items, next_cursor


def query_all_logs(
    baby_id: str,
    from_iso_bound: str,
    to_iso_bound: str,
    log_type: str | None = None,
) -> list[dict]:
    """Exhaustively page a window (used by daily totals / summaries)."""
    items: list[dict] = []
    cursor = None
    while True:
        page, cursor = query_logs(
            baby_id, from_iso_bound, to_iso_bound,
            newest_first=False, limit=200, cursor=cursor, log_type=log_type,
        )
        items.extend(page)
        if not cursor:
            return items
