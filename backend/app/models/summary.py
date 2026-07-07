from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from app.models.baby import Targets
from app.models.event import EventType, Severity
from app.models.food import DoseUnit


class BreastMilkBreakdown(BaseModel):
    pumped_ml: float = 0
    latch_estimated_ml: float = 0
    latch_measured_ml: float = 0
    total_ml: float = 0


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
    pct_of_lysine_target: Optional[float] = None
    pct_of_protein_target: Optional[float] = None

    feeds: list[FeedBrief] = []
    spit_ups: list[EventBrief] = []
    vomits: list[EventBrief] = []
    fussiness: list[EventBrief] = []
    meds: list[MedGiven] = []
    notes: list[EventBrief] = []

    # Server-rendered shareable text (times in the family's timezone).
    summary_text: str = ""
