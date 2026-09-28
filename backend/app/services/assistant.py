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
from app.services.tz import day_window, effective_day, to_local

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
            "name": "get_poop_history",
            "description": (
                "Get the diaper/poop record for the last N days: per-day counts "
                "(pee, poop), every poop with its time, hours since the previous "
                "poop, color, consistency and the parent's note, plus hours since "
                "the most recent poop and the longest gap. Call this for anything "
                "about poop, bowel movements, constipation, 'how many days since "
                "she pooped', stool consistency, or diaper counts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "How many calendar days back to include, 1 to 92",
                    }
                },
                "required": ["days"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recipe_history",
            "description": (
                "Get the family's feeding recipe history: for each plan the "
                "metabolic team ordered, when it took effect, the prepared bottle "
                "(breast milk ml + batch formula ml per feed), the batch recipe "
                "(powder grams, water to final volume), what top-ups are made of, "
                "feeds per day, who ordered it and notes. Call this for 'what is/was "
                "the recipe', 'what are top-ups', 'when did "
                "the plan change', batch yield questions, or when a clinic update "
                "should state the current plan."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dietitian_update",
            "description": (
                "Get the ready-to-send feeding-log update for the metabolic dietitian, "
                "in the exact format the family pastes into MyChart: one section per "
                "family day for the last N full days (plus this morning), one bullet per "
                "feed with time, volume and the parent's note, and one total line per "
                "day with the breast-milk amount. Call this whenever the parent asks for "
                "the dietitian update (they may call it by the dietitian's name), "
                "'feeding logs for the last N days', or a feeds message to send the care "
                "team. Return the text VERBATIM — never reformat, summarize, add or drop "
                "lines — and list any warnings separately so the parent can fix the log "
                "before sending."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "How many full days before today to include, 1 to 14",
                    }
                },
                "required": ["days"],
            },
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
    {
        "type": "function",
        "function": {
            "name": "search_community",
            "description": (
                "Search real discussions from a private Facebook support group of "
                "~1.4K families affected by GA-1, spanning 2008-2026. Use this for "
                "lived-experience questions that the baby's own logs cannot answer: "
                "what other parents did, what they observed, how they handled "
                "something practical. Returns whole threads with permalinks to cite. "
                "Parent anecdote, never medical guidance."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The question or topic in natural language.",
                    },
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Synonyms and alternate wordings to widen the search - this "
                            "matters a lot, because matching is keyword-based and parents "
                            "write 'jabs', 'shots' and 'immunisations' for one thing. "
                            "Include brand names where relevant (Tylenol, Calpol, "
                            "Beyfortus, Glutarex)."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "community_practices",
            "description": (
                "Structured counts of what families DID, extracted from every thread "
                "on a topic - not just the ones retrieved. Use this whenever the "
                "question is quantitative ('how many families...', 'what do most "
                "people do...', 'what are the common approaches') or asks for "
                "before/during/after practices. Prefer this over search_community "
                "for counting; search_community cannot count honestly because it "
                "only sees a few threads. Currently only the topic 'vaccination' "
                "has been extracted."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "enum": ["vaccination"],
                        "description": "Extracted topic. Only 'vaccination' exists so far.",
                    },
                    "phase": {
                        "type": "string",
                        "enum": ["before", "during", "after"],
                        "description": "Narrow to one phase. Omit for the full picture.",
                    },
                    "vaccine": {
                        "type": "string",
                        "enum": [
                            "flu", "covid", "mmr", "routine_infant",
                            "rsv_beyfortus_synagis", "varicella", "other", "unspecified",
                        ],
                    },
                    "outcome": {
                        "type": "string",
                        "enum": [
                            "no_issues", "mild_fever", "high_fever", "lethargy_only",
                            "metabolic_crisis", "hospitalised", "declined_vaccine", "unclear",
                        ],
                    },
                },
                "required": ["topic"],
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
- The feeding plan (bottle composition, batch recipe) changes over time; get_recipe_history \
says what was in effect when. Mixed bottles in the log are already split per that recipe.
- The dietitian update / "feeding logs to send": call get_dietitian_update(days) and return its text verbatim (a greeting line is fine). Never rebuild that message from get_day_summary.
- Poop/constipation questions: use get_poop_history (gaps between poops, consistency, notes). \
State gaps in days+hours; a gap of several days is a fact to report, not to diagnose.

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

Community knowledge (search_community / community_practices):
- These search real discussions from a private Facebook group of ~1.4K GA-1 families. \
Use them for lived-experience questions the logs cannot answer: what other parents did, \
what they observed, how they handled something practical.
- NEVER blend the two sources in a way that hides which is which. This baby's own numbers \
come from the log tools; anything from the group is what OTHER families reported. Say which.
- Counting questions ("how many families...", "what do most people do") must use \
community_practices, NOT search_community. Retrieval only sees a few threads, so counting \
from it invents statistics.
- Even with community_practices, these are counts of what families WROTE, never rates. Say \
"9 families described X", never "9% of families" and never "X is common in GA-1".
- Always offer the permalink so the parent can read the original thread themselves.
- This is anecdote from strangers, not clinical evidence. Practices vary widely and much of \
it is years old. Present the RANGE of what families did rather than a single answer, and \
route anything clinical to the metabolic team. Never let group practice become a recommendation.

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
    if name == "get_poop_history":
        from app.services.diapers import diaper_series

        try:
            days = max(1, min(92, int(tool_input.get("days", 7))))
        except (TypeError, ValueError):
            days = 7
        today = effective_day(now, tz_name, day_start)
        series = diaper_series(
            baby.id, today - timedelta(days=days - 1), today, tz_name, day_start, now=now
        )

        def local(dt):
            return to_local(dt, tz_name).strftime("%Y-%m-%d %H:%M") if dt else None

        def gap_text(h):
            if h is None:
                return None
            d, rem = divmod(int(round(h)), 24)
            return f"{d}d {rem}h" if d else f"{rem}h"

        return json.dumps({
            "days": [
                {"day": d.day.isoformat(), "poop": d.poop, "pee": d.pee, "changes": d.changes}
                for d in series.days
            ],
            "poops": [
                {
                    "at": local(p.occurred_at),
                    "since_previous_poop": gap_text(p.gap_hours),
                    "color": p.color,
                    "consistency": p.consistency,
                    "note": p.note,
                }
                for p in series.poops
            ],
            "last_poop_at": local(series.last_poop_at),
            "time_since_last_poop": gap_text(series.hours_since_last_poop),
            "average_gap_between_poops_in_range": gap_text(series.avg_gap_hours),
            "poops_in_range": len(series.poops),
            "longest_gap_in_range": gap_text(series.longest_gap_hours),
            "longest_gap_ended_at": local(series.longest_gap_ended_at),
        })
    if name == "get_recipe_history":
        from app.services import recipes as recipe_svc

        recipes = recipe_svc.list_recipes(family_id, baby.id)
        out = []
        for i, r in enumerate(recipes):
            until = recipes[i + 1].effective_at if i + 1 < len(recipes) else None
            out.append({
                "label": r.label,
                "effective_from": to_local(r.effective_at, tz_name).strftime("%Y-%m-%d %H:%M"),
                "effective_until": (
                    to_local(until, tz_name).strftime("%Y-%m-%d %H:%M") if until else "now"
                ),
                "per_feed": {
                    "breast_milk_ml": r.breast_milk_ml,
                    "batch_formula_ml": r.batch_ml,
                    "prepared_ml": r.prepared_ml,
                },
                "batch": {
                    "powders": [{"name": p.name, "grams": p.grams} for p in r.powders],
                    "final_volume_ml": r.batch_final_volume_ml,
                    "feeds_per_batch": r.feeds_per_batch,
                },
                "top_ups": (
                    {
                        "powders": [{"name": p.name, "grams": p.grams} for p in r.topoff_powders],
                        "water_ml": r.topoff_water_ml,
                        "description": recipe_svc.describe_topoff(r),
                    }
                    if r.has_own_topoff
                    else "more of the batch formula"
                ),
                "feeds_per_day": r.feeds_per_day,
                "source": r.source,
                "notes": r.notes,
            })
        return json.dumps({"recipes": out, "current": out[-1] if out else None})
    if name == "get_dietitian_update":
        from app.services.dietitian import dietitian_report

        try:
            days = max(1, min(14, int(tool_input.get("days", 3))))
        except (TypeError, ValueError):
            return json.dumps({"error": "days must be an integer"})
        report = dietitian_report(family_id, baby, tz_name, day_start, days, now=now)
        return json.dumps({
            "text": report.text,
            "warnings": [w.message for w in report.warnings],
            "days": days,
        })
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
    elif name == "search_community":
        from app.services import community

        return community.search(
            str(tool_input.get("query", "")),
            tool_input.get("keywords") or [],
        )
    elif name == "community_practices":
        from app.services import community

        return community.practices(
            topic=str(tool_input.get("topic", "vaccination")),
            phase=tool_input.get("phase"),
            vaccine=tool_input.get("vaccine"),
            outcome=tool_input.get("outcome"),
        )
    else:
        return json.dumps({"error": f"unknown tool {name}"})

    payload = summary.model_dump(mode="json", exclude={"summary_text"})
    return json.dumps(payload)


COMMUNITY_TOOLS = [t for t in TOOLS if t["function"]["name"].startswith(("search_community", "community_"))]

COMMUNITY_ONLY_RULES = """

COMMUNITY-ONLY MODE (the parent explicitly asked for support-group data only):
- Answer ONLY from search_community / community_practices results. You have no
  access to this baby's logs in this mode, and you must not draw on your own
  general knowledge of GA-1, vaccines, or medicine.
- If the tools return nothing relevant, say plainly that the corpus has nothing on
  this and stop. Do NOT fall back to what you know. An empty answer is correct here.
- Every factual statement must be traceable to a returned thread. Quote or closely
  paraphrase, and give the permalink."""


def _provenance(name: str, args: dict, result: str) -> dict | None:
    """Summarise what a tool actually returned, for the client to display.

    The chat bubble is model-authored text, so a number in it is only ever a
    claim. This record is built from the tool output itself, which lets the app
    show what the data really said next to what the model wrote about it.
    """
    try:
        payload = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        return {"tool": name, "kind": "other"}

    if name == "search_community":
        return {
            "tool": name,
            "kind": "community",
            "query": args.get("query"),
            "threads": [
                {
                    "post_id": t.get("post_id"),
                    "url": t.get("url"),
                    "total_comments": t.get("total_comments"),
                    "excerpt": (t.get("post") or "")[:160],
                }
                for t in payload.get("threads", [])
            ],
        }
    if name == "community_practices":
        return {
            "tool": name,
            "kind": "community",
            "topic": payload.get("topic"),
            "reports": payload.get("reports"),
            "distinct_families": payload.get("distinct_families"),
            "threads_with_extracted_practices": payload.get(
                "threads_with_extracted_practices"
            ),
            "top_practices": {
                phase: payload.get(phase, [])[:8]
                for phase in ("before", "during", "after")
                if payload.get(phase)
            },
            "outcomes": payload.get("outcomes"),
        }
    return {"tool": name, "kind": "baby_logs", "args": args}


def chat(
    baby: Baby,
    tz_name: str,
    parent_name: str,
    messages: list[dict],
    day_start: time = time.min,
    family_id: str = "",
    community_only: bool = False,
    sources_out: list | None = None,
) -> str:
    """Run the tool-use loop and return the assistant's final text reply.

    `sources_out`, if given, is filled with a record of what each tool actually
    returned. `community_only` restricts the model to the support-group corpus.
    """
    client = _client()
    system = _system_prompt(baby, tz_name, parent_name, day_start)
    if community_only:
        system += COMMUNITY_ONLY_RULES
    convo: list[dict] = [{"role": "system", "content": system}, *messages]
    active_tools = COMMUNITY_TOOLS if community_only else TOOLS
    community_used = False

    for round_no in range(MAX_TOOL_ROUNDS + 1):
        kwargs: dict = {}
        # Telling the model "only use the corpus" is not enforcement: asked a
        # straight biochemistry question it answered from its own knowledge with
        # no tool call at all. Forcing a tool call on the first turn makes the
        # corpus the only possible source of a first answer.
        if community_only and round_no == 0:
            kwargs["tool_choice"] = "required"

        response = client.chat.completions.create(
            model=settings.assistant_model,
            max_completion_tokens=3000,
            # gpt-5.5 chat completions requires 'none' when function tools are
            # used (also keeps the tool loop inside the 29s route budget).
            reasoning_effort="none",
            tools=active_tools,
            messages=convo,
            **kwargs,
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            # Hard backstop: in community-only mode an answer that consulted no
            # community tool is the model talking from its own knowledge, which
            # is exactly what this mode exists to prevent. Refuse rather than
            # pass it off as group data.
            if community_only and not community_used:
                return (
                    "I could not find anything about that in the GA-1 support group "
                    "corpus, so I have nothing to report.\n\n"
                    "This mode answers only from what families actually wrote in the "
                    "group. It will not fall back on general knowledge — ask again "
                    "without community-only mode if you want that."
                )
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
            result = _run_tool(
                tc.function.name, args, baby, tz_name, day_start, family_id
            )
            record = _provenance(tc.function.name, args, result)
            # A forced tool call is not evidence the answer came from the corpus:
            # asked a biochemistry question the model dutifully called a tool,
            # ignored the empty-ish result and answered from its own knowledge.
            # Only a call that actually returned content counts.
            if record and record.get("kind") == "community":
                got_threads = bool(record.get("threads"))
                got_reports = bool(record.get("reports"))
                if got_threads or got_reports:
                    community_used = True
            if sources_out is not None and record:
                sources_out.append(record)
            convo.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                }
            )

    return (
        "I wasn't able to finish looking that up — please try asking in a "
        "smaller chunk (e.g. one day at a time)."
    )
