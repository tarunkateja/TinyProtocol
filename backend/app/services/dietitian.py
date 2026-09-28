"""The dietitian update: the exact message the parents paste into MyChart
for the metabolic dietitian — one section per family day (8 AM → 8 AM),
one bullet per feed, no breast-milk/batch split, one total line per day,
then a "This morning" section up to send time.

Format (set by the parents with the dietitian, September 2026):

    Monday 9/7
      - 9:00 AM — 90 ml prepared mix (large spit up)
      - 12:10 PM — 100 ml (90 ml prepared mix + 10 ml top-off)
      - 3:05 PM — 20 ml Pro-Phree top-up
    Total: 655 ml (400.2 ml breast milk).

Lean on purpose: the dietitian tracks against the plan and knows the recipe,
so nothing here explains what the mix is, and no lysine/protein/meds/diaper
lines appear. Anything that needs a human look before sending (pending
Huckleberry imports, over-size bottles, likely mislabels, empty days) is a
warning next to the text, never a line inside it.
"""

import math
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from app.models.baby import Baby
from app.models.dietitian import DietitianReport, ReportLine, ReportSection, ReportWarning
from app.models.event import Event
from app.models.feed import Feed
from app.models.recipe import Recipe
from app.services import recipes as recipe_svc
from app.services.tz import day_window, effective_day, to_local

# A standalone formula-only bottle this big is often a mislabeled mix.
_BIG_FORMULA_ML = 60


def dietitian_report(
    family_id: str,
    baby: Baby,
    tz_name: str,
    day_start: time,
    days: int,
    now: Optional[datetime] = None,
    include_notes: bool = True,
) -> DietitianReport:
    """`days` full family days before today, plus today so far. Notes are
    the parent's Huckleberry/feed notes in parentheses; they can run long."""
    from app.repo import family_items, keys, logs
    from app.services.huckleberry import _normalize_hb_key

    now = now or datetime.now(timezone.utc)
    today = effective_day(now, tz_name, day_start)
    first = today - timedelta(days=days)
    window_from, _ = day_window(first, tz_name, day_start)

    items = logs.query_all_logs(
        baby.id, keys.log_sk_bound(window_from), keys.log_sk_bound(now)
    )
    feeds: list[tuple[Feed, dict]] = []
    weights: list[Event] = []
    for raw in items:
        if raw.get("item_type") == keys.LOG_TYPE_FEED:
            feeds.append((Feed.model_validate(raw), raw))
        elif raw.get("item_type") == keys.LOG_TYPE_EVENT:
            ev = Event.model_validate(raw)
            if ev.type == "weight" and ev.weight_g:
                weights.append(ev)

    recipes = recipe_svc.list_recipes(family_id, baby.id)
    topup_labels = _topup_labels(recipes)
    imports = {
        _normalize_hb_key(i["hb_key"]): i
        for i in family_items.list_by_prefix(family_id, f"HBIMPORT#{baby.id}#")
        if i.get("hb_key")
    }

    def bucket(dt: datetime) -> date:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return effective_day(dt, tz_name, day_start)

    by_day: dict[date, list[tuple[Feed, dict]]] = {}
    for feed, raw in feeds:
        by_day.setdefault(bucket(feed.occurred_at), []).append((feed, raw))
    weight_by_day: dict[date, Event] = {}
    for ev in weights:
        weight_by_day[bucket(ev.occurred_at)] = ev  # last one of the day wins

    warnings: list[ReportWarning] = []
    sections: list[ReportSection] = []
    for i in range(days):
        d = first + timedelta(days=i)
        wf, wt = day_window(d, tz_name, day_start)
        sections.append(
            _section(
                d, _day_label(d), wf, wt, by_day.get(d, []), weight_by_day.get(d),
                recipes, topup_labels, imports, tz_name, warnings, partial=False,
                include_notes=include_notes,
            )
        )

    wf_today, _ = day_window(today, tz_name, day_start)
    local_now = to_local(now, tz_name)
    if to_local(wf_today, tz_name).date() == local_now.date() and local_now.hour < 12:
        label = "This morning"
    else:
        label = f"{_day_label(today)} (so far)"
    partial = _section(
        today, label, wf_today, now, by_day.get(today, []), weight_by_day.get(today),
        recipes, topup_labels, imports, tz_name, warnings, partial=True,
        include_notes=include_notes,
    )
    if partial.feed_count:
        sections.append(partial)

    _import_warnings(imports, feeds, window_from, now, tz_name, day_start, warnings)
    warnings.sort(key=lambda w: (w.day.isoformat(), (w.at or datetime.min.replace(tzinfo=timezone.utc)).isoformat()))

    return DietitianReport(
        baby_id=baby.id,
        baby_name=baby.name,
        days=days,
        generated_at=now,
        window_from=window_from,
        window_to=now,
        sections=sections,
        warnings=warnings,
        text="\n\n".join(s.text for s in sections),
    )


