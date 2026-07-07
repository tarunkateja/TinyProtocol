"""The AI assistant: Claude with tools over the baby's real logs.

Design rule: the model NEVER computes or invents nutrition numbers. It calls
tools that run the same aggregation code as the Totals/Summary endpoints and
quotes what comes back. The system prompt enforces the medical guardrails.
"""

import json
from datetime import date, datetime, timedelta, timezone

import anthropic

from app.config import settings
from app.models.baby import Baby
from app.services.summary import summarize_window
from app.services.tz import day_window, to_local

MAX_TOOL_ROUNDS = 5

TOOLS = [
    {
        "name": "get_day_summary",
        "description": (
            "Get the complete log for one calendar day (in the family's timezone): "
            "every feed with its components and times, total ml split by source "
            "(pumped breast milk / latch estimate / formula / metabolic formula), "
            "natural protein g and lysine mg vs the daily targets, medications "
            "given, spit-ups/vomits/fussiness with severity and times, and notes. "
            "Call this when the user asks about a specific day. Call it once per "
            "day you need — e.g. twice to compare two days."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "The calendar day, formatted YYYY-MM-DD",
                }
            },
            "required": ["date"],
        },
    },
    {
        "name": "get_recent_summary",
        "description": (
            "Get the same aggregated log for a rolling window of the last N hours "
            "ending right now. Call this for 'today so far', 'last 24 hours', "
            "'since last night', or when drafting an update for the care team."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "hours": {
                    "type": "integer",
                    "description": "Window size in hours, 1 to 336",
                }
            },
            "required": ["hours"],
        },
    },
]


def is_configured() -> bool:
    return bool(settings.anthropic_api_key)


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _system_prompt(baby: Baby, tz_name: str, parent_name: str) -> str:
    now_local = to_local(datetime.now(timezone.utc), tz_name)
    targets = []
    if baby.targets.lysine_mg_per_day:
        targets.append(f"lysine {baby.targets.lysine_mg_per_day} mg/day")
    if baby.targets.natural_protein_g_per_day:
        targets.append(f"natural protein {baby.targets.natural_protein_g_per_day} g/day")
    target_line = ", ".join(targets) if targets else "not set yet"
    conditions = ", ".join(baby.conditions) if baby.conditions else "none recorded"

    return f"""You are the TinyProtocol assistant, helping {parent_name} — a parent using the \
TinyProtocol app to track feeds and care for their baby, {baby.name}.

Context:
- Baby: {baby.name}. Conditions: {conditions}.
- Daily intake targets from the family's metabolic team: {target_line}.
- Current local time: {now_local.strftime('%A, %B %-d %Y, %-I:%M %p')} ({tz_name}).
- Direct-breastfeeding (latch) amounts in the logs are ESTIMATES from minutes × an \
assumed rate unless marked as weighed. Note this when latch numbers are material to your answer.

Data rules (absolute):
- Every quantity you state (ml, grams, mg, counts, times) must come verbatim from a tool \
result in this conversation. Never estimate, extrapolate, infer, or fill in numbers. If you \
haven't fetched the relevant data yet, fetch it. If the data doesn't exist, say so plainly.
- Do not do your own nutrition math beyond simple restating; the tool results already \
contain computed totals and target percentages.

Medical rules (absolute):
- You are not a medical professional and this is not medical advice. Never recommend \
changing feed amounts, formula ratios, medication doses, or the emergency regimen — \
even if asked directly. For any clinical question or concerning symptom, tell the parent \
to contact their metabolic team, and offer to summarize the relevant data for that conversation.
- If the logs suggest something urgent (e.g. repeated vomiting for a GA1 baby), say clearly \
that they should contact their metabolic team promptly — without diagnosing.

Style:
- Be warm, concise, and practical — this parent is likely sleep-deprived.
- When asked to draft a message/update for the metabolic team or doctor: write it in a \
clinical, scannable format with exact numbers, dates, and times from the tools; no fluff; \
first person from the parent. The parent will review and send it themselves.
- When comparing days or spotting patterns, present the numbers first, keep interpretation \
minimal and factual, and never speculate about causes of symptoms."""


def _run_tool(name: str, tool_input: dict, baby: Baby, tz_name: str) -> str:
    now = datetime.now(timezone.utc)
    if name == "get_day_summary":
        try:
            day = date.fromisoformat(str(tool_input.get("date", "")))
        except ValueError:
            return json.dumps({"error": "date must be YYYY-MM-DD"})
        window_from, window_to = day_window(day, tz_name)
        summary = summarize_window(baby, window_from, window_to, tz_name, day=day)
    elif name == "get_recent_summary":
        try:
            hours = max(1, min(336, int(tool_input.get("hours", 24))))
        except (TypeError, ValueError):
            return json.dumps({"error": "hours must be an integer"})
        summary = summarize_window(baby, now - timedelta(hours=hours), now, tz_name)
    else:
        return json.dumps({"error": f"unknown tool {name}"})

    payload = summary.model_dump(mode="json", exclude={"summary_text"})
    return json.dumps(payload)


def chat(
    baby: Baby, tz_name: str, parent_name: str, messages: list[dict]
) -> str:
    """Run the tool-use loop and return the assistant's final text reply."""
    client = _client()
    convo: list[dict] = list(messages)
    system = _system_prompt(baby, tz_name, parent_name)

    for _ in range(MAX_TOOL_ROUNDS + 1):
        response = client.messages.create(
            model=settings.assistant_model,
            max_tokens=2048,
            system=system,
            tools=TOOLS,
            messages=convo,
        )

        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text")

        convo.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type == "tool_use":
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": _run_tool(block.name, block.input, baby, tz_name),
                    }
                )
        convo.append({"role": "user", "content": results})

    return (
        "I wasn't able to finish looking that up — please try asking in a "
        "smaller chunk (e.g. one day at a time)."
    )
