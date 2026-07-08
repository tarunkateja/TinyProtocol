"""Every PK/SK/GSI pattern in the table lives here — nowhere else.

Table shape (single table):
    USER#<email>        / PROFILE                          user, login by email
    FAMILY#<fid>        / META                             family (name, timezone)
    FAMILY#<fid>        / MEMBER#<email>                   membership
    FAMILY#<fid>        / INVITE#<code>                    invite (TTL), GSI1 by code
    FAMILY#<fid>        / BABY#<id> | FOOD#<id> | MEDPRESET#<id>
    BABY#<bid>          / LOG#<utc-iso>#FEED|EVENT#<ulid>  timeline items, GSI1 by log id

GSI1 resolves ids that arrive without their full key:
    LOGID#<log_id>  -> feed/event item
    INVITE#<code>   -> invite item (join flow doesn't know the family id)
"""

from datetime import datetime, timezone

USER_PROFILE_SK = "PROFILE"
FAMILY_META_SK = "META"
GSI1_NAME = "GSI1"
# Constant GSI1SK: the index is a pure id -> item lookup, no sorting needed.
GSI1_STATIC_SK = "A"

LOG_TYPE_FEED = "FEED"
LOG_TYPE_EVENT = "EVENT"


def iso_z(dt: datetime) -> str:
    """Fixed-width UTC ISO-8601 with milliseconds — lexically sortable."""
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def norm_email(email: str) -> str:
    return email.strip().lower()


def user_pk(email: str) -> str:
    return f"USER#{norm_email(email)}"


def family_pk(family_id: str) -> str:
    return f"FAMILY#{family_id}"


def member_sk(email: str) -> str:
    return f"MEMBER#{norm_email(email)}"


def invite_sk(code: str) -> str:
    return f"INVITE#{code}"


def baby_sk(baby_id: str) -> str:
    return f"BABY#{baby_id}"


def food_sk(food_id: str) -> str:
    return f"FOOD#{food_id}"


def med_preset_sk(preset_id: str) -> str:
    return f"MEDPRESET#{preset_id}"


def feed_preset_sk(preset_id: str) -> str:
    return f"FEEDPRESET#{preset_id}"


def chat_sk(chat_id: str) -> str:
    return f"CHAT#{chat_id}"


def baby_pk(baby_id: str) -> str:
    return f"BABY#{baby_id}"


def log_sk(occurred_at: datetime, log_type: str, log_id: str) -> str:
    return f"LOG#{iso_z(occurred_at)}#{log_type}#{log_id}"


def log_sk_bound(dt: datetime) -> str:
    """SK boundary for BETWEEN queries over the timeline."""
    return f"LOG#{iso_z(dt)}"


def gsi1_log_pk(log_id: str) -> str:
    return f"LOGID#{log_id}"


def gsi1_invite_pk(code: str) -> str:
    return f"INVITE#{code}"
