import os

# Must be set before any app import — Settings reads the environment at import.
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ["TABLE_NAME"] = "TinyProtocol-test"
os.environ["JWT_SECRET"] = "test-secret"
os.environ.pop("DYNAMO_ENDPOINT_URL", None)

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from app.config import settings
from app.main import app
from app.repo import client as repo_client
from app.repo.schema import create_table


@pytest.fixture()
def client():
    with mock_aws():
        repo_client.reset()
        create_table(
            boto3.client("dynamodb", region_name="us-east-1"), settings.table_name
        )
        with TestClient(app) as c:
            yield c
    repo_client.reset()


@pytest.fixture()
def auth_client(client):
    """Registered family with a baby; requests carry the token."""
    resp = client.post(
        "/v1/auth/register",
        json={
            "email": "dad@example.com",
            "password": "hunter2hunter2",
            "name": "Dad",
            "timezone": "America/New_York",
            "baby": {
                "name": "Pea",
                "conditions": ["GA1"],
                "default_latch_rate_ml_per_10min": 25,
                "targets": {
                    "lysine_mg_per_day": 420,
                    "natural_protein_g_per_day": 6.0,
                },
            },
        },
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"

    babies = client.get("/v1/babies").json()
    client.baby_id = babies[0]["id"]

    foods = client.get("/v1/foods").json()
    client.foods = {f["name"]: f for f in foods}
    return client
