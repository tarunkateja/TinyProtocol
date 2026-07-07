from datetime import datetime
from typing import Literal, Optional

from pydantic import AwareDatetime, BaseModel, model_validator

from app.models.food import DoseUnit

EventType = Literal["spit_up", "vomit", "fussiness", "medication", "note"]
Severity = Literal["small", "medium", "large"]


class EventIn(BaseModel):
    occurred_at: AwareDatetime
    type: EventType
    severity: Optional[Severity] = None  # spit_up / vomit
    related_feed_id: Optional[str] = None  # e.g. "spit up after this feed"
    med_name: Optional[str] = None  # medication
    dose_amount: Optional[float] = None
    dose_unit: Optional[DoseUnit] = None
    note: Optional[str] = None

    @model_validator(mode="after")
    def _check_medication(self) -> "EventIn":
        if self.type == "medication" and not self.med_name:
            raise ValueError("medication events need med_name")
        return self


class EventUpdate(BaseModel):
    occurred_at: Optional[AwareDatetime] = None
    severity: Optional[Severity] = None
    related_feed_id: Optional[str] = None
    med_name: Optional[str] = None
    dose_amount: Optional[float] = None
    dose_unit: Optional[DoseUnit] = None
    note: Optional[str] = None


class Event(BaseModel):
    item_type: Literal["EVENT"] = "EVENT"
    id: str
    baby_id: str
    occurred_at: datetime
    type: EventType
    severity: Optional[Severity] = None
    related_feed_id: Optional[str] = None
    med_name: Optional[str] = None
    dose_amount: Optional[float] = None
    dose_unit: Optional[DoseUnit] = None
    note: Optional[str] = None
    created_at: datetime
