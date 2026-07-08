"""Async worker Lambda: AI extraction for care documents.

Invoked fire-and-forget by POST /docs/{id}/process (same code bundle,
separate function with a 300s timeout — extraction doesn't fit the API
Gateway 30s window). Reads the object from S3, sends it to gpt-4o, writes
the structured extraction back onto the DOC item, and fans lab results out
to LAB# items.
"""

import base64
import io
import json
from datetime import datetime, timezone

import boto3
from openai import OpenAI
from ulid import ULID

from app.config import settings
from app.models.care import DocExtraction, LabResult
from app.repo import family_items, keys

MAX_PDF_PAGES = 10

EXTRACTION_SCHEMA = {
    "name": "care_doc_extraction",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short human title for the document"},
            "doc_type": {
                "type": "string",
                "enum": [
                    "clinic_guide", "emergency_letter", "sick_day_protocol",
                    "lab_report", "prescription", "formula_instructions", "other",
                ],
            },
            "summary_points": {
                "type": "array", "items": {"type": "string"},
                "description": "5-8 plain-text bullets a sleep-deprived parent can scan",
            },
            "contacts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "phone": {"type": "string"},
                        "when": {"type": ["string", "null"]},
                    },
                    "required": ["label", "phone", "when"],
                    "additionalProperties": False,
                },
            },
            "key_facts": {
                "type": "array", "items": {"type": "string"},
                "description": "Actionable rules/doses/thresholds stated in the document",
            },
            "lab_results": {
                "type": "array",
                "description": "ONLY for lab reports: every analyte row with a numeric value",
                "items": {
                    "type": "object",
                    "properties": {
                        "analyte": {"type": "string", "description": "lowercase_snake_case, e.g. lysine, glutarylcarnitine, free_carnitine"},
                        "value": {"type": "number"},
                        "unit": {"type": "string"},
                        "collected_date": {"type": "string", "description": "YYYY-MM-DD; empty string if unknown"},
                    },
                    "required": ["analyte", "value", "unit", "collected_date"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["title", "doc_type", "summary_points", "contacts", "key_facts", "lab_results"],
        "additionalProperties": False,
    },
}

PROMPT = """You are processing a medical/care document uploaded by the parents of an
infant with GA1 (glutaric aciduria type 1) into their private care app. Extract the
content faithfully — do NOT invent, infer, or embellish anything not printed in the
document. Plain text only, no Markdown. Extract every phone number with its purpose
and availability hours. For lab reports, extract every analyte row exactly as printed
(value, unit, collection date). If a field doesn't apply, return it empty."""


def _trim_pdf(data: bytes) -> bytes:
    """Keep the first MAX_PDF_PAGES pages to bound cost and latency."""
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(data))
    if len(reader.pages) <= MAX_PDF_PAGES:
        return data
    writer = PdfWriter()
    for page in reader.pages[:MAX_PDF_PAGES]:
        writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _content_part(data: bytes, content_type: str, filename: str) -> dict:
    if content_type == "application/pdf":
        b64 = base64.b64encode(_trim_pdf(data)).decode()
        return {
            "type": "file",
            "file": {"filename": filename, "file_data": f"data:application/pdf;base64,{b64}"},
        }
    b64 = base64.b64encode(data).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{b64}"}}


def _extract(data: bytes, content_type: str, filename: str) -> dict:
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.assistant_model,
        max_tokens=3000,
        response_format={"type": "json_schema", "json_schema": EXTRACTION_SCHEMA},
        messages=[
            {"role": "system", "content": PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract this document."},
                    _content_part(data, content_type, filename),
                ],
            },
        ],
    )
    return json.loads(response.choices[0].message.content or "{}")


def _store_labs(family_id: str, doc_id: str, lab_results: list[dict]) -> int:
    stored = 0
    for row in lab_results:
        try:
            collected = row.get("collected_date") or datetime.now(timezone.utc).date().isoformat()
            lab = LabResult(
                id=str(ULID()),
                analyte=str(row["analyte"]).strip().lower().replace(" ", "_"),
                value=float(row["value"]),
                unit=str(row["unit"]).strip(),
                collected_date=collected,
                source_doc_id=doc_id,
                created_at=datetime.now(timezone.utc),
            )
        except (KeyError, ValueError, TypeError):
            continue
        family_items.put(
            family_id, keys.lab_sk(str(lab.collected_date), lab.id),
            lab.model_dump(mode="json"),
        )
        stored += 1
    return stored


def process_doc(family_id: str, doc_id: str) -> None:
    item = family_items.get(family_id, keys.doc_sk(doc_id))
    if item is None or item.get("status") != "processing":
        return

    try:
        obj = boto3.client("s3").get_object(
            Bucket=settings.docs_bucket, Key=item["s3_key"]
        )
        data = obj["Body"].read()
        raw = _extract(data, item["content_type"], item["filename"])
        extraction = DocExtraction(
            doc_type=raw.get("doc_type") or "other",
            summary_points=[p for p in raw.get("summary_points", []) if p][:10],
            contacts=raw.get("contacts", []),
            key_facts=[f for f in raw.get("key_facts", []) if f][:15],
        )
        labs_added = 0
        if extraction.doc_type == "lab_report" or raw.get("lab_results"):
            labs_added = _store_labs(family_id, doc_id, raw.get("lab_results", []))

        family_items.update_fields(
            family_id,
            keys.doc_sk(doc_id),
            {
                "status": "ready",
                "error": "",
                "title": (raw.get("title") or item.get("title") or item["filename"])[:120],
                "summary": "\n".join(f"• {p}" for p in extraction.summary_points),
                "extracted": extraction.model_dump(mode="json"),
                "lab_results_added": labs_added,
            },
            condition="#f0 = :processing",
            condition_values={":processing": "processing"},
        )
    except Exception as e:  # surface anything as a retryable error state
        family_items.update_fields(
            family_id,
            keys.doc_sk(doc_id),
            {"status": "error", "error": str(e)[:300]},
        )


def handler(event, context):
    if event.get("task") == "process_doc":
        process_doc(event["family_id"], event["doc_id"])
    return {"ok": True}
