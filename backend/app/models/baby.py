from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class Targets(BaseModel):
    """Daily intake targets from the metabolic team. Absolute per-day values."""

    lysine_mg_per_day: Optional[float] = Field(None, gt=0)
    natural_protein_g_per_day: Optional[float] = Field(None, gt=0)


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
