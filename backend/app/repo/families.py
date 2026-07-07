import time

from boto3.dynamodb.conditions import Key

from app.repo import keys
from app.repo.client import from_item, get_table, to_item

INVITE_TTL_SECONDS = 72 * 3600


def create_family(family_id: str, name: str | None, timezone: str) -> None:
    get_table().put_item(
        Item=to_item(
            {
                "PK": keys.family_pk(family_id),
                "SK": keys.FAMILY_META_SK,
                "id": family_id,
                "name": name,
                "timezone": timezone,
            }
        )
    )


def get_family(family_id: str) -> dict | None:
    resp = get_table().get_item(
        Key={"PK": keys.family_pk(family_id), "SK": keys.FAMILY_META_SK}
    )
    item = resp.get("Item")
    return from_item(item) if item else None


def put_family(family_id: str, data: dict) -> None:
    item = {"PK": keys.family_pk(family_id), "SK": keys.FAMILY_META_SK, **data}
    get_table().put_item(Item=to_item(item))


def add_member(family_id: str, email: str, name: str, role: str = "parent") -> None:
    get_table().put_item(
        Item=to_item(
            {
                "PK": keys.family_pk(family_id),
                "SK": keys.member_sk(email),
                "email": keys.norm_email(email),
                "name": name,
                "role": role,
            }
        )
    )


def list_members(family_id: str) -> list[dict]:
    resp = get_table().query(
        KeyConditionExpression=Key("PK").eq(keys.family_pk(family_id))
        & Key("SK").begins_with("MEMBER#")
    )
    return [from_item(i) for i in resp["Items"]]


def create_invite(family_id: str, code: str, created_by: str) -> int:
    """Returns the expiry epoch."""
    expires = int(time.time()) + INVITE_TTL_SECONDS
    get_table().put_item(
        Item=to_item(
            {
                "PK": keys.family_pk(family_id),
                "SK": keys.invite_sk(code),
                "GSI1PK": keys.gsi1_invite_pk(code),
                "GSI1SK": keys.GSI1_STATIC_SK,
                "code": code,
                "family_id": family_id,
                "created_by": created_by,
                "ttl": expires,
            }
        )
    )
    return expires


def find_invite(code: str) -> dict | None:
    """Invite lookup by code alone (the joiner doesn't know the family id)."""
    resp = get_table().query(
        IndexName=keys.GSI1_NAME,
        KeyConditionExpression=Key("GSI1PK").eq(keys.gsi1_invite_pk(code)),
    )
    items = resp.get("Items", [])
    if not items:
        return None
    invite = from_item(items[0])
    # DynamoDB TTL deletion can lag by up to ~48h — enforce expiry ourselves.
    if invite.get("ttl", 0) < int(time.time()):
        return None
    return invite


def delete_invite(family_id: str, code: str) -> None:
    get_table().delete_item(
        Key={"PK": keys.family_pk(family_id), "SK": keys.invite_sk(code)}
    )
