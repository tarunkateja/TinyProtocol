"""Pure component math: parent input + food catalog -> nutrition snapshot.

Computed ONCE at write time and stored on the feed. Feeds are medical records:
editing the catalog later must never silently rewrite history.
"""

from app.models.feed import FeedComponentIn, FeedTotals
from app.models.food import Food


class NutritionError(ValueError):
    """Component/food mismatch the client must fix (rendered as a 422)."""


def compute_components(
    components: list[FeedComponentIn], foods: dict[str, Food]
) -> tuple[list[dict], FeedTotals]:
    """Returns (component snapshots as dicts, feed totals)."""
    out: list[dict] = []
    totals = FeedTotals()

    for comp in components:
        food = foods.get(comp.food_id)
        if food is None:
            raise NutritionError(f"Unknown food: {comp.food_id}")

        is_estimated = False
        if comp.kind == "liquid":
            _require_basis(food, "per_100ml")
            effective_ml = comp.volume_ml
            units = effective_ml / 100
        elif comp.kind == "powder":
            _require_basis(food, "per_scoop")
            effective_ml = 0.0
            units = comp.scoops
        else:  # latch
            _require_basis(food, "per_100ml")
            if comp.measured_ml is not None:
                effective_ml = comp.measured_ml
            else:
                effective_ml = comp.minutes * comp.rate_ml_per_10min / 10
                is_estimated = True
            units = effective_ml / 100

        protein_g = round(units * food.natural_protein_g_per_unit, 3)
        lysine_mg = round(units * food.lysine_mg_per_unit, 2)
        effective_ml = round(effective_ml, 1)

        snapshot = comp.model_dump()
        snapshot.update(
            food_name=food.name,
            food_category=food.category,
            effective_ml=effective_ml,
            natural_protein_g=protein_g,
            lysine_mg=lysine_mg,
            is_estimated=is_estimated,
        )
        out.append(snapshot)

        totals.total_ml = round(totals.total_ml + effective_ml, 1)
        totals.natural_protein_g = round(totals.natural_protein_g + protein_g, 3)
        totals.lysine_mg = round(totals.lysine_mg + lysine_mg, 2)

        ml_field = {
            "breast_milk": "breast_milk_ml",
            "formula": "formula_ml",
            "metabolic_formula": "metabolic_formula_ml",
            "other": "other_ml",
        }[food.category]
        setattr(totals, ml_field, round(getattr(totals, ml_field) + effective_ml, 1))

        if comp.kind == "powder":
            if food.category == "metabolic_formula":
                totals.metabolic_formula_scoops += comp.scoops
            elif food.category == "formula":
                totals.formula_scoops += comp.scoops

    return out, totals


def _require_basis(food: Food, basis: str) -> None:
    if food.unit_basis != basis:
        raise NutritionError(
            f"Food '{food.name}' is measured {food.unit_basis}, "
            f"but this component needs a {basis} food"
        )
