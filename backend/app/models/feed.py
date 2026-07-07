from datetime import datetime
from typing import Annotated, Literal, Optional, Union

from pydantic import AwareDatetime, BaseModel, Field

from app.models.food import FoodCategory


# --------------------------------------------------------------------------- #
# Input components — what the parent types in at 3am
# --------------------------------------------------------------------------- #
class LiquidComponent(BaseModel):
    """A measured liquid in the bottle: pumped breast milk, prepared formula."""

    kind: Literal["liquid"]
    food_id: str
    volume_ml: float = Field(gt=0)


class PowderComponent(BaseModel):
    """Powder mixed into the bottle (formula / metabolic formula). Adds no volume."""

    kind: Literal["powder"]
    food_id: str
    scoops: float = Field(gt=0)


class LatchComponent(BaseModel):
    """Direct breastfeeding. Intake estimated from minutes x rate, unless weighed."""

    kind: Literal["latch"]
    food_id: str
    minutes: float = Field(gt=0)
    rate_ml_per_10min: float = Field(ge=0)
    # Weighed-feed override (pre/post-feed scale); wins over the estimate if set.
    measured_ml: Optional[float] = Field(None, ge=0)


FeedComponentIn = Annotated[
    Union[LiquidComponent, PowderComponent, LatchComponent],
    Field(discriminator="kind"),
]


# --------------------------------------------------------------------------- #
# Stored components — input + nutrition snapshot computed at write time
# --------------------------------------------------------------------------- #
class _NutritionSnapshot(BaseModel):
    food_name: str
    food_category: FoodCategory
    effective_ml: float
    natural_protein_g: float
    lysine_mg: float
    is_estimated: bool = False


class LiquidComponentOut(LiquidComponent, _NutritionSnapshot):
    pass


class PowderComponentOut(PowderComponent, _NutritionSnapshot):
    pass


class LatchComponentOut(LatchComponent, _NutritionSnapshot):
    pass


FeedComponentOut = Annotated[
    Union[LiquidComponentOut, PowderComponentOut, LatchComponentOut],
    Field(discriminator="kind"),
]


class FeedTotals(BaseModel):
    total_ml: float = 0
    breast_milk_ml: float = 0
    formula_ml: float = 0
    metabolic_formula_ml: float = 0
    other_ml: float = 0
    formula_scoops: float = 0
    metabolic_formula_scoops: float = 0
    natural_protein_g: float = 0
    lysine_mg: float = 0


# --------------------------------------------------------------------------- #
# Feed
# --------------------------------------------------------------------------- #
class FeedIn(BaseModel):
    occurred_at: AwareDatetime
    components: list[FeedComponentIn] = Field(min_length=1)
    notes: Optional[str] = None


class FeedUpdate(BaseModel):
    occurred_at: Optional[AwareDatetime] = None
    components: Optional[list[FeedComponentIn]] = Field(None, min_length=1)
    notes: Optional[str] = None


class Feed(BaseModel):
    item_type: Literal["FEED"] = "FEED"
    id: str
    baby_id: str
    occurred_at: datetime
    components: list[FeedComponentOut]
    totals: FeedTotals
    notes: Optional[str] = None
    created_at: datetime
