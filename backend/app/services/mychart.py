"""MyChart -> TinyProtocol sync via Epic's patient-access FHIR APIs.

SMART standalone patient launch (OAuth2 + PKCE, public client): the parent
signs in on MyChart's own page; we store only the tokens — never the
password. A scheduled pass (same Lambda as the Huckleberry sync) pulls lab
Observations, clinical DocumentReferences, and — where the org allows it —
Communications, landing them as review-first MCIMPORT rows.

The two network seams (`token_request`, `fhir_request`) are module-level so
tests can monkeypatch them without touching Epic.
"""

import base64
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlencode

from ulid import ULID

from app.config import settings
from app.models.mychart import McImport, McSyncResult
from app.repo import family_items, keys

log = logging.getLogger(__name__)

AUTH_TTL_MINUTES = 15
LAB_LOOKBACK_DAYS = 365  # first sync pulls a year of labs; later syncs overlap 30d
SYNC_OVERLAP_DAYS = 30
MAX_PAGES = 10


class MyChartError(Exception):
    pass


class MyChartAuthError(MyChartError):
    """Tokens rejected — the parent must reconnect through MyChart."""


def _now_iso() -> str:
    return keys.iso_z(datetime.now(timezone.utc))


def _endpoints(fhir_base: str) -> tuple[str, str]:
    """authorize/token endpoints for an Epic Interconnect FHIR base."""
    root = fhir_base.rstrip("/")
    for suffix in ("/api/FHIR/R4", "/api/FHIR/STU3", "/api/FHIR/DSTU2"):
        if root.endswith(suffix):
            root = root[: -len(suffix)]
            break
    return f"{root}/oauth2/authorize", f"{root}/oauth2/token"


# --------------------------------------------------------------------------- #
# Network seams (monkeypatched in tests)
# --------------------------------------------------------------------------- #
async def token_request(url: str, data: dict) -> dict:
    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data) as resp:
            body = await resp.json(content_type=None)
            if resp.status != 200:
                desc = (body or {}).get("error_description") or (body or {}).get("error") or str(resp.status)
                raise MyChartAuthError(f"Token request failed: {desc}")
            return body


