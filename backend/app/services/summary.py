"""Aggregate a window of feeds+events into the Summary model and render the
shareable doctor text (times in the family's timezone)."""

from datetime import date, datetime

from app.models.baby import Baby
from app.models.event import Event
from app.models.feed import Feed, FeedComponentOut
from app.models.summary import (
    BreastMilkBreakdown,
    DiaperBrief,
    EventBrief,
    FeedBrief,
    MedGiven,
    PumpedVsFed,
    PumpingBrief,
    Summary,
    VolumeTargetEval,
    WeightBrief,
)
from app.services.tz import to_local


def summarize_window(
    baby: Baby,
    window_from: datetime,
    window_to: datetime,
    tz_name: str,
    day: date | None = None,
    window_label: str = "",
) -> Summary:
    """Query the timeline and aggregate it — shared by the summary endpoints
    and the AI assistant's tools."""
    from app.repo import keys, logs

    items = logs.query_all_logs(
        baby.id, keys.log_sk_bound(window_from), keys.log_sk_bound(window_to)
    )
    feeds = [
        Feed.model_validate(i) for i in items if i.get("item_type") == keys.LOG_TYPE_FEED
    ]
    events = [
        Event.model_validate(i)
        for i in items
        if i.get("item_type") == keys.LOG_TYPE_EVENT
    ]
    return build_summary(
        baby, feeds, events, window_from, window_to, tz_name,
        day=day, window_label=window_label,
    )


