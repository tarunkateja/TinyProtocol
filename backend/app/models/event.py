from datetime import datetime
from typing import Literal, Optional

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from app.models.food import DoseUnit

EventType = Literal[
    "spit_up", "vomit", "fussiness", "medication", "note", "pumping", "diaper"
]
Severity = Literal["small", "medium", "large"]
PumpSide = Literal["left", "right", "both"]
DiaperKind = Literal["pee", "poop", "both"]


class _EventFields(BaseModel):
    """Shared shape + per-type coherence checks (run on create AND update)."""

    type: EventType
    severity: Optional[Severity] = None  # spit_up / vomit
    related_feed_id: Optional[str] = None  # e.g. "spit up after this feed"
    med_name: Optional[str] = None  # medication
    dose_amount: Optional[float] = Field(None, gt=0)
    dose_unit: Optional[DoseUnit] = None
    pumped_ml: Optional[float] = Field(None, gt=0)  # pumping
    side: Optional[PumpSide] = None
    duration_minutes: Optional[float] = Field(None, gt=0)
    diaper_kind: Optional[DiaperKind] = None  # diaper
    note: Optional[str] = None

    @model_validator(mode="after")
    def _check_type_fields(self) -> "_EventFields":
        if self.type == "medication" and not self.med_name:
            raise ValueError("medication events need med_name")
        if self.type == "pumping" and self.pumped_ml is None:
            raise ValueError("pumping events need pumped_ml")
        if self.type == "diaper" and self.diaper_kind is None:
            raise ValueError("diaper events need diaper_kind")
        return self


class EventIn(_EventFields):
    occurred_at: AwareDatetime


class EventUpdate(BaseModel):
    occurred_at: Optional[AwareDatetime] = None
    severity: Optional[Severity] = None
    related_feed_id: Optional[str] = None
    med_name: Optional[str] = None
    dose_amount: Optional[float] = Field(None, gt=0)
    dose_unit: Optional[DoseUnit] = None
    pumped_ml: Optional[float] = Field(None, gt=0)
    side: Optional[PumpSide] = None
    duration_minutes: Optional[float] = Field(None, gt=0)
    diaper_kind: Optional[DiaperKind] = None
    note: Optional[str] = None


class Event(_EventFields):
    item_type: Literal["EVENT"] = "EVENT"
    id: str
    baby_id: str
    occurred_at: datetime
    created_at: datetime
