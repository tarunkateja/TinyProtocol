"""The AI assistant: an LLM with tools over the baby's real logs.

Design rule: the model NEVER computes or invents nutrition numbers. It calls
tools that run the same aggregation code as the Totals/Summary endpoints and
quotes what comes back. The system prompt enforces the medical guardrails.
"""

import json
from datetime import date, datetime, time, timedelta, timezone

from openai import OpenAI

from app.config import settings
from app.models.baby import Baby
from app.services.summary import summarize_window
from app.services.tz import day_window, to_local

MAX_TOOL_ROUNDS = 5

TOOLS = [
    {
        "type": "function",
        "function": {
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
            "parameters": {
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
    },
    {
        "type": "function",
        "function": {
            "name": "get_care_notes",
            "description": (
                "Get the family's care information: the emergency card (ER "
                "interventions, when-to-call rules, care team phone numbers with "
                "hours, bring-to-ER list, formula ordering rules), key facts "
                "extracted from uploaded clinic documents, and the parents' OPEN "
                "questions for the next clinic visit. Call this for anything about "
                "contacting the care team, emergencies, clinic logistics, or when "
                "drafting a clinic update (include open questions)."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_lab_results",
            "description": (
                "Get all stored lab results (analyte, value, unit, collection "
                "date) — e.g. plasma lysine, glutarylcarnitine, carnitine — for "
                "trend questions like 'how has her lysine level changed?'."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_summary",
            "description": (
                "Get the same aggregated log for a rolling window of the last N hours "
                "ending right now. Call this for 'today so far', 'last 24 hours', "
                "'since last night', or when drafting an update for the care team."
            ),
            "parameters": {
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
    },
]


def is_configured() -> bool:
    return bool(settings.openai_api_key)


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


def _system_prompt(
    baby: Baby, tz_name: str, parent_name: str, day_start: time = time.min
) -> str:
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
- TODAY'S DATE is {now_local.strftime('%Y-%m-%d')}. The family's day runs from \
{day_start.strftime('%H:%M')} to {day_start.strftime('%H:%M')} the next morning — \
get_day_summary('{now_local.strftime('%Y-%m-%d')}') covers that window.
- Date arithmetic: "yesterday" = today minus 1 day; "last 3 days" = today, yesterday, \
and the day before — call get_day_summary once for EACH date (compute exact YYYY-MM-DD \
values from today's date above; never guess dates). Use get_recent_summary(hours=N) \
only for rolling windows like "last 24 hours".
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
- PLAIN TEXT ONLY — your reply renders in a simple chat bubble that does not support \
Markdown. Never use **bold**, _italics_, # headings, tables, or --- dividers. Use short \
lines, '•' for bullets, CAPITALIZED WORDS or a trailing colon for emphasis, and blank \
lines between sections.
- Be warm, concise, and practical — this parent is likely sleep-deprived.
- When asked to draft a message/update for the metabolic team or doctor: write it in a \
clinical, scannable format with exact numbers, dates, and times from the tools; no fluff; \
first person from the parent. The parent will review and send it themselves.
- When comparing days or spotting patterns, present the numbers first, keep interpretation \
minimal and factual, and never speculate about causes of symptoms."""


def _run_tool(
    name: str,
    tool_input: dict,
    baby: Baby,
    tz_name: str,
    day_start: time = time.min,
    family_id: str = "",
) -> str:
    from app.repo import family_items
    from app.repo import keys as rkeys

    now = datetime.now(timezone.utc)
    if name == "get_care_notes":
        care = family_items.get(family_id, rkeys.CARE_PROFILE_SK) or {}
        care.pop("PK", None)
        care.pop("SK", None)
        docs = family_items.list_by_prefix(family_id, "DOC#")
        doc_facts = [
            {
                "title": d.get("title"),
                "key_facts": (d.get("extracted") or {}).get("key_facts", []),
                "contacts": (d.get("extracted") or {}).get("contacts", []),
            }
            for d in docs
            if d.get("status") == "ready"
        ]
        notes = family_items.list_by_prefix(family_id, "CLINICNOTE#")
        open_questions = [n["text"] for n in notes if not n.get("done")]
        return json.dumps({
            "emergency_card": care,
            "document_key_facts": doc_facts,
            "open_clinic_questions": open_questions,
        })
    if name == "get_lab_results":
        labs = family_items.list_by_prefix(family_id, "LAB#")
        rows = [
            {k: v for k, v in lab.items() if k in ("analyte", "value", "unit", "collected_date")}
            for lab in labs
        ]
        rows.sort(key=lambda r: (r.get("analyte", ""), r.get("collected_date", "")))
        return json.dumps({"lab_results": rows})
    if name == "get_day_summary":
        try:
            day = date.fromisoformat(str(tool_input.get("date", "")))
        except ValueError:
            return json.dumps({"error": "date must be YYYY-MM-DD"})
        window_from, window_to = day_window(day, tz_name, day_start)
        if family_id:
            from app.services import target_history

            baby = baby.model_copy(
                update={"targets": target_history.targets_for_day(family_id, baby, day)}
            )
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
    baby: Baby,
    tz_name: str,
    parent_name: str,
    messages: list[dict],
    day_start: time = time.min,
    family_id: str = "",
) -> str:
    """Run the tool-use loop and return the assistant's final text reply."""
    client = _client()
    convo: list[dict] = [
        {"role": "system", "content": _system_prompt(baby, tz_name, parent_name, day_start)},
        *messages,
    ]

    for _ in range(MAX_TOOL_ROUNDS + 1):
        response = client.chat.completions.create(
            model=settings.assistant_model,
            max_completion_tokens=3000,
            # gpt-5.5 chat completions requires 'none' when function tools are
            # used (also keeps the tool loop inside the 29s route budget).
            reasoning_effort="none",
            tools=TOOLS,
            messages=convo,
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            return msg.content or ""

        convo.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
        )
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            convo.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": _run_tool(
                        tc.function.name, args, baby, tz_name, day_start, family_id
                    ),
                }
            )

    return (
        "I wasn't able to finish looking that up — please try asking in a "
        "smaller chunk (e.g. one day at a time)."
    )