def build_summary(
    baby: Baby,
    feeds: list[Feed],
    events: list[Event],
    window_from: datetime,
    window_to: datetime,
    tz_name: str,
    day: date | None = None,
    window_label: str = "",
) -> Summary:
    if not window_label:
        if day:
            window_label = to_local(window_from, tz_name).strftime("%a %b %-d")
        else:
            hours = round((window_to - window_from).total_seconds() / 3600)
            window_label = f"last {hours}h"

    # Per-kg targets win when a current weight exists (GA1 targets are
    # weight-based and change as the baby grows).
    targets = baby.targets
    lysine_basis = protein_basis = ""
    if baby.current_weight_g:
        kg = round(baby.current_weight_g / 1000, 2)
        updates: dict = {}
        if targets.lysine_mg_per_kg:
            updates["lysine_mg_per_day"] = round(targets.lysine_mg_per_kg * kg, 1)
            lysine_basis = f"{_num(targets.lysine_mg_per_kg)} mg/kg × {_num(kg)} kg"
        if targets.natural_protein_g_per_kg:
            updates["natural_protein_g_per_day"] = round(
                targets.natural_protein_g_per_kg * kg, 2
            )
            protein_basis = f"{_num(targets.natural_protein_g_per_kg)} g/kg × {_num(kg)} kg"
        if updates:
            targets = targets.model_copy(update=updates)

    s = Summary(
        baby_id=baby.id,
        baby_name=baby.name,
        window_from=window_from,
        window_to=window_to,
        day=day,
        targets=targets,
        lysine_target_basis=lysine_basis,
        protein_target_basis=protein_basis,
        breast_milk=BreastMilkBreakdown(),
        window_label=window_label,
    )

    for feed in sorted(feeds, key=lambda f: f.occurred_at):
        s.feed_count += 1
        t = feed.totals
        s.total_ml = round(s.total_ml + t.total_ml, 1)
        s.formula_ml = round(s.formula_ml + t.formula_ml, 1)
        s.formula_scoops += t.formula_scoops
        s.metabolic_formula_ml = round(s.metabolic_formula_ml + t.metabolic_formula_ml, 1)
        s.metabolic_formula_scoops += t.metabolic_formula_scoops
        s.other_ml = round(s.other_ml + t.other_ml, 1)
        s.natural_protein_g = round(s.natural_protein_g + t.natural_protein_g, 2)
        s.lysine_mg = round(s.lysine_mg + t.lysine_mg, 1)

        for comp in feed.components:
            if comp.food_category != "breast_milk":
                continue
            bm = s.breast_milk
            bm.total_ml = round(bm.total_ml + comp.effective_ml, 1)
            if comp.kind == "liquid":
                bm.pumped_ml = round(bm.pumped_ml + comp.effective_ml, 1)
            elif comp.kind == "latch" and comp.is_estimated:
                bm.latch_estimated_ml = round(bm.latch_estimated_ml + comp.effective_ml, 1)
            elif comp.kind == "latch":
                bm.latch_measured_ml = round(bm.latch_measured_ml + comp.effective_ml, 1)

        s.feeds.append(
            FeedBrief(
                id=feed.id,
                occurred_at=feed.occurred_at,
                total_ml=t.total_ml,
                description=describe_components(feed.components),
            )
        )

    for ev in sorted(events, key=lambda e: e.occurred_at):
        if ev.type == "pumping":
            s.pumping_sessions += 1
            s.pumped_output_ml = round(s.pumped_output_ml + (ev.pumped_ml or 0), 1)
            s.pumpings.append(
                PumpingBrief(
                    id=ev.id, occurred_at=ev.occurred_at,
                    pumped_ml=ev.pumped_ml or 0, side=ev.side,
                    duration_minutes=ev.duration_minutes,
                )
            )
        elif ev.type == "diaper":
            s.diapers.changes += 1
            if ev.diaper_kind in ("pee", "both"):
                s.diapers.pee += 1
            if ev.diaper_kind in ("poop", "both"):
                s.diapers.poop += 1
            s.diaper_events.append(
                DiaperBrief(
                    id=ev.id, occurred_at=ev.occurred_at,
                    diaper_kind=ev.diaper_kind or "pee", note=ev.note,
                    color=ev.diaper_color, consistency=ev.diaper_consistency,
                )
            )
        elif ev.type == "weight":
            s.weights.append(
                WeightBrief(id=ev.id, occurred_at=ev.occurred_at, weight_g=ev.weight_g or 0)
            )
        elif ev.type == "medication":
            s.meds.append(
                MedGiven(
                    occurred_at=ev.occurred_at, med_name=ev.med_name or "medication",
                    dose_amount=ev.dose_amount, dose_unit=ev.dose_unit,
                )
            )
        else:
            brief = EventBrief(
                id=ev.id, occurred_at=ev.occurred_at, type=ev.type,
                severity=ev.severity, note=ev.note,
            )
            if ev.type == "spit_up":
                s.spit_ups.append(brief)
            elif ev.type == "vomit":
                s.vomits.append(brief)
            elif ev.type == "fussiness":
                s.fussiness.append(brief)
            else:
                s.notes.append(brief)

    s.pumped_vs_fed = PumpedVsFed(
        pumped_ml=s.pumped_output_ml,
        fed_ml=s.breast_milk.total_ml,
        net_ml=round(s.pumped_output_ml - s.breast_milk.total_ml, 1),
    )

    if s.targets.lysine_mg_per_day:
        s.pct_of_lysine_target = round(100 * s.lysine_mg / s.targets.lysine_mg_per_day, 1)
    if s.targets.natural_protein_g_per_day:
        s.pct_of_protein_target = round(
            100 * s.natural_protein_g / s.targets.natural_protein_g_per_day, 1
        )

    actual_by_category = {
        "breast_milk": s.breast_milk.total_ml,
        "formula": s.formula_ml,
        "metabolic_formula": s.metabolic_formula_ml,
    }
    for vt in s.targets.volume_targets:
        actual = actual_by_category[vt.category]
        if vt.direction == "min":
            status = "met" if actual >= vt.ml_per_day else "under"
        else:
            status = "met" if actual <= vt.ml_per_day else "over"
        s.volume_targets.append(
            VolumeTargetEval(
                category=vt.category,
                direction=vt.direction,
                target_ml=vt.ml_per_day,
                actual_ml=actual,
                estimated_ml=(
                    s.breast_milk.latch_estimated_ml if vt.category == "breast_milk" else 0
                ),
                status=status,
            )
        )

    s.summary_text = render_text(s, tz_name)
    return s


def describe_components(components: list[FeedComponentOut]) -> str:
    parts = []
    for c in components:
        if c.kind == "liquid":
            parts.append(f"{_num(c.volume_ml)}ml {c.food_name}")
        elif c.kind == "powder":
            parts.append(f"{_num(c.scoops)} scoop {c.food_name}")
        else:
            approx = "~" if c.is_estimated else ""
            parts.append(
                f"{_num(c.minutes)}min latch ({approx}{_num(c.effective_ml)}ml)"
            )
    return " + ".join(parts)


_CATEGORY_LABEL = {
    "breast_milk": "Breast milk",
    "formula": "Formula",
    "metabolic_formula": "Metabolic formula",
}


