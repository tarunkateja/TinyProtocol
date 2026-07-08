from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

FoodCategory = Literal["breast_milk", "formula", "metabolic_formula", "other"]
# per_100ml: nutrition given per 100 ml of liquid (breast milk, prepared formula)
# per_scoop: nutrition given per scoop of powder added to a bottle
UnitBasis = Literal["per_100ml", "per_scoop"]
DoseUnit = Literal["mg", "ml"]


class FoodIn(BaseModel):
    name: str = Field(min_length=1)
    category: FoodCategory
    unit_basis: UnitBasis
    natural_protein_g_per_unit: float = Field(0, ge=0)
    lysine_mg_per_unit: float = Field(0, ge=0)
    description: Optional[str] = None
    # Where the nutrition values come from (e.g. USDA FoodData Central, a
    # manufacturer label). Shown in the app so parents can verify.
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    # Seeded values are estimates — a dietitian must confirm before trusting totals.
    needs_dietitian_verification: bool = True


class FoodUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    natural_protein_g_per_unit: Optional[float] = Field(None, ge=0)
    lysine_mg_per_unit: Optional[float] = Field(None, ge=0)
    description: Optional[str] = None
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    needs_dietitian_verification: Optional[bool] = None
    archived: Optional[bool] = None


class Food(FoodIn):
    id: str
    archived: bool = False
    created_at: datetime


class MedPresetIn(BaseModel):
    name: str = Field(min_length=1)
    dose_unit: DoseUnit = "ml"
    default_dose: Optional[float] = Field(None, gt=0)
    concentration_mg_per_ml: Optional[float] = Field(None, gt=0)
    notes: Optional[str] = None


class MedPresetUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    dose_unit: Optional[DoseUnit] = None
    default_dose: Optional[float] = Field(None, gt=0)
    concentration_mg_per_ml: Optional[float] = Field(None, gt=0)
    notes: Optional[str] = None


class MedPreset(MedPresetIn):
    id: str
    created_at: datetime
