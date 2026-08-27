"""MyChart (Epic patient FHIR) endpoints: connect via SMART standalone
patient launch, review-first imports for labs / documents / messages."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from ulid import ULID

from app.auth import CurrentUser, get_current_user
from app.config import settings
from app.models.care import Doc, LabResult
from app.models.mychart import (
    McConnectUrl,
    McImport,
    McLabConfirmIn,
    McStatus,
    McSyncResult,
)
from app.repo import family_items, keys
from app.routers.deps import get_baby_or_404
from app.services import mychart as mc

router = APIRouter(tags=["mychart"])


def _configured() -> bool:
    return bool(settings.mychart_client_id and settings.mychart_redirect_url)


def _status(user: CurrentUser, baby_id: str) -> McStatus:
    conn = mc.get_connection(user.family_id, baby_id)
    if conn is None:
        return McStatus(connected=False, configured=_configured())
    imports = mc.list_imports(user.family_id, baby_id, status="pending")
    return McStatus(
        connected=True,
        configured=_configured(),
        fhir_base=conn.get("fhir_base"),
        scopes=conn.get("granted_scopes"),
        last_synced_at=conn.get("last_synced_at") or None,
        status=conn.get("status"),
        last_error=conn.get("last_error") or None,
        pending_labs=sum(1 for i in imports if i.kind == "lab"),
        pending_docs=sum(1 for i in imports if i.kind == "doc"),
        pending_messages=sum(1 for i in imports if i.kind == "message"),
        messages_available=conn.get("messages_available"),
    )


@router.get("/babies/{baby_id}/mychart", response_model=McStatus)
def get_status(baby_id: str, user: CurrentUser = Depends(get_current_user)):
    get_baby_or_404(user, baby_id)
    return _status(user, baby_id)


@router.post("/babies/{baby_id}/mychart/connect-url", response_model=McConnectUrl)
def connect_url(baby_id: str, user: CurrentUser = Depends(get_current_user)):
    get_baby_or_404(user, baby_id)
    if not _configured():
        raise HTTPException(503, "MyChart sync isn't configured yet (Epic client id missing)")
    return McConnectUrl(url=mc.build_connect_url(user.family_id, baby_id))


_CALLBACK_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TinyProtocol</title></head>
<body style="font-family: -apple-system, sans-serif; background: #FBF7F1; color: #332E40;
display: flex; align-items: center; justify-content: center; min-height: 90vh; text-align: center;">
<div><div style="font-size: 48px">{icon}</div>
<h2 style="margin: 8px 0">{title}</h2>
<p style="color: #8D8699; max-width: 320px">{body}</p></div></body></html>"""


@router.get("/mychart/callback", response_class=HTMLResponse)
async def oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
):
    """Public browser landing for the MyChart OAuth redirect (no app auth —
    the state nonce minted by connect-url is the credential)."""
    if error or not code or not state:
        return HTMLResponse(
            _CALLBACK_HTML.format(
                icon="😕", title="MyChart sign-in didn't finish",
                body=(error_description or error or "Missing code — go back to TinyProtocol and try Connect again."),
            ),
            status_code=400,
        )
    try:
        await mc.complete_auth(state, code)
    except mc.MyChartError as e:
        return HTMLResponse(
            _CALLBACK_HTML.format(icon="😕", title="Could not connect", body=str(e)), status_code=400
        )
    return HTMLResponse(
        _CALLBACK_HTML.format(
            icon="🏥", title="MyChart connected",
            body="You can close this page and return to TinyProtocol — labs and documents will appear under review.",
        )
    )


@router.delete("/babies/{baby_id}/mychart", status_code=204)
def disconnect(baby_id: str, user: CurrentUser = Depends(get_current_user)):
    get_baby_or_404(user, baby_id)
    if mc.get_connection(user.family_id, baby_id) is None:
        raise HTTPException(404, "MyChart is not connected")
    family_items.delete(user.family_id, keys.mychart_sk(baby_id))
    for imp in mc.list_imports(user.family_id, baby_id):
        if imp.status == "pending":
            family_items.delete(user.family_id, keys.mc_import_sk(baby_id, imp.mc_key))


@router.post("/babies/{baby_id}/mychart/sync", response_model=McSyncResult)
async def sync_now(baby_id: str, user: CurrentUser = Depends(get_current_user)):
    get_baby_or_404(user, baby_id)
    try:
        return await mc.sync_baby(user.family_id, baby_id)
    except mc.MyChartAuthError as e:
        raise HTTPException(401, str(e))
    except mc.MyChartError as e:
        raise HTTPException(502, str(e))


@router.get("/babies/{baby_id}/mychart/imports")
def imports(
    baby_id: str,
    status: Optional[str] = Query(None),
    user: CurrentUser = Depends(get_current_user),
):
    get_baby_or_404(user, baby_id)
    return {"items": mc.list_imports(user.family_id, baby_id, status=status)}


