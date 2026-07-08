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


def update_fields(
    family_id: str,
    sk: str,
    updates: dict,
    condition: str | None = None,
    condition_values: dict | None = None,
) -> bool:
    """Set top-level fields with an optional condition expression. Returns
    False if the condition failed (e.g. someone else grabbed the work)."""
    from botocore.exceptions import ClientError

    names = {f"#f{i}": k for i, k in enumerate(updates)}
    values = {f":v{i}": v for i, v in enumerate(updates.values())}
    expr = ", ".join(f"#f{i} = :v{i}" for i in range(len(updates)))
    kwargs: dict = {
        "Key": {"PK": keys.family_pk(family_id), "SK": sk},
        "UpdateExpression": f"SET {expr}",
        "ExpressionAttributeNames": names,
        "ExpressionAttributeValues": to_item(values),
    }
    if condition:
        kwargs["ConditionExpression"] = condition
        if condition_values:
            kwargs["ExpressionAttributeValues"] = to_item({**values, **condition_values})
    try:
        get_table().update_item(**kwargs)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def delete(family_id: str, sk: str) -> None:
    get_table().delete_item(Key={"PK": keys.family_pk(family_id), "SK": sk})


def list_by_prefix(family_id: str, sk_prefix: str) -> list[dict]:
    resp = get_table().query(
        KeyConditionExpression=Key("PK").eq(keys.family_pk(family_id))
        & Key("SK").begins_with(sk_prefix)
    )
    return [from_item(i) for i in resp["Items"]]
