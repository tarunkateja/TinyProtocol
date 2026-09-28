"""The dietitian update — the exact feeding-log message the parents paste
into MyChart for the metabolic dietitian, plus the pre-send checks."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class ReportLine(BaseModel):
    at: datetime
    text: str  # "90 ml prepared mix (large spit up)"
    feed_ids: list[str]


class ReportSection(BaseModel):
    day: date
    label: str  # "Monday 9/7", "This morning"
    partial: bool = False
    window_from: datetime
    window_to: datetime
    lines: list[ReportLine] = []
    feed_count: int = 0
    total_ml: float = 0
    breast_milk_ml: float = 0
    batch_ml: float = 0  # prepared-batch formula (mix share + top-offs)
    topup_ml: float = 0  # the recipe's own top-up food (e.g. Pro-Phree)
    weight_g: Optional[float] = None
    text: str = ""


class ReportWarning(BaseModel):
    day: date
    at: Optional[datetime] = None
    message: str


class DietitianReport(BaseModel):
    baby_id: str
    baby_name: str
    days: int
    generated_at: datetime
    window_from: datetime
    window_to: datetime
    sections: list[ReportSection]
    warnings: list[ReportWarning]
    text: str
