"""MyChart sync: SMART standalone OAuth, review-first lab/doc/message imports.

The network seams (token_request / fhir_request) are monkeypatched — no Epic.
"""

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from app.config import settings
from app.services import mychart as mc


@pytest.fixture()
def mychart_env(monkeypatch):
    monkeypatch.setattr(settings, "mychart_client_id", "client-123")
    monkeypatch.setattr(settings, "mychart_redirect_url", "https://api.example.com/v1/mychart/callback")
    monkeypatch.setattr(
        settings, "mychart_fhir_base",
        "https://epic.example.org/Interconnect-FHIRPRD/api/FHIR/R4/",
    )


def _obs(id, name, value, unit, when, rr=None):
    o = {
        "resourceType": "Observation", "id": id,
        "code": {"text": name}, "effectiveDateTime": when,
        "valueQuantity": {"value": value, "unit": unit},
    }
    if rr:
        o["referenceRange"] = [{"text": rr}]
    return o


FHIR_DATA = {}  # resource -> list of resources; set per-test


@pytest.fixture()
def fake_epic(monkeypatch, mychart_env):
    calls = {"token": [], "fhir": []}

    async def fake_token(url, data):
        calls["token"].append((url, data))
        assert url == "https://epic.example.org/Interconnect-FHIRPRD/oauth2/token"
        if data["grant_type"] == "authorization_code":
            assert data["code_verifier"], "PKCE verifier must be sent"
            return {
                "access_token": "at-1", "expires_in": 3600,
                "refresh_token": "rt-1", "patient": "pat-777",
                "scope": "patient/Observation.read offline_access",
            }
        assert data["grant_type"] == "refresh_token"
        return {"access_token": "at-2", "expires_in": 3600, "refresh_token": "rt-2"}

    async def fake_fhir(token, url, params=None, raw=False):
        calls["fhir"].append((token, url, params))
        if raw:
            return b"%PDF-fake", "application/pdf"
        resource = url.rstrip("/").rsplit("/", 1)[-1].split("?")[0]
        if resource == "Communication" and not FHIR_DATA.get("Communication_ok"):
            raise mc.MyChartAuthError("FHIR request rejected (403)")
        return {"resourceType": "Bundle", "entry": [
            {"resource": r} for r in FHIR_DATA.get(resource, [])
        ]}

    monkeypatch.setattr(mc, "token_request", fake_token)
    monkeypatch.setattr(mc, "fhir_request", fake_fhir)
    FHIR_DATA.clear()
    return calls


def _connect(c, baby_id):
    resp = c.post(f"/v1/babies/{baby_id}/mychart/connect-url")
    assert resp.status_code == 200, resp.text
    url = resp.json()["url"]
    q = parse_qs(urlparse(url).query)
    assert q["code_challenge_method"] == ["S256"] and q["client_id"] == ["client-123"]
    cb = c.get("/v1/mychart/callback", params={"code": "abc", "state": q["state"][0]})
    assert cb.status_code == 200, cb.text
    assert "MyChart connected" in cb.text
    return url


def test_connect_stores_tokens_and_patient(auth_client, fake_epic):
    c = auth_client
    _connect(c, c.baby_id)
    status = c.get(f"/v1/babies/{c.baby_id}/mychart").json()
    assert status["connected"] is True and status["status"] == "ok"
    # token exchange used PKCE; connection carries the patient context
    conn = mc.get_connection(_family_id(c), c.baby_id)
    assert conn["patient_fhir_id"] == "pat-777" and conn["refresh_token"] == "rt-1"


def _family_id(c) -> str:
    return c.get("/v1/family").json()["id"]


def test_callback_rejects_unknown_state(auth_client, fake_epic):
    resp = auth_client.get("/v1/mychart/callback", params={"code": "x", "state": "FAM.unknown"})
    assert resp.status_code == 400