async def fhir_request(access_token: str, url: str, params: Optional[dict] = None, raw: bool = False):
    import aiohttp

    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/fhir+json, application/json, */*"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, headers=headers) as resp:
            if resp.status in (401, 403):
                raise MyChartAuthError(f"FHIR request rejected ({resp.status}) for {url.split('?')[0]}")
            if resp.status == 404:
                raise MyChartError(f"Not found: {url.split('?')[0]}")
            if resp.status != 200:
                raise MyChartError(f"FHIR request failed ({resp.status})")
            if raw:
                return await resp.read(), resp.headers.get("Content-Type", "application/octet-stream")
            return await resp.json(content_type=None)


# --------------------------------------------------------------------------- #
# OAuth: connect URL + callback
# --------------------------------------------------------------------------- #
def build_connect_url(family_id: str, baby_id: str) -> str:
    if not settings.mychart_client_id or not settings.mychart_redirect_url:
        raise MyChartError("MyChart is not configured yet")
    state = str(ULID())
    verifier = secrets.token_urlsafe(64)[:128]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    family_items.put(
        family_id,
        keys.mc_auth_sk(state),
        {
            "item_type": "MCAUTH",
            "baby_id": baby_id,
            "verifier": verifier,
            "created_at": _now_iso(),
        },
    )
    authorize, _ = _endpoints(settings.mychart_fhir_base)
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.mychart_client_id,
            "redirect_uri": settings.mychart_redirect_url,
            "scope": settings.mychart_scopes,
            "state": f"{family_id}.{state}",
            "aud": settings.mychart_fhir_base.rstrip("/"),
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{authorize}?{query}"


async def complete_auth(full_state: str, code: str) -> str:
    """Exchange the auth code; store the connection. Returns the baby_id."""
    try:
        family_id, state = full_state.split(".", 1)
    except ValueError:
        raise MyChartError("Malformed state")
    pending = family_items.get(family_id, keys.mc_auth_sk(state))
    if pending is None:
        raise MyChartError("Unknown or expired sign-in attempt — try Connect again")
    family_items.delete(family_id, keys.mc_auth_sk(state))
    created = datetime.fromisoformat(pending["created_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) - created > timedelta(minutes=AUTH_TTL_MINUTES):
        raise MyChartError("Sign-in attempt expired — try Connect again")

    _, token_url = _endpoints(settings.mychart_fhir_base)
    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.mychart_redirect_url,
        "client_id": settings.mychart_client_id,
        "code_verifier": pending["verifier"],
    }
    if settings.mychart_client_secret:
        token_data["client_secret"] = settings.mychart_client_secret
    body = await token_request(token_url, token_data)
    baby_id = pending["baby_id"]
    expires_in = int(body.get("expires_in") or 300)
    conn = {
        "item_type": "MCSYNC",
        "baby_id": baby_id,
        "fhir_base": settings.mychart_fhir_base,
        "patient_fhir_id": body.get("patient"),
        "access_token": body["access_token"],
        "access_expires_at": keys.iso_z(datetime.now(timezone.utc) + timedelta(seconds=expires_in - 30)),
        "refresh_token": body.get("refresh_token") or "",
        "granted_scopes": body.get("scope") or "",
        "status": "ok",
        "last_error": "",
        "messages_available": None,
        "created_at": _now_iso(),
    }
    if not conn["patient_fhir_id"]:
        raise MyChartError("Epic returned no patient context — is this a patient app client id?")
    family_items.put(family_id, keys.mychart_sk(baby_id), conn)
    return baby_id


def get_connection(family_id: str, baby_id: str) -> Optional[dict]:
    return family_items.get(family_id, keys.mychart_sk(baby_id))


async def _access_token(family_id: str, baby_id: str, conn: dict) -> str:
    """Current access token, refreshing when expired (refresh token rotates)."""
    exp = datetime.fromisoformat(conn["access_expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) < exp:
        return conn["access_token"]
    if not conn.get("refresh_token"):
        family_items.update_fields(
            family_id, keys.mychart_sk(baby_id),
            {"status": "auth_expired", "last_error": "Session expired — reconnect through MyChart"},
        )
        raise MyChartAuthError("Access expired and no refresh token — reconnect")
    _, token_url = _endpoints(conn.get("fhir_base") or settings.mychart_fhir_base)
    try:
        refresh_data = {
            "grant_type": "refresh_token",
            "refresh_token": conn["refresh_token"],
            "client_id": settings.mychart_client_id,
        }
        if settings.mychart_client_secret:
            refresh_data["client_secret"] = settings.mychart_client_secret
        body = await token_request(token_url, refresh_data)
    except MyChartAuthError:
        family_items.update_fields(
            family_id, keys.mychart_sk(baby_id),
            {"status": "auth_expired", "last_error": "MyChart session expired — reconnect"},
        )
        raise
    expires_in = int(body.get("expires_in") or 300)
    updates = {
        "access_token": body["access_token"],
        "access_expires_at": keys.iso_z(datetime.now(timezone.utc) + timedelta(seconds=expires_in - 30)),
    }
    if body.get("refresh_token"):
        updates["refresh_token"] = body["refresh_token"]
    family_items.update_fields(family_id, keys.mychart_sk(baby_id), updates)
    conn.update(updates)
    return conn["access_token"]


# --------------------------------------------------------------------------- #
# FHIR parsing
# --------------------------------------------------------------------------- #
async def _search_all(token: str, base: str, resource: str, params: dict) -> list[dict]:
    url = f"{base.rstrip('/')}/{resource}"
    out: list[dict] = []
    for _ in range(MAX_PAGES):
        bundle = await fhir_request(token, url, params)
        params = None  # next-links carry their own query
        for entry in bundle.get("entry", []) or []:
            res = entry.get("resource") or {}
            if res.get("resourceType") == resource:
                out.append(res)
        nxt = next((l.get("url") for l in bundle.get("link", []) or [] if l.get("relation") == "next"), None)
        if not nxt:
            break
        url = nxt
    return out


def _obs_row(obs: dict) -> Optional[dict]:
    """One lab Observation -> import-row fields (None = not a usable lab)."""
    code = obs.get("code") or {}
    name = code.get("text") or next(
        (c.get("display") for c in code.get("coding", []) if c.get("display")), None
    )
    if not name:
        return None
    when = obs.get("effectiveDateTime") or obs.get("issued") or ""
    row: dict = {
        "kind": "lab",
        "analyte": name[:60],
        "collected_date": when[:10] if when else None,
    }
    vq = obs.get("valueQuantity")
    if vq and vq.get("value") is not None:
        row["value"] = float(vq["value"])
        row["unit"] = str(vq.get("unit") or vq.get("code") or "")[:20] or "?"
    elif obs.get("valueString"):
        row["value_text"] = str(obs["valueString"])[:200]
    elif obs.get("valueCodeableConcept"):
        row["value_text"] = str((obs["valueCodeableConcept"].get("text") or ""))[:200]
    else:
        return None  # panels/organizers without their own value
    rr = (obs.get("referenceRange") or [{}])[0].get("text")
    if rr:
        row["reference_range"] = str(rr)[:80]
    return row


def _doc_row(ref: dict) -> Optional[dict]:
    desc = ref.get("description") or (ref.get("type") or {}).get("text") or "Document"
    when = ref.get("date") or ""
    contents = ref.get("content") or []
    best = None
    for c in contents:
        att = c.get("attachment") or {}
        ct = (att.get("contentType") or "").lower()
        if not att.get("url"):
            continue
        if ct == "application/pdf":
            best = (ct, att["url"])
            break
        if best is None and ct.startswith("image/"):
            best = (ct, att["url"])
    return {
        "kind": "doc",
        "title": str(desc)[:120],
        "doc_date": when[:10] if when else None,
        "content_type": best[0] if best else None,
        "binary_url": best[1] if best else None,
    }


def _msg_row(com: dict) -> Optional[dict]:
    texts = [p.get("contentString") for p in com.get("payload", []) or [] if p.get("contentString")]
    if not texts:
        return None
    sender = (com.get("sender") or {}).get("display")
    when = com.get("sent") or com.get("received") or ""
    return {
        "kind": "message",
        "sender": sender,
        "sent_at": when[:16].replace("T", " ") if when else None,
        "text": "\n\n".join(texts)[:4000],
    }


# --------------------------------------------------------------------------- #
# Sync
# --------------------------------------------------------------------------- #
async def sync_baby(family_id: str, baby_id: str) -> McSyncResult:
    conn = get_connection(family_id, baby_id)
    if conn is None:
        raise MyChartError("MyChart is not connected for this baby")
    token = await _access_token(family_id, baby_id, conn)
    base = (conn.get("fhir_base") or settings.mychart_fhir_base).rstrip("/")
    pid = conn["patient_fhir_id"]

    existing = {
        i["mc_key"]
        for i in family_items.list_by_prefix(family_id, f"MCIMPORT#{baby_id}#")
    }
    result = McSyncResult()
    now_iso = _now_iso()
    since = (
        datetime.now(timezone.utc)
        - timedelta(days=SYNC_OVERLAP_DAYS if conn.get("last_synced_at") else LAB_LOOKBACK_DAYS)
    ).strftime("%Y-%m-%d")

    def _put(fhir_id: str, fields: dict) -> None:
        mc_key = f"{fields['kind']}:{fhir_id}"
        if mc_key in existing:
            return
        existing.add(mc_key)
        result.new_pending += 1
        family_items.put(
            family_id,
            keys.mc_import_sk(baby_id, mc_key),
            {
                "item_type": "MCIMPORT",
                "baby_id": baby_id,
                "mc_key": mc_key,
                "status": "pending",
                "created_at": now_iso,
                "updated_at": now_iso,
                **fields,
            },
        )

    try:
        for obs in await _search_all(
            token, base, "Observation",
            {"patient": pid, "category": "laboratory", "date": f"ge{since}", "_count": "100"},
        ):
            row = _obs_row(obs)
            if row and obs.get("id"):
                result.labs_found += 1
                _put(obs["id"], row)

        for ref in await _search_all(
            token, base, "DocumentReference", {"patient": pid, "_count": "50"}
        ):
            row = _doc_row(ref)
            if row and ref.get("id"):
                result.docs_found += 1
                _put(ref["id"], row)

        # Communications: many orgs don't expose MyChart messages to patient
        # apps — probe once, remember the answer, degrade quietly.
        if conn.get("messages_available") is not False:
            try:
                for com in await _search_all(
                    token, base, "Communication", {"patient": pid, "_count": "50"}
                ):
                    row = _msg_row(com)
                    if row and com.get("id"):
                        result.messages_found += 1
                        _put(com["id"], row)
                result.messages_available = True
            except (MyChartAuthError, MyChartError) as e:
                log.info("Communication not available: %s", e)
                result.messages_available = False
            family_items.update_fields(
                family_id, keys.mychart_sk(baby_id),
                {"messages_available": result.messages_available},
            )
    except MyChartAuthError as e:
        family_items.update_fields(
            family_id, keys.mychart_sk(baby_id),
            {"status": "auth_expired", "last_error": str(e)[:200]},
        )
        raise
    except MyChartError as e:
        family_items.update_fields(
            family_id, keys.mychart_sk(baby_id),
            {"status": "error", "last_error": str(e)[:200]},
        )
        raise

    family_items.update_fields(
        family_id, keys.mychart_sk(baby_id),
        {"last_synced_at": now_iso, "status": "ok", "last_error": ""},
    )
    return result


def list_imports(family_id: str, baby_id: str, status: Optional[str] = None) -> list[McImport]:
    items = family_items.list_by_prefix(family_id, f"MCIMPORT#{baby_id}#")
    imports = [McImport.model_validate(i) for i in items]
    if status:
        imports = [i for i in imports if i.status == status]
    imports.sort(key=lambda i: (i.collected_date or i.doc_date or i.sent_at or ""), reverse=True)
    return imports


async def fetch_binary(family_id: str, baby_id: str, binary_url: str) -> tuple[bytes, str]:
    conn = get_connection(family_id, baby_id)
    if conn is None:
        raise MyChartError("MyChart is not connected")
    token = await _access_token(family_id, baby_id, conn)
    base = (conn.get("fhir_base") or settings.mychart_fhir_base).rstrip("/")
    url = binary_url if binary_url.startswith("http") else f"{base}/{binary_url.lstrip('/')}"
    return await fhir_request(token, url, raw=True)


async def sync_all_connections() -> list[dict]:
    """One pass over every MyChart connection (scheduled Lambda)."""
    results = []
    for conn in family_items.scan_sk_prefix("MYCHART#"):
        family_id = conn["PK"].split("#", 1)[1]
        baby_id = conn["baby_id"]
        if conn.get("status") == "auth_expired" and not conn.get("refresh_token"):
            continue  # nothing to retry until the parent reconnects
        try:
            r = await sync_baby(family_id, baby_id)
            results.append({"family_id": family_id, "baby_id": baby_id, **r.model_dump()})
        except MyChartError as e:
            results.append({"family_id": family_id, "baby_id": baby_id, "error": str(e)[:200]})
    return results