def render_text(s: Summary, tz_name: str) -> str:
    lines: list[str] = []
    as_of = to_local(s.window_to, tz_name).strftime("%b %-d, %-I:%M %p")
    lines.append(f"{s.baby_name} — {s.window_label} (as of {as_of})")

    lines.append(f"Feeds: {s.feed_count} · total {_num(s.total_ml)} ml")
    bm = s.breast_milk
    if bm.total_ml:
        detail = [f"pumped {_num(bm.pumped_ml)}"] if bm.pumped_ml else []
        if bm.latch_estimated_ml:
            detail.append(f"latch est {_num(bm.latch_estimated_ml)}")
        if bm.latch_measured_ml:
            detail.append(f"latch weighed {_num(bm.latch_measured_ml)}")
        lines.append(f"• Breast milk {_num(bm.total_ml)} ml ({' · '.join(detail)})")
    if s.formula_ml or s.formula_scoops:
        extra = f" + {_num(s.formula_scoops)} scoops" if s.formula_scoops else ""
        lines.append(f"• Formula {_num(s.formula_ml)} ml{extra}")
    if s.metabolic_formula_ml or s.metabolic_formula_scoops:
        bits = []
        if s.metabolic_formula_ml:
            bits.append(f"{_num(s.metabolic_formula_ml)} ml")
        if s.metabolic_formula_scoops:
            bits.append(f"{_num(s.metabolic_formula_scoops)} scoops")
        lines.append(f"• Metabolic formula {' + '.join(bits)}")

    protein_line = _target_line("Natural protein", s.natural_protein_g, "g",
                                s.targets.natural_protein_g_per_day, s.pct_of_protein_target)
    if s.protein_target_basis:
        protein_line += f" [{s.protein_target_basis}]"
    lines.append(protein_line)
    lysine_line = _target_line("Lysine", s.lysine_mg, "mg",
                               s.targets.lysine_mg_per_day, s.pct_of_lysine_target)
    if s.lysine_target_basis:
        lysine_line += f" [{s.lysine_target_basis}]"
    lines.append(lysine_line)

    for vt in s.volume_targets:
        label = _CATEGORY_LABEL[vt.category]
        gap = round(vt.target_ml - vt.actual_ml, 1)
        if vt.direction == "min":
            tail = "target met" if vt.status == "met" else f"{_num(gap)} to go"
            lines.append(f"{label}: {_num(vt.actual_ml)} ml of min {_num(vt.target_ml)} ({tail})")
        else:
            tail = f"over by {_num(-gap)}" if vt.status == "over" else f"{_num(gap)} left"
            lines.append(f"{label}: {_num(vt.actual_ml)} ml of max {_num(vt.target_ml)} ({tail})")

    if s.weights:
        w = s.weights[-1]
        lines.append(
            f"Weight: {_lb_oz(w.weight_g)} / {_num(round(w.weight_g / 1000, 2))} kg "
            f"({_t(w.occurred_at, tz_name)})"
        )
    if s.pumping_sessions:
        lines.append(
            f"Pumped: {_num(s.pumped_output_ml)} ml ({s.pumping_sessions} sessions) · "
            f"breast milk fed {_num(s.pumped_vs_fed.fed_ml)} ml this window"
        )
    if s.diapers.changes:
        lines.append(
            f"Diapers: {s.diapers.changes} (pee {s.diapers.pee} · poop {s.diapers.poop})"
        )

    if s.meds:
        by_med: dict[str, list[str]] = {}
        for m in s.meds:
            dose = f" {_num(m.dose_amount)} {m.dose_unit}" if m.dose_amount else ""
            by_med.setdefault(f"{m.med_name}{dose}", []).append(_t(m.occurred_at, tz_name))
        lines.append("Meds:")
        for label, times in by_med.items():
            lines.append(f"• {label} — {', '.join(times)}")

    for title, evs in (("Spit-ups", s.spit_ups), ("Vomits", s.vomits), ("Fussy", s.fussiness)):
        if evs:
            items = ", ".join(
                f"{e.severity + ' ' if e.severity else ''}{_t(e.occurred_at, tz_name)}"
                for e in evs
            )
            lines.append(f"{title}: {len(evs)} ({items})")

    for n in s.notes:
        lines.append(f"Note {_t(n.occurred_at, tz_name)}: {n.note or ''}".rstrip())

    return "\n".join(lines)


def _target_line(label: str, value: float, unit: str, target: float | None,
                 pct: float | None) -> str:
    if target:
        return f"{label}: {_num(value)} {unit} of {_num(target)} {unit} target ({_num(pct or 0)}%)"
    return f"{label}: {_num(value)} {unit}"


def _t(dt: datetime, tz_name: str) -> str:
    return to_local(dt, tz_name).strftime("%-I:%M %p")


def _num(x: float | None) -> str:
    if x is None:
        return "0"
    return str(int(x)) if float(x) == int(x) else str(round(x, 2))


_G_PER_OZ = 28.349523125


def _lb_oz(grams: float) -> str:
    """Grams → '6 lb 6 oz' — how the parents (and US peds) talk about weight;
    storage and per-kg target math stay metric."""
    total_oz = grams / _G_PER_OZ
    lb = int(total_oz // 16)
    oz = round(total_oz - lb * 16, 1)
    if oz >= 16:
        lb, oz = lb + 1, 0
    return f"{lb} lb {_num(oz)} oz" if oz else f"{lb} lb"