def test_sync_lands_review_first_imports(auth_client, fake_epic):
    c = auth_client
    _connect(c, c.baby_id)
    FHIR_DATA["Observation"] = [
        _obs("o1", "Lysine", 92, "umol/L", "2026-08-20T09:00:00Z", rr="52-196"),
        _obs("o2", "Carnitine Free", 31.0, "umol/L", "2026-08-20T09:00:00Z"),
        {"resourceType": "Observation", "id": "panel", "code": {"text": "Amino Acid Panel"}},  # no value
    ]
    FHIR_DATA["DocumentReference"] = [{
        "resourceType": "DocumentReference", "id": "d1",
        "description": "GI Clinic Visit Summary", "date": "2026-08-19T15:00:00Z",
        "content": [
            {"attachment": {"contentType": "text/html", "url": "Binary/html1"}},
            {"attachment": {"contentType": "application/pdf", "url": "Binary/pdf1"}},
        ],
    }]
    FHIR_DATA["Communication_ok"] = True
    FHIR_DATA["Communication"] = [{
        "resourceType": "Communication", "id": "m1",
        "sender": {"display": "Madison Smith RD"}, "sent": "2026-08-24T10:40:00Z",
        "payload": [{"contentString": "How did the transition to Glutarex-1 go?"}],
    }]
    r = c.post(f"/v1/babies/{c.baby_id}/mychart/sync").json()
    assert (r["labs_found"], r["docs_found"], r["messages_found"]) == (2, 1, 1)
    assert r["new_pending"] == 4 and r["messages_available"] is True

    imports = c.get(f"/v1/babies/{c.baby_id}/mychart/imports", params={"status": "pending"}).json()["items"]
    by_key = {i["mc_key"]: i for i in imports}
    assert by_key["lab:o1"]["value"] == 92 and by_key["lab:o1"]["reference_range"] == "52-196"
    assert by_key["lab:o1"]["collected_date"] == "2026-08-20"
    assert by_key["doc:d1"]["content_type"] == "application/pdf"
    assert "Glutarex" in by_key["message:m1"]["text"]

    # Re-sync is idempotent.
    assert c.post(f"/v1/babies/{c.baby_id}/mychart/sync").json()["new_pending"] == 0


def test_confirm_lab_and_dismiss(auth_client, fake_epic):
    c = auth_client
    _connect(c, c.baby_id)
    FHIR_DATA["Observation"] = [_obs("o1", "Plasma Lysine", 92, "umol/L", "2026-08-20T09:00:00Z")]
    c.post(f"/v1/babies/{c.baby_id}/mychart/sync")
    resp = c.post(f"/v1/babies/{c.baby_id}/mychart/imports/lab:o1/confirm", json={"analyte": "lysine"})
    assert resp.status_code == 200, resp.text
    labs = c.get("/v1/labs").json()
    assert [(l["analyte"], l["value"], str(l["collected_date"])) for l in labs] == [("lysine", 92.0, "2026-08-20")]
    # double confirm blocked
    assert c.post(f"/v1/babies/{c.baby_id}/mychart/imports/lab:o1/confirm", json={}).status_code == 409

    FHIR_DATA["Observation"].append(_obs("o2", "Hgb", 11, "g/dL", "2026-08-20T09:00:00Z"))
    c.post(f"/v1/babies/{c.baby_id}/mychart/sync")
    assert c.post(f"/v1/babies/{c.baby_id}/mychart/imports/lab:o2/dismiss").status_code == 204
    pending = c.get(f"/v1/babies/{c.baby_id}/mychart/imports", params={"status": "pending"}).json()["items"]
    assert pending == []


def test_messages_unavailable_is_remembered(auth_client, fake_epic):
    c = auth_client
    _connect(c, c.baby_id)
    FHIR_DATA["Observation"] = []
    FHIR_DATA["DocumentReference"] = []
    r = c.post(f"/v1/babies/{c.baby_id}/mychart/sync").json()
    assert r["messages_available"] is False
    status = c.get(f"/v1/babies/{c.baby_id}/mychart").json()
    assert status["messages_available"] is False
    # Later syncs don't re-probe (fake would raise again anyway — just verify ok status).
    assert c.post(f"/v1/babies/{c.baby_id}/mychart/sync").status_code == 200


def test_refresh_token_rotation(auth_client, fake_epic):
    c = auth_client
    _connect(c, c.baby_id)
    fam = _family_id(c)
    from app.repo import family_items, keys as rkeys

    family_items.update_fields(
        fam, rkeys.mychart_sk(c.baby_id),
        {"access_expires_at": mc.keys.iso_z(datetime.now(timezone.utc) - timedelta(minutes=1))},
    )
    FHIR_DATA["Observation"] = []
    FHIR_DATA["DocumentReference"] = []
    assert c.post(f"/v1/babies/{c.baby_id}/mychart/sync").status_code == 200
    conn = mc.get_connection(fam, c.baby_id)
    assert conn["access_token"] == "at-2" and conn["refresh_token"] == "rt-2"


def test_unconfigured_returns_503(auth_client, monkeypatch):
    monkeypatch.setattr(settings, "mychart_client_id", "")
    resp = auth_client.post(f"/v1/babies/{auth_client.baby_id}/mychart/connect-url")
    assert resp.status_code == 503
    assert auth_client.get(f"/v1/babies/{auth_client.baby_id}/mychart").json()["configured"] is False
