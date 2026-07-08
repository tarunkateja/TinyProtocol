from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

VolumeCategory = Literal["breast_milk", "formula", "metabolic_formula"]


class VolumeTarget(BaseModel):
    """A per-day volume goal for one source, e.g. max 400 ml breast milk or
    min 120 ml GA1 formula. Only liquid/latch ml count — powder scoops don't."""

    category: VolumeCategory
    direction: Literal["min", "max"]
    ml_per_day: float = Field(gt=0)


class Targets(BaseModel):
    """Daily intake targets from the metabolic team. Absolute per-day values."""

    lysine_mg_per_day: Optional[float] = Field(None, gt=0)
    natural_protein_g_per_day: Optional[float] = Field(None, gt=0)
    # Per-kg targets (GA1 targets are weight-based, e.g. lysine 65-100 mg/kg/day
    # at 0-6 months). When set AND a current weight exists, these win over the
    # absolute values above.
    lysine_mg_per_kg: Optional[float] = Field(None, gt=0)
    natural_protein_g_per_kg: Optional[float] = Field(None, gt=0)
    volume_targets: list[VolumeTarget] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def _check_volume_targets(self) -> "Targets":
        seen: dict[tuple[str, str], float] = {}
        for t in self.volume_targets:
            key = (t.category, t.direction)
            if key in seen:
                raise ValueError(f"duplicate volume target for {t.category} {t.direction}")
            seen[key] = t.ml_per_day
        for cat in {t.category for t in self.volume_targets}:
            lo, hi = seen.get((cat, "min")), seen.get((cat, "max"))
            if lo is not None and hi is not None and lo > hi:
                raise ValueError(f"{cat}: min target exceeds max target")
        return self


class BabyIn(BaseModel):
    name: str = Field(min_length=1)
    date_of_birth: Optional[date] = None
    sex: Optional[str] = None
    birth_weight_g: Optional[int] = Field(None, gt=0)
    # e.g. ["GA1"]. Empty for babies with no metabolic condition.
    conditions: list[str] = Field(default_factory=list)
    # Prefills the latch estimate; editable on every feed.
    default_latch_rate_ml_per_10min: float = Field(20, ge=0)
    targets: Targets = Field(default_factory=Targets)
    notes: Optional[str] = None


class BabyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    date_of_birth: Optional[date] = None
    sex: Optional[str] = None
    birth_weight_g: Optional[int] = Field(None, gt=0)
    conditions: Optional[list[str]] = None
    default_latch_rate_ml_per_10min: Optional[float] = Field(None, ge=0)
    targets: Optional[Targets] = None
    notes: Optional[str] = None


class Baby(BabyIn):
    id: str
    created_at: datetime
    # Maintained automatically from the newest logged weight event.
    current_weight_g: Optional[float] = None
