"""Assistant endpoint tests with a faked Anthropic client — no real API calls."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from app.config import settings
from app.services import assistant


class FakeBlock(SimpleNamespace):
    pass


class FakeAnthropicClient:
    """First call: request the get_recent_summary tool. Second: final answer."""

    def __init__(self):
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    FakeBlock(
                        type="tool_use",
                        id="toolu_1",
                        name="get_recent_summary",
                        input={"hours": 24},
                    )
                ],
            )
        # Echo the lysine total from the tool result to prove data flowed through.
        tool_result = json.loads(self.calls[-1]["messages"][-1]["content"][0]["content"])
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[
                FakeBlock(
                    type="text",
                    text=f"In the last 24h: {tool_result['lysine_mg']} mg lysine.",
                )
            ],
        )


def test_chat_runs_tools_and_answers(auth_client, monkeypatch):
    c = auth_client
    baby_id = c.baby_id
    bm = c.foods["Breast milk"]

    # 60 ml breast milk -> 42 mg lysine, per the seeded values.
    resp = c.post(
        f"/v1/babies/{baby_id}/feeds",
        json={
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "components": [{"kind": "liquid", "food_id": bm["id"], "volume_ml": 60}],
        },
    )
    assert resp.status_code == 201, resp.text

    fake = FakeAnthropicClient()
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(assistant, "_client", lambda: fake)

    resp = c.post(
        f"/v1/babies/{baby_id}/assistant/chat",
        json={"messages": [{"role": "user", "content": "How much lysine today?"}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["reply"] == "In the last 24h: 42.0 mg lysine."

    # The system prompt carried the guardrails and baby context.
    system = fake.calls[0]["system"]
    assert "not medical advice" in system
    assert "Pea" in system and "GA1" in system
    assert fake.calls[0]["model"] == "claude-opus-4-8"


def test_chat_unconfigured_returns_503(auth_client, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    resp = auth_client.post(
        f"/v1/babies/{auth_client.baby_id}/assistant/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 503


def test_chat_rejects_assistant_last_message(auth_client, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    resp = auth_client.post(
        f"/v1/babies/{auth_client.baby_id}/assistant/chat",
        json={"messages": [{"role": "assistant", "content": "hello"}]},
    )
    assert resp.status_code == 422


def test_day_summary_tool_validates_date(auth_client):
    from app.models.baby import Baby

    baby = Baby.model_validate(
        auth_client.get(f"/v1/babies/{auth_client.baby_id}").json()
    )
    out = assistant._run_tool(
        "get_day_summary", {"date": "not-a-date"}, baby, "America/New_York"
    )
    assert json.loads(out)["error"] == "date must be YYYY-MM-DD"
