"""Every PK/SK/GSI pattern in the table lives here — nowhere else.

Table shape (single table):
    USER#<email>        / PROFILE                          user, login by email
    FAMILY#<fid>        / META                             family (name, timezone)
    FAMILY#<fid>        / MEMBER#<email>                   membership
    FAMILY#<fid>        / INVITE#<code>                    invite (TTL), GSI1 by code
    FAMILY#<fid>        / BABY#<id> | FOOD#<id> | MEDPRESET#<id>
    FAMILY#<fid>        / TARGETHIST#<baby_id>#<date>       target snapshots
    FAMILY#<fid>        / RECIPE#<baby_id>#<utc-iso>        feeding recipes (effective-dated)
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


CARE_PROFILE_SK = "CAREPROFILE"


def clinic_note_sk(note_id: str) -> str:
    return f"CLINICNOTE#{note_id}"


def doc_sk(doc_id: str) -> str:
    return f"DOC#{doc_id}"


def lab_sk(collected_date: str, lab_id: str) -> str:
    # Date first so a prefix query returns chronological order.
    return f"LAB#{collected_date}#{lab_id}"


def huckleberry_sk(baby_id: str) -> str:
    """Per-baby Huckleberry connection (refresh token, child uid, mapping)."""
    return f"HUCKLEBERRY#{baby_id}"


def hb_import_sk(baby_id: str, hb_key: str) -> str:
    """One imported/pending Huckleberry event; hb_key is the Firestore doc id
    (stable across upstream edits), so re-syncs are idempotent."""
    return f"HBIMPORT#{baby_id}#{hb_key}"


def target_hist_sk(baby_id: str, effective_date: str) -> str:
    # Date last so a per-baby prefix query returns chronological order.
    return f"TARGETHIST#{baby_id}#{effective_date}"


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


def recipe_sk(baby_id: str, effective_at: datetime) -> str:
    # Effective time last so a per-baby prefix query returns chronological order.
    return f"RECIPE#{baby_id}#{iso_z(effective_at)}"


def mychart_sk(baby_id: str) -> str:
    """Per-baby MyChart (Epic FHIR) connection: tokens, patient id, endpoints."""
    return f"MYCHART#{baby_id}"


def mc_import_sk(baby_id: str, mc_key: str) -> str:
    """One MyChart import row; mc_key is '<kind>:<fhir id>' so re-syncs are
    idempotent."""
    return f"MCIMPORT#{baby_id}#{mc_key}"


def mc_auth_sk(state: str) -> str:
    """Pending OAuth handshake (PKCE verifier), keyed by the state nonce."""
    return f"MCAUTH#{state}"