# --------------------------------------------------------------------------- #
# One day
# --------------------------------------------------------------------------- #
def _section(
    day: date,
    label: str,
    window_from: datetime,
    window_to: datetime,
    day_feeds: list[tuple[Feed, dict]],
    weight: Optional[Event],
    recipes: list[Recipe],
    topup_labels: dict[str, str],
    imports: dict[str, dict],
    tz_name: str,
    warnings: list[ReportWarning],
    partial: bool,
    include_notes: bool = True,
) -> ReportSection:
    from app.services.huckleberry import _normalize_hb_key

    s = ReportSection(
        day=day, label=label, partial=partial,
        window_from=window_from, window_to=window_to,
        weight_g=weight.weight_g if weight else None,
    )
    described: list[tuple[Feed, str, Optional[str]]] = []
    for feed, raw in sorted(day_feeds, key=lambda fr: fr[0].occurred_at):
        recipe = recipe_svc.recipe_in_effect(recipes, feed.occurred_at)
        parts = _classify(feed, topup_labels)
        text = _feed_text(feed, parts, recipe)
        note = feed.notes if include_notes else None
        if include_notes and not note and raw.get("hb_key"):
            imp = imports.get(_normalize_hb_key(raw["hb_key"]))
            note = imp.get("notes") if imp else None
        described.append((feed, text, _clean_note(note)))
        _feed_warnings(feed, parts, recipe, day, tz_name, warnings)

        s.feed_count += 1
        t = feed.totals
        s.total_ml = _r1(s.total_ml + t.total_ml)
        s.breast_milk_ml = _r1(s.breast_milk_ml + t.breast_milk_ml)
        s.batch_ml = _r1(s.batch_ml + parts["batch"])
        s.topup_ml = _r1(s.topup_ml + sum(parts["topups"].values()))

    # Feeds logged at the same minute are one bottle split across two
    # Huckleberry entries ("70 ml prepared mix + 20 ml breast milk").
    for group in _group_same_minute(described, tz_name):
        texts = " + ".join(t for _, t, _ in group)
        notes = [n for _, _, n in group if n]
        if notes:
            texts += f" ({'; '.join(dict.fromkeys(notes))})"
        s.lines.append(
            ReportLine(at=group[0][0].occurred_at, text=texts, feed_ids=[f.id for f, _, _ in group])
        )

    if not partial and not s.feed_count:
        warnings.append(ReportWarning(day=day, message=f"{label}: no feeds logged"))

    s.text = _render(s, tz_name)
    return s


def _render(s: ReportSection, tz_name: str) -> str:
    lines = [s.label]
    if s.lines:
        for line in s.lines:
            lines.append(f"  - {_t(line.at, tz_name)} — {line.text}")
    else:
        lines.append("  - nothing logged")
    if not s.partial and s.feed_count:
        lines.append(f"Total: {_n(s.total_ml)} ml ({_n(s.breast_milk_ml)} ml breast milk).")
    if s.weight_g:
        lines.append(f"Weight: {_n(round(s.weight_g / 1000, 3))} kg")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# One feed
# --------------------------------------------------------------------------- #
def _classify(feed: Feed, topup_labels: dict[str, str]) -> dict:
    """Split a feed's components into what the dietitian message names:
    breast milk, prepared batch, the recipe's own top-up food, nursing."""
    parts: dict = {"bm": 0.0, "batch": 0.0, "topups": {}, "latch": [], "other": []}
    for c in feed.components:
        if c.kind == "latch":
            parts["latch"].append(c)
        elif c.kind == "powder":
            parts["other"].append(f"{_n(c.scoops)} scoop {c.food_name}")
        elif c.food_category == "breast_milk":
            parts["bm"] = _r1(parts["bm"] + c.volume_ml)
        elif c.food_id in topup_labels:
            label = topup_labels[c.food_id]
            parts["topups"][label] = _r1(parts["topups"].get(label, 0) + c.volume_ml)
        elif c.food_category in ("formula", "metabolic_formula"):
            parts["batch"] = _r1(parts["batch"] + c.volume_ml)
        else:
            parts["other"].append(f"{_n(c.volume_ml)} ml {c.food_name}")
    return parts


def _feed_text(feed: Feed, parts: dict, recipe: Optional[Recipe]) -> str:
    bm, batch = parts["bm"], parts["batch"]
    mix = _r1(bm + batch)
    pieces: list[str] = []
    if bm > 0 and batch > 0:
        prepared = recipe.prepared_ml if recipe else None
        if prepared and mix > prepared + 0.05:
            # A full bottle plus a top-off from the batch in the same entry.
            pieces.append(f"{_n(prepared)} ml prepared mix")
            pieces.append(f"{_n(mix - prepared)} ml top-off")
        else:
            pieces.append(f"{_n(mix)} ml prepared mix")
    elif bm > 0:
        pieces.append(f"{_n(bm)} ml breast milk")
    elif batch > 0:
        pieces.append(f"{_n(batch)} ml top-off")
    for label, ml in parts["topups"].items():
        pieces.append(f"{_n(ml)} ml {label}")
    for c in parts["latch"]:
        approx = "~" if c.is_estimated else ""
        pieces.append(f"{_n(c.minutes)} min nursing ({approx}{_n(c.effective_ml)} ml)")
    pieces.extend(parts["other"])
    if len(pieces) == 1:
        return pieces[0]
    return f"{_n(feed.totals.total_ml)} ml ({' + '.join(pieces)})"