def _get_import_or_404(user: CurrentUser, baby_id: str, mc_key: str) -> McImport:
    item = family_items.get(user.family_id, keys.mc_import_sk(baby_id, mc_key))
    if item is None:
        raise HTTPException(404, "Import not found")
    return McImport.model_validate(item)


def _mark(user: CurrentUser, baby_id: str, mc_key: str, status: str, imported_id: str = "") -> None:
    updates = {"status": status, "updated_at": keys.iso_z(datetime.now(timezone.utc))}
    if imported_id:
        updates["imported_id"] = imported_id
    family_items.update_fields(user.family_id, keys.mc_import_sk(baby_id, mc_key), updates)


@router.post("/babies/{baby_id}/mychart/imports/{mc_key}/confirm")
async def confirm_import(
    baby_id: str,
    mc_key: str,
    body: McLabConfirmIn,
    user: CurrentUser = Depends(get_current_user),
):
    get_baby_or_404(user, baby_id)
    imp = _get_import_or_404(user, baby_id, mc_key)
    if imp.status != "pending":
        raise HTTPException(409, f"Import is {imp.status}, not pending")

    if imp.kind == "lab":
        if imp.value is None:
            raise HTTPException(422, "This result has no numeric value — it can't be tracked as a lab")
        collected = body.collected_date or imp.collected_date
        if not collected:
            raise HTTPException(422, "No collection date — supply collected_date")
        lab = LabResult(
            id=str(ULID()),
            analyte=(body.analyte or imp.analyte or "").strip().lower().replace(" ", "_"),
            value=imp.value,
            unit=(body.unit or imp.unit or "?").strip(),
            collected_date=collected,
            created_at=datetime.now(timezone.utc),
        )
        item = lab.model_dump(mode="json")
        item["source"] = "mychart"
        family_items.put(user.family_id, keys.lab_sk(str(lab.collected_date), lab.id), item)
        _mark(user, baby_id, mc_key, "imported", lab.id)
        return {"kind": "lab", "lab": lab}

    if imp.kind == "doc":
        if not imp.binary_url or not imp.content_type:
            raise HTTPException(422, "No importable (PDF/image) rendition for this document")
        if not settings.docs_bucket:
            raise HTTPException(503, "Document storage isn't configured")
        try:
            content, served_type = await mc.fetch_binary(user.family_id, baby_id, imp.binary_url)
        except mc.MyChartAuthError as e:
            raise HTTPException(401, str(e))
        except mc.MyChartError as e:
            raise HTTPException(502, str(e))
        import boto3

        content_type = imp.content_type if imp.content_type != "application/pdf" else "application/pdf"
        ext = "pdf" if content_type == "application/pdf" else content_type.split("/")[-1]
        doc_id = str(ULID())
        filename = f"mychart-{(imp.doc_date or 'document')}-{doc_id[-6:]}.{ext}"
        doc = Doc(
            id=doc_id,
            title=imp.title or filename,
            filename=filename,
            content_type=content_type,
            s3_key=f"{user.family_id}/{doc_id}/{filename}",
            status="uploaded",
            created_at=datetime.now(timezone.utc),
        )
        boto3.client("s3").put_object(
            Bucket=settings.docs_bucket, Key=doc.s3_key, Body=content, ContentType=content_type
        )
        item = doc.model_dump(mode="json")
        item["source"] = "mychart"
        family_items.put(user.family_id, keys.doc_sk(doc.id), item)
        _mark(user, baby_id, mc_key, "imported", doc.id)
        return {"kind": "doc", "doc": doc}

    # message → clinic care note (a record of what the team said)
    text = f"MyChart message{f' from {imp.sender}' if imp.sender else ''}"
    text += f" ({imp.sent_at})" if imp.sent_at else ""
    text += f": {imp.text or ''}"
    note = {
        "id": str(ULID()),
        "text": text[:500],
        "done": True,  # informational, not an open question
        "created_by": user.email,
        "created_at": keys.iso_z(datetime.now(timezone.utc)),
        "source": "mychart",
    }
    family_items.put(user.family_id, keys.clinic_note_sk(note["id"]), note)
    _mark(user, baby_id, mc_key, "imported", note["id"])
    return {"kind": "message", "note_id": note["id"]}


@router.post("/babies/{baby_id}/mychart/imports/{mc_key}/dismiss", status_code=204)
def dismiss_import(baby_id: str, mc_key: str, user: CurrentUser = Depends(get_current_user)):
    get_baby_or_404(user, baby_id)
    imp = _get_import_or_404(user, baby_id, mc_key)
    if imp.status == "imported":
        raise HTTPException(409, "Already imported")
    _mark(user, baby_id, mc_key, "dismissed")
