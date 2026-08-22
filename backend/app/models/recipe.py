"""Feeding recipes — what goes in a bottle and how the batch is made.

The metabolic team changes the plan often (a vaccination week, a growth
check, a hospital stay), and each change must be a Settings edit, never a
code edit. A recipe is effective from a TIMESTAMP (plans change mid-day:
"85 ml feeds starting tonight"), and the recipe in effect at a feed's time
decides how a Huckleberry mixed bottle splits into breast milk vs batch.

Split rule for a logged volume V against a recipe with B ml breast milk and
F ml batch per prepared bottle (P = B + F):
    breast_milk = min(B, V * B / P);  batch = V - breast_milk
V < P is a partial feed of the prepared bottle (proportional); V == P is the
full bottle; V > P is a bottle plus a top-off from the batch (breast milk is
capped at what the bottle held).
"""

from datetime import datetime
from typing import Optional

from pydantic import AwareDatetime, BaseModel, Field, computed_field, model_validator


class RecipePowder(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    grams: float = Field(gt=0)
    # Optional link to a powder food in the catalog (for future nutrition).
    food_id: Optional[str] = None


class RecipeIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    effective_at: AwareDatetime
    # The prepared bottle: fixed breast milk + batch formula per feed.
    breast_milk_ml: float = Field(0, ge=0)
    batch_ml: float = Field(0, ge=0)
    # The batch: powders + water to a final volume.
    powders: list[RecipePowder] = Field(default_factory=list, max_length=6)
    batch_final_volume_ml: Optional[float] = Field(None, gt=0)
    feeds_per_day: Optional[int] = Field(None, gt=0, le=24)
    # Which liquid foods represent the two parts when a feed is built from
    # this recipe. Empty = fall back to the Huckleberry mapping's
    # "Breast Milk" / "Formula" foods.
    breast_milk_food_id: Optional[str] = None
    batch_food_id: Optional[str] = None
    source: Optional[str] = Field(None, max_length=200)  # who ordered it, when
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _has_a_bottle(self) -> "RecipeIn":
        if self.breast_milk_ml + self.batch_ml <= 0:
            raise ValueError("a recipe needs breast milk and/or batch ml per feed")
        return self


class RecipeUpdate(BaseModel):
    label: Optional[str] = Field(None, min_length=1, max_length=80)
    effective_at: Optional[AwareDatetime] = None
    breast_milk_ml: Optional[float] = Field(None, ge=0)
    batch_ml: Optional[float] = Field(None, ge=0)
    powders: Optional[list[RecipePowder]] = Field(None, max_length=6)
    batch_final_volume_ml: Optional[float] = Field(None, gt=0)
    feeds_per_day: Optional[int] = Field(None, gt=0, le=24)
    breast_milk_food_id: Optional[str] = None
    batch_food_id: Optional[str] = None
    source: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = None


class Recipe(RecipeIn):
    id: str
    created_at: datetime

    @computed_field  # type: ignore[misc]
    @property
    def prepared_ml(self) -> float:
        return round(self.breast_milk_ml + self.batch_ml, 1)

    @computed_field  # type: ignore[misc]
    @property
    def feeds_per_batch(self) -> Optional[float]:
        """How many bottles one batch covers (before top-offs)."""
        if not self.batch_final_volume_ml or self.batch_ml <= 0:
            return None
        return round(self.batch_final_volume_ml / self.batch_ml, 1)


class ResplitChange(BaseModel):
    feed_id: str
    occurred_at: datetime
    total_ml: float
    recipe_label: str
    before: dict[str, float]  # food name -> ml
    after: dict[str, float]


class ResplitResult(BaseModel):
    applied: bool
    changes: list[ResplitChange]
    unchanged: int = 0  # recipe-mapped feeds already split correctly
    skipped_no_recipe: int = 0  # no recipe in effect at that time
    skipped_unlinked: int = 0  # manually edited (hb link broken) — hands off
