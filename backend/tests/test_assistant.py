"""Assistant chat-session tests with a faked OpenAI client — no real API calls."""

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
    """Tool round on the first exchange, then plain answers echoing history size."""

    def __init__(self):
        self.calls = []
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        last = kwargs["messages"][-1]
        if last["role"] == "user" and "lysine" in last["content"]:
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
        if last["role"] == "tool":
            tool_result = json.loads(last["content"])
            return _msg(
                content=f"In the last 24h: {tool_result['lysine_mg']} mg lysine.",
                tool_calls=None,
            )
        n_user = sum(1 for m in kwargs["messages"] if m["role"] == "user")
        return _msg(content=f"reply #{n_user}", tool_calls=None)


def _enable(monkeypatch):
    fake = FakeOpenAIClient()
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(assistant, "_client", lambda: fake)
    return fake


def test_chat_session_lifecycle(auth_client, monkeypatch):
    c = auth_client
    baby_id = c.baby_id
    bm = c.foods["Breast milk"]
    fake = _enable(monkeypatch)

    resp = c.post(
        f"/v1/babies/{baby_id}/feeds",
        json={
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "components": [{"kind": "liquid", "food_id": bm["id"], "volume_ml": 60}],
        },
    )
    assert resp.status_code == 201, resp.text

    # Create a chat: tools run, reply quotes real data, title from question.
    resp = c.post(
        f"/v1/babies/{baby_id}/assistant/chats",
        json={"content": "How much lysine today?"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    chat_id = body["chat"]["id"]
    assert body["reply"] == "In the last 24h: 42.0 mg lysine."
    assert body["chat"]["title"] == "How much lysine today?"
    assert [m["role"] for m in body["chat"]["messages"]] == ["user", "assistant"]

    # Continue it: full stored history goes to the model.
    resp = c.post(
        f"/v1/assistant/chats/{chat_id}/messages", json={"content": "thanks!"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["reply"] == "reply #2"
    sent_roles = [m["role"] for m in fake.calls[-1]["messages"]]
    assert sent_roles == ["system", "user", "assistant", "user"]

    # A second chat; list is newest-first metadata without messages.
    c.post(f"/v1/babies/{baby_id}/assistant/chats", json={"content": "second chat"})
    chats = c.get("/v1/assistant/chats").json()
    assert [ch["title"] for ch in chats] == ["second chat", "How much lysine today?"]
    assert "messages" not in chats[0]

    # Fetch full chat; delete it; gone.
    full = c.get(f"/v1/assistant/chats/{chat_id}").json()
    assert len(full["messages"]) == 4
    assert c.delete(f"/v1/assistant/chats/{chat_id}").status_code == 204
    assert c.get(f"/v1/assistant/chats/{chat_id}").status_code == 404


def test_chat_unconfigured_returns_503(auth_client, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    resp = auth_client.post(
        f"/v1/babies/{auth_client.baby_id}/assistant/chats",
        json={"content": "hi"},
    )
    assert resp.status_code == 503


def test_day_summary_tool_validates_date(auth_client):
    from app.models.baby import Baby

    baby = Baby.model_validate(
        auth_client.get(f"/v1/babies/{auth_client.baby_id}").json()
    )
    out = assistant._run_tool(
        "get_day_summary", {"date": "not-a-date"}, baby, "America/New_York"
    )
    assert json.loads(out)["error"] == "date must be YYYY-MM-DD"
