"""Aggregate a window of feeds+events into the Summary model and render the
shareable doctor text (times in the family's timezone)."""

from datetime import date, datetime

from app.models.baby import Baby
from app.models.event import Event
from app.models.feed import Feed, FeedComponentOut
from app.models.summary import (
    BreastMilkBreakdown,
    EventBrief,
    FeedBrief,
    MedGiven,
    Summary,
)
from app.services.tz import to_local


def build_summary(
    baby: Baby,
    feeds: list[Feed],
    events: list[Event],
    window_from: datetime,
    window_to: datetime,
    tz_name: str,
    day: date | None = None,
) -> Summary:
    s = Summary(
        baby_id=baby.id,
        baby_name=baby.name,
        window_from=window_from,
        window_to=window_to,
        day=day,
        targets=baby.targets,
        breast_milk=BreastMilkBreakdown(),
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
        elif ev.type == "medication":
            s.meds.append(
                MedGiven(
                    occurred_at=ev.occurred_at, med_name=ev.med_name or "medication",
                    dose_amount=ev.dose_amount, dose_unit=ev.dose_unit,
                )
            )
        else:
            s.notes.append(brief)

    if s.targets.lysine_mg_per_day:
        s.pct_of_lysine_target = round(100 * s.lysine_mg / s.targets.lysine_mg_per_day, 1)
    if s.targets.natural_protein_g_per_day:
        s.pct_of_protein_target = round(
            100 * s.natural_protein_g / s.targets.natural_protein_g_per_day, 1
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


def render_text(s: Summary, tz_name: str) -> str:
    lines: list[str] = []
    if s.day:
        header = to_local(s.window_from, tz_name).strftime("%a %b %-d")
        lines.append(f"{s.baby_name} — {header}")
    else:
        hours = round((s.window_to - s.window_from).total_seconds() / 3600)
        as_of = to_local(s.window_to, tz_name).strftime("%b %-d, %-I:%M %p")
        lines.append(f"{s.baby_name} — last {hours}h (as of {as_of})")

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

    lines.append(_target_line("Natural protein", s.natural_protein_g, "g",
                              s.targets.natural_protein_g_per_day, s.pct_of_protein_target))
    lines.append(_target_line("Lysine", s.lysine_mg, "mg",
                              s.targets.lysine_mg_per_day, s.pct_of_lysine_target))

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