def _feed_warnings(
    feed: Feed, parts: dict, recipe: Optional[Recipe], day: date, tz_name: str,
    warnings: list[ReportWarning],
) -> None:
    when = _when(feed.occurred_at, tz_name)
    bm, batch = parts["bm"], parts["batch"]
    prepared = recipe.prepared_ml if recipe else None
    if bm > 0 and batch > 0 and prepared and bm + batch > prepared + 0.05:
        warnings.append(ReportWarning(
            day=day, at=feed.occurred_at,
            message=(
                f"{when}: {_n(bm + batch)} ml logged vs the {_n(prepared)} ml bottle — "
                f"shown as a {_n(bm + batch - prepared)} ml top-off; confirm what the extra was"
            ),
        ))
    elif batch > 0 and bm == 0 and batch >= _BIG_FORMULA_ML:
        warnings.append(ReportWarning(
            day=day, at=feed.occurred_at,
            message=f"{when}: {_n(batch)} ml formula-only bottle — a mislabeled mix?",
        ))
    elif bm > 0 and batch == 0 and prepared and abs(bm - prepared) < 0.5:
        warnings.append(ReportWarning(
            day=day, at=feed.occurred_at,
            message=(
                f"{when}: {_n(bm)} ml breast-milk-only bottle is exactly the prepared "
                f"volume — a mislabeled mix?"
            ),
        ))


def _import_warnings(
    imports: dict[str, dict],
    feeds: list[tuple[Feed, dict]],
    window_from: datetime,
    window_to: datetime,
    tz_name: str,
    day_start: time,
    warnings: list[ReportWarning],
) -> None:
    """Huckleberry rows that mean the log isn't final yet."""
    feed_ids = {f.id for f, _ in feeds}
    lo, hi = window_from.isoformat(), window_to.isoformat()
    for imp in imports.values():
        if imp.get("mode") not in ("bottle", "breast"):
            continue
        at = imp.get("occurred_at")
        if not at:
            continue
        dt = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if not (window_from <= dt < window_to):
            continue
        day = effective_day(dt, tz_name, day_start)
        what = (
            f"{_n(imp['amount_ml'])} ml {imp.get('bottle_type') or 'bottle'}"
            if imp.get("amount_ml") is not None
            else f"{_n(imp.get('minutes'))} min nursing"
        )
        if imp.get("status") == "pending":
            warnings.append(ReportWarning(
                day=day, at=dt,
                message=f"{_when(dt, tz_name)}: {what} still pending in Huckleberry review",
            ))
        elif imp.get("status") == "deleted_upstream" and imp.get("feed_id") in feed_ids:
            warnings.append(ReportWarning(
                day=day, at=dt,
                message=(
                    f"{_when(dt, tz_name)}: {what} was deleted in Huckleberry but is still "
                    f"in the log (re-logged with a new amount?)"
                ),
            ))


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _topup_labels(recipes: list[Recipe]) -> dict[str, str]:
    """food_id -> 'Pro-Phree top-up' for every recipe's own top-up food."""
    labels: dict[str, str] = {}
    for r in recipes:
        if not r.topoff_food_id:
            continue
        if r.topoff_powders:
            labels[r.topoff_food_id] = " + ".join(p.name for p in r.topoff_powders) + " top-up"
        else:
            labels.setdefault(r.topoff_food_id, "top-up")
    return labels


def _group_same_minute(
    described: list[tuple[Feed, str, Optional[str]]], tz_name: str
) -> list[list[tuple[Feed, str, Optional[str]]]]:
    groups: list[list] = []
    last_minute = None
    for item in described:
        minute = to_local(item[0].occurred_at, tz_name).strftime("%Y-%m-%d %H:%M")
        if groups and minute == last_minute:
            groups[-1].append(item)
        else:
            groups.append([item])
            last_minute = minute
    return groups


def _clean_note(note: Optional[str]) -> Optional[str]:
    if not note:
        return None
    cleaned = re.sub(r"\s+", " ", note).strip().strip("()").strip()
    return cleaned or None


def _day_label(d: date) -> str:
    return d.strftime("%A %-m/%-d")


def _t(dt: datetime, tz_name: str) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return to_local(dt, tz_name).strftime("%-I:%M %p")


def _when(dt: datetime, tz_name: str) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return to_local(dt, tz_name).strftime("%a %-m/%-d %-I:%M %p")


def _r1(x: float) -> float:
    """Round half-up to 0.1 (matches the recipe split rounding)."""
    return math.floor(x * 10 + 0.5) / 10


def _n(x: Optional[float]) -> str:
    if x is None:
        return "0"
    x = round(float(x), 3)
    return str(int(x)) if x == int(x) else f"{x:g}"
