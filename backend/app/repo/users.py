from botocore.exceptions import ClientError

from app.repo import keys
from app.repo.client import from_item, get_table, to_item


class EmailExistsError(Exception):
    pass


def create_user(
    *, email: str, name: str, password_hash: str, family_id: str, user_id: str
) -> None:
    item = {
        "PK": keys.user_pk(email),
        "SK": keys.USER_PROFILE_SK,
        "id": user_id,
        "email": keys.norm_email(email),
        "name": name,
        "password_hash": password_hash,
        "family_id": family_id,
    }
    try:
        get_table().put_item(
            Item=to_item(item), ConditionExpression="attribute_not_exists(PK)"
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise EmailExistsError(email)
        raise


def get_user(email: str) -> dict | None:
    resp = get_table().get_item(
        Key={"PK": keys.user_pk(email), "SK": keys.USER_PROFILE_SK}
    )
    item = resp.get("Item")
    return from_item(item) if item else None
