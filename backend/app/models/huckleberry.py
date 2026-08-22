from datetime import datetime
from typing import Literal, Optional, Union

from pydantic import BaseModel, EmailStr, Field

# Huckleberry's bottle types (their exact strings — used as mapping keys).
HB_BOTTLE_TYPES = [
    "Breast Milk",
    "Formula",
    "Tube Feeding",
    "Cow Milk",
    "Goat Milk",
    "Soy Milk",
    "Other",
]

ImportStatus = Literal["pending", "imported", "dismissed", "deleted_upstream"]


class HbConnectIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)
    # Required only when the Huckleberry account has more than one child.
    child_uid: Optional[str] = None


class HbChild(BaseModel):
    uid: str
    name: str


class HbChildSelection(BaseModel):
    """Connect response when the account has several children: pick one and
    re-submit. Nothing is stored until then."""

    needs_child_selection: Literal[True] = True
    children: list[HbChild]


class HbSplitPart(BaseModel):
    """One slice of a mixed-bottle mapping. Parts are a ratio, not ml: their
    40+20 mix means a 45 ml partial bottle imports as 30 + 15."""

    food_id: str
    food_name: Optional[str] = None  # filled in for display on the way out
    parts: float = Field(gt=0)


class HbRecipeMapping(BaseModel):
    """Mixed bottle split by the feeding recipe in effect at the feed's time
    (Settings → Recipe). Plan changes are recipe edits, never mapping edits."""

    mode: Literal["recipe"]


# A bottle type maps to a single liquid food, to a fixed proportional split
# across several, or to "whatever the recipe said at that time".
HbMappingValue = Union[str, list[HbSplitPart], HbRecipeMapping]


class HbMappingEntry(BaseModel):
    food_id: Optional[str] = None
    food_name: Optional[str] = None
    split: Optional[list[HbSplitPart]] = None
    recipe: bool = False
    recipe_summary: Optional[str] = None  # the recipe in effect right now


class HbConnectionUpdate(BaseModel):
    auto_import: Optional[bool] = None
    # bottle type -> food_id or split; only liquid (per_100ml) foods qualify.
    mapping: Optional[dict[str, HbMappingValue]] = None
    latch_rate_ml_per_10min: Optional[float] = Field(None, ge=0)


class HbStatus(BaseModel):
    connected: bool
    hb_email: Optional[str] = None
    child_name: Optional[str] = None
    auto_import: bool = False
    mapping: dict[str, HbMappingEntry] = {}
    latch_rate_ml_per_10min: Optional[float] = None
    last_synced_at: Optional[datetime] = None
    status: Optional[str] = None  # ok | auth_failed
    last_error: Optional[str] = None
    pending_count: int = 0


class HbImport(BaseModel):
    item_type: Literal["HBIMPORT"] = "HBIMPORT"
    baby_id: str
    hb_key: str
    status: ImportStatus
    mode: Literal["bottle", "breast", "diaper", "medication", "pumping"]
    occurred_at: datetime
    bottle_type: Optional[str] = None
    amount_ml: Optional[float] = None
    minutes: Optional[float] = None  # breast: left+right nursing time
    diaper_kind: Optional[str] = None  # diaper: pee | poop | both
    diaper_color: Optional[str] = None
    diaper_consistency: Optional[str] = None
    pumped_ml: Optional[float] = None  # pumping
    side: Optional[str] = None
    duration_minutes: Optional[float] = None
    med_name: Optional[str] = None  # medication
    dose_amount: Optional[float] = None
    dose_unit: Optional[str] = None  # ml (oz/tsp converted; drops -> note)
    notes: Optional[str] = None
    hb_last_updated: Optional[float] = None
    food_id: Optional[str] = None  # mapping resolved at sync time (display only)
    feed_id: Optional[str] = None  # feed OR event id, set once imported
    created_at: datetime
    updated_at: datetime


class HbConfirmIn(BaseModel):
    """Overrides applied when confirming a pending import."""

    volume_ml: Optional[float] = Field(None, gt=0)  # bottle: correct the amount
    rate_ml_per_10min: Optional[float] = Field(None, ge=0)  # breast: estimate rate
    measured_ml: Optional[float] = Field(None, ge=0)  # breast: weighed feed wins


class HbSyncResult(BaseModel):
    fetched: int = 0
    new_pending: int = 0
    auto_imported: int = 0
    updated: int = 0
    deleted_upstream: int = 0
    skipped_solids: int = 0
