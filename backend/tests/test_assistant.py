"""Assistant endpoint tests with a faked OpenAI client — no real API calls."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from app.config import settings
from app.services import assistant


def _msg(**kwargs):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(**kwargs))]
    )


class FakeOpenAIClient:
    """First call: request the get_recent_summary tool. Second: final answer."""

    def __init__(self):
        self.calls = []
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return _msg(
                content=None,
                tool_calls=[
                    SimpleNamespace(
                        id="call_1",
                        function=SimpleNamespace(
                            name="get_recent_summary",
                            arguments=json.dumps({"hours": 24}),
                        ),
                    )
                ],
            )
        # Echo the lysine total from the tool result to prove data flowed through.
        tool_result = json.loads(self.calls[-1]["messages"][-1]["content"])
        return _msg(
            content=f"In the last 24h: {tool_result['lysine_mg']} mg lysine.",
            tool_calls=None,
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

    fake = FakeOpenAIClient()
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(assistant, "_client", lambda: fake)

    resp = c.post(
        f"/v1/babies/{baby_id}/assistant/chat",
        json={"messages": [{"role": "user", "content": "How much lysine today?"}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["reply"] == "In the last 24h: 42.0 mg lysine."

    # The system prompt carried the guardrails and baby context.
    system = fake.calls[0]["messages"][0]
    assert system["role"] == "system"
    assert "not medical advice" in system["content"]
    assert "Pea" in system["content"] and "GA1" in system["content"]
    assert fake.calls[0]["model"] == "gpt-4o"

    # The tool result went back with the matching tool_call_id.
    tool_msg = fake.calls[1]["messages"][-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "call_1"


def test_chat_unconfigured_returns_503(auth_client, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    resp = auth_client.post(
        f"/v1/babies/{auth_client.baby_id}/assistant/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 503


def test_chat_rejects_assistant_last_message(auth_client, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
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
