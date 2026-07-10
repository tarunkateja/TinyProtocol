"""v3: weight/per-kg targets, care profile, clinic notes, labs, docs pipeline."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import boto3

from app.config import settings


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def test_weight_event_updates_baby_and_perkg_targets(auth_client):
    c = auth_client
    baby_id = c.baby_id
    now = datetime.now(timezone.utc)

    # Set per-kg targets (GMDI range for 0-6mo: lysine 65-100 mg/kg/day).
    r = c.patch(
        f"/v1/babies/{baby_id}",
        json={"targets": {"lysine_mg_per_kg": 70, "natural_protein_g_per_kg": 1.2}},
    )
    assert r.status_code == 200, r.text

    # Log a weight of 6.5 kg.
    r = c.post(
        f"/v1/babies/{baby_id}/events",
        json={"occurred_at": _iso(now), "type": "weight", "weight_g": 6500},
    )
    assert r.status_code == 201, r.text
    assert c.get(f"/v1/babies/{baby_id}").json()["current_weight_g"] == 6500

    s = c.get(f"/v1/babies/{baby_id}/summary?hours=24").json()
    assert s["targets"]["lysine_mg_per_day"] == 455.0  # 70 * 6.5
    assert s["lysine_target_basis"] == "70 mg/kg × 6.5 kg"
    assert s["targets"]["natural_protein_g_per_day"] == 7.8
    assert s["weights"][0]["weight_g"] == 6500
    assert "Weight: 6.5 kg" in s["summary_text"]

    # Missing weight_g rejected.
    r = c.post(
        f"/v1/babies/{baby_id}/events",
        json={"occurred_at": _iso(now), "type": "weight"},
    )
    assert r.status_code == 422


def test_care_profile_roundtrip(auth_client):
    c = auth_client
    assert c.get("/v1/care-profile").json()["contacts"] == []
    r = c.put(
        "/v1/care-profile",
        json={
            "patient": {"name": "Pea", "diagnosis": "GA-1"},
            "er_interventions": ["Start D10 at 1.5x maintenance"],
            "contacts": [{"label": "Genetics", "phone": "312-227-6120", "when": "M-F"}],
            "bring_to_er": ["Emergency letter"],
        },
    )
    assert r.status_code == 200, r.text
    got = c.get("/v1/care-profile").json()
    assert got["patient"]["name"] == "Pea"
    assert got["contacts"][0]["phone"] == "312-227-6120"
    assert got["updated_at"] is not None


def test_clinic_notes_crud(auth_client):
    c = auth_client
    r = c.post("/v1/clinic-notes", json={"text": "Ask about lysine target change"})
    assert r.status_code == 201, r.text
    note_id = r.json()["id"]
    assert r.json()["created_by"] == "Dad"

    c.post("/v1/clinic-notes", json={"text": "Formula reorder timing"})
    c.patch(f"/v1/clinic-notes/{note_id}", json={"done": True})
    notes = c.get("/v1/clinic-notes").json()
    assert [n["done"] for n in notes] == [False, True]  # open first
    assert c.delete(f"/v1/clinic-notes/{note_id}").status_code == 204
    assert len(c.get("/v1/clinic-notes").json()) == 1


def test_labs_manual_crud(auth_client):
    c = auth_client
    r = c.post(
        "/v1/labs",
        json={"analyte": "Lysine", "value": 82, "unit": "umol/L", "collected_date": "2026-07-01"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["analyte"] == "lysine"  # normalized
    lab_id = r.json()["id"]
    c.post(
        "/v1/labs",
        json={"analyte": "lysine", "value": 75, "unit": "umol/L", "collected_date": "2026-06-01"},
    )
    labs = c.get("/v1/labs").json()
    assert [l["collected_date"] for l in labs] == ["2026-06-01", "2026-07-01"]
    assert c.delete(f"/v1/labs/{lab_id}").status_code == 204
    assert len(c.get("/v1/labs").json()) == 1


def _setup_docs(monkeypatch):
    monkeypatch.setattr(settings, "docs_bucket", "test-docs-bucket")
    monkeypatch.setattr(settings, "worker_function_name", "test-worker")
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-docs-bucket")


def test_docs_pipeline(auth_client, monkeypatch):
    c = auth_client
    _setup_docs(monkeypatch)
    invoked = {}
    monkeypatch.setattr(
        "app.routers.docs.boto3.client",
        lambda svc, **kw: (
            FakeLambda(invoked) if svc == "lambda" else boto3_client_real(svc, **kw)
        ),
    )

    r = c.post("/v1/docs", json={"filename": "letter.pdf", "content_type": "application/pdf"})
    assert r.status_code == 201, r.text
    body = r.json()
    doc_id = body["doc"]["id"]
    assert body["upload_content_type"] == "application/pdf"
    assert "test-docs-bucket" in body["upload_url"]

    # Processing before upload → 409.
    assert c.post(f"/v1/docs/{doc_id}/process").status_code == 409

    # "Upload" the object directly, then process.
    boto3.client("s3", region_name="us-east-1").put_object(
        Bucket="test-docs-bucket", Key=body["doc"]["s3_key"], Body=b"%PDF-1.4 fake"
    )
    r = c.post(f"/v1/docs/{doc_id}/process")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "processing"
    assert invoked["payload"]["doc_id"] == doc_id
    # Double-process while in flight → 409.
    assert c.post(f"/v1/docs/{doc_id}/process").status_code == 409

    # Worker path with a faked OpenAI extraction incl. lab results.
    from app import worker

    fake_extraction = {
        "title": "Plasma amino acids 7/1",
        "doc_type": "lab_report",
        "summary_points": ["Lysine 82 umol/L on 7/1"],
        "contacts": [],
        "key_facts": ["Lysine within target range"],
        "lab_results": [
            {"analyte": "Lysine", "value": 82, "unit": "umol/L", "collected_date": "2026-07-01"},
            {"analyte": "Alanine", "value": 310, "unit": "umol/L", "collected_date": ""},
        ],
    }
    monkeypatch.setattr(worker, "_extract", lambda *a, **k: fake_extraction)
    worker.process_doc(_family_id(c), doc_id)

    doc = c.get(f"/v1/docs/{doc_id}").json()
    assert doc["status"] == "ready"
    assert doc["title"] == "Plasma amino acids 7/1"
    assert "Lysine 82" in doc["summary"]

    # Extracted values wait on the doc for review — nothing auto-logged, and
    # a missing collection date stays empty rather than defaulting to today.
    assert doc["extracted"]["lab_results"] == [
        {"analyte": "lysine", "value": 82, "unit": "umol/L", "collected_date": "2026-07-01"},
        {"analyte": "alanine", "value": 310, "unit": "umol/L", "collected_date": ""},
    ]
    assert c.get("/v1/labs").json() == []

    # The parent confirms just the value they care about, with the real date.
    r = c.post(
        "/v1/labs",
        json={
            "analyte": "lysine", "value": 82, "unit": "umol/L",
            "collected_date": "2026-07-01", "source_doc_id": doc_id,
        },
    )
    assert r.status_code == 201, r.text
    labs = c.get("/v1/labs").json()
    assert len(labs) == 1
    assert labs[0]["analyte"] == "lysine" and labs[0]["source_doc_id"] == doc_id

    # Download URL + delete.
    assert "url" in c.get(f"/v1/docs/{doc_id}/download").json()
    assert c.delete(f"/v1/docs/{doc_id}").status_code == 204
    assert c.get(f"/v1/docs/{doc_id}").status_code == 404


boto3_client_real = boto3.client


class FakeLambda:
    def __init__(self, sink):
        self.sink = sink

    def invoke(self, FunctionName, InvocationType, Payload):
        self.sink["payload"] = json.loads(Payload)
        return {"StatusCode": 202}


def _family_id(c):
    return c.get("/v1/me").json()["family"]["id"]
