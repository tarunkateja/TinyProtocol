"""Care documents: presigned upload to S3, async AI extraction, retrieval."""

import json
from datetime import datetime, timedelta, timezone

import boto3
from fastapi import APIRouter, Depends, HTTPException
from ulid import ULID

from app.auth import CurrentUser, get_current_user
from app.config import settings
from app.models.care import Doc, DocCreate, DocCreated
from app.repo import family_items, keys

router = APIRouter(tags=["docs"])

STALE_PROCESSING = timedelta(minutes=5)


def _s3():
    return boto3.client("s3")


def _require_configured() -> None:
    if not settings.docs_bucket:
        raise HTTPException(503, "Document storage isn't configured yet")


def _load_doc(user: CurrentUser, doc_id: str) -> Doc:
    item = family_items.get(user.family_id, keys.doc_sk(doc_id))
    if item is None:
        raise HTTPException(404, "Document not found")
    return Doc.model_validate(item)


@router.post("/docs", response_model=DocCreated, status_code=201)
def create_doc(body: DocCreate, user: CurrentUser = Depends(get_current_user)):
    _require_configured()
    doc_id = str(ULID())
    doc = Doc(
        id=doc_id,
        title=body.title or body.filename,
        filename=body.filename,
        content_type=body.content_type,
        s3_key=f"{user.family_id}/{doc_id}/{body.filename}",
        status="uploaded",
        created_at=datetime.now(timezone.utc),
    )
    family_items.put(user.family_id, keys.doc_sk(doc.id), doc.model_dump(mode="json"))
    # ContentType is part of the signature — the client MUST send it verbatim.
    upload_url = _s3().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.docs_bucket,
            "Key": doc.s3_key,
            "ContentType": body.content_type,
        },
        ExpiresIn=900,
    )
    return DocCreated(doc=doc, upload_url=upload_url, upload_content_type=body.content_type)


@router.get("/docs", response_model=list[Doc])
def list_docs(user: CurrentUser = Depends(get_current_user)):
    items = family_items.list_by_prefix(user.family_id, "DOC#")
    docs = [Doc.model_validate(i) for i in items]
    return sorted(docs, key=lambda d: d.created_at, reverse=True)


@router.get("/docs/{doc_id}", response_model=Doc)
def get_doc(doc_id: str, user: CurrentUser = Depends(get_current_user)):
    return _load_doc(user, doc_id)


@router.post("/docs/{doc_id}/process", response_model=Doc)
def process_doc(doc_id: str, user: CurrentUser = Depends(get_current_user)):
    _require_configured()
    doc = _load_doc(user, doc_id)
    if doc.status == "ready":
        return doc

    try:
        head = _s3().head_object(Bucket=settings.docs_bucket, Key=doc.s3_key)
    except _s3().exceptions.ClientError:
        raise HTTPException(409, "The file hasn't finished uploading yet — try again")
    if head["ContentLength"] > settings.max_doc_bytes:
        family_items.update_fields(
            user.family_id, keys.doc_sk(doc_id),
            {"status": "error", "error": "File is larger than 15 MB"},
        )
        raise HTTPException(413, "File is larger than 15 MB")

    now = datetime.now(timezone.utc)
    stale_before = (now - STALE_PROCESSING).isoformat()
    # uploaded/error → processing, or re-claim a stale processing run.
    claimed = family_items.update_fields(
        user.family_id,
        keys.doc_sk(doc_id),
        {"status": "processing", "processing_started_at": now.isoformat()},
        condition=(
            "#f0 IN (:uploaded, :error) OR "
            "(#f0 = :processing AND #f1 < :stale)"
        ),
        condition_values={
            ":uploaded": "uploaded",
            ":error": "error",
            ":processing": "processing",
            ":stale": stale_before,
        },
    )
    if not claimed:
        raise HTTPException(409, "Already being processed")

    if not settings.worker_function_name:
        raise HTTPException(503, "Document processing isn't configured yet")
    boto3.client("lambda").invoke(
        FunctionName=settings.worker_function_name,
        InvocationType="Event",
        Payload=json.dumps(
            {"task": "process_doc", "family_id": user.family_id, "doc_id": doc_id}
        ).encode(),
    )
    return _load_doc(user, doc_id)


@router.get("/docs/{doc_id}/download")
def download_doc(doc_id: str, user: CurrentUser = Depends(get_current_user)):
    _require_configured()
    doc = _load_doc(user, doc_id)
    url = _s3().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.docs_bucket, "Key": doc.s3_key},
        ExpiresIn=900,
    )
    return {"url": url}


@router.delete("/docs/{doc_id}", status_code=204)
def delete_doc(doc_id: str, user: CurrentUser = Depends(get_current_user)):
    _require_configured()
    doc = _load_doc(user, doc_id)
    # Object first — an orphaned DynamoDB record is worse than an orphaned object.
    _s3().delete_object(Bucket=settings.docs_bucket, Key=doc.s3_key)
    family_items.delete(user.family_id, keys.doc_sk(doc_id))
