from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel

from app.models.baby import Targets, VolumeCategory
from app.models.event import DiaperKind, EventType, PumpSide, Severity
from app.models.food import DoseUnit


class BreastMilkBreakdown(BaseModel):
    # NOTE: pumped_ml here means pumped milk FED by bottle in this window —
    # pumping *output* is Summary.pumped_output_ml.
    pumped_ml: float = 0
    latch_estimated_ml: float = 0
    latch_measured_ml: float = 0
    total_ml: float = 0


class PumpedVsFed(BaseModel):
    """Window-scoped flow, not stash inventory: milk pumped today is often
    fed tomorrow."""

    pumped_ml: float = 0
    fed_ml: float = 0
    net_ml: float = 0


class DiaperCounts(BaseModel):
    pee: int = 0  # 'both' increments pee AND poop
    poop: int = 0
    changes: int = 0


class PumpingBrief(BaseModel):
    id: str
    occurred_at: datetime
    pumped_ml: float
    side: Optional[PumpSide] = None
    duration_minutes: Optional[float] = None


class DiaperBrief(BaseModel):
    id: str
    occurred_at: datetime
    diaper_kind: DiaperKind
    color: Optional[str] = None
    consistency: Optional[str] = None
    note: Optional[str] = None


class WeightBrief(BaseModel):
    id: str
    occurred_at: datetime
    weight_g: float


class VolumeTargetEval(BaseModel):
    category: VolumeCategory
    direction: Literal["min", "max"]
    target_ml: float
    actual_ml: float
    estimated_ml: float = 0  # the latch-estimate share of actual_ml
    status: Literal["under", "met", "over"]


class FeedBrief(BaseModel):
    id: str
    occurred_at: datetime
    total_ml: float
    description: str  # e.g. "60ml breast milk + 1 scoop GA1 formula"


class EventBrief(BaseModel):
    id: str
    occurred_at: datetime
    type: EventType
    severity: Optional[Severity] = None
    note: Optional[str] = None


class MedGiven(BaseModel):
    occurred_at: datetime
    med_name: str
    dose_amount: Optional[float] = None
    dose_unit: Optional[DoseUnit] = None


class Summary(BaseModel):
    """Aggregated window of feeds+events. Used for daily totals AND the 24h doctor summary."""

    baby_id: str
    baby_name: str
    window_from: datetime
    window_to: datetime
    day: Optional[date] = None  # set when this is a local-day bucket

    feed_count: int = 0
    total_ml: float = 0
    breast_milk: BreastMilkBreakdown = BreastMilkBreakdown()
    formula_ml: float = 0
    formula_scoops: float = 0
    metabolic_formula_ml: float = 0
    metabolic_formula_scoops: float = 0
    other_ml: float = 0

    natural_protein_g: float = 0
    lysine_mg: float = 0
    targets: Targets = Targets()
    # Set when the target came from per-kg × current weight.
    lysine_target_basis: str = ""
    protein_target_basis: str = ""
    pct_of_lysine_target: Optional[float] = None
    pct_of_protein_target: Optional[float] = None
    volume_targets: list[VolumeTargetEval] = []

    pumped_output_ml: float = 0
    pumping_sessions: int = 0
    pumped_vs_fed: PumpedVsFed = PumpedVsFed()
    diapers: DiaperCounts = DiaperCounts()

    feeds: list[FeedBrief] = []
    weights: list[WeightBrief] = []
    pumpings: list[PumpingBrief] = []
    diaper_events: list[DiaperBrief] = []
    spit_ups: list[EventBrief] = []
    vomits: list[EventBrief] = []
    fussiness: list[EventBrief] = []
    meds: list[MedGiven] = []
    notes: list[EventBrief] = []
    # Human label for the window, e.g. "last 24h" or "since 7:00 AM".
    window_label: str = ""

    # Server-rendered shareable text (times in the family's timezone).
    summary_text: str = ""


class DailyIntakeDay(BaseModel):
    """One local day's intake by source, for the trends chart."""

    day: date
    feed_count: int = 0
    total_ml: float = 0
    breast_milk_ml: float = 0  # includes latch estimates
    formula_ml: float = 0
    metabolic_formula_ml: float = 0
    other_ml: float = 0


class DailyIntakeSeries(BaseModel):
    baby_id: str
    from_day: date
    to_day: date
    days: list[DailyIntakeDay]


class DiaperDay(BaseModel):
    """One local day's diaper counts ('both' counts as pee AND poop)."""

    day: date
    changes: int = 0
    pee: int = 0
    poop: int = 0


class PoopEvent(BaseModel):
    id: str
    occurred_at: datetime
    diaper_kind: DiaperKind
    color: Optional[str] = None
    consistency: Optional[str] = None
    note: Optional[str] = None
    # Hours since the previous poop (None for the first one we know of).
    gap_hours: Optional[float] = None


class DiaperSeries(BaseModel):
    """Per-day diaper counts plus every poop with the gap before it — the
    constipation view: how often, how long between, what it looked like."""

    baby_id: str
    from_day: date
    to_day: date
    days: list[DiaperDay]
    poops: list[PoopEvent]  # ascending, within the range
    last_poop_at: Optional[datetime] = None  # newest poop up to now (may predate the range)
    hours_since_last_poop: Optional[float] = None
    longest_gap_hours: Optional[float] = None  # among poops in the range
    longest_gap_ended_at: Optional[datetime] = None
    # Mean hours between consecutive poops, over the poops in the range.
    avg_gap_hours: Optional[float] = None


class WeightPoint(BaseModel):
    id: str
    occurred_at: datetime
    weight_g: float


class WeightSeries(BaseModel):
    """All weight check-ins (ascending), plus birth context for the chart."""

    baby_id: str
    date_of_birth: Optional[date] = None
    birth_weight_g: Optional[int] = None
    weights: list[WeightPoint]
