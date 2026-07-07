from datetime import datetime, timezone

import pytest
from pydantic import TypeAdapter

from app.models.feed import FeedComponentIn
from app.models.food import Food
from app.services.nutrition import NutritionError, compute_components

NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)

BREAST_MILK = Food(
    id="bm", name="Breast milk", category="breast_milk", unit_basis="per_100ml",
    natural_protein_g_per_unit=1.0, lysine_mg_per_unit=70, created_at=NOW,
)
FORMULA_LIQUID = Food(
    id="fl", name="Formula (prepared)", category="formula", unit_basis="per_100ml",
    natural_protein_g_per_unit=1.4, lysine_mg_per_unit=115, created_at=NOW,
)
FORMULA_POWDER = Food(
    id="fp", name="Formula (powder)", category="formula", unit_basis="per_scoop",
    natural_protein_g_per_unit=1.0, lysine_mg_per_unit=80, created_at=NOW,
)
METABOLIC_POWDER = Food(
    id="mp", name="GA1 formula", category="metabolic_formula", unit_basis="per_scoop",
    natural_protein_g_per_unit=0, lysine_mg_per_unit=0, created_at=NOW,
)
FOODS = {f.id: f for f in (BREAST_MILK, FORMULA_LIQUID, FORMULA_POWDER, METABOLIC_POWDER)}

_adapter = TypeAdapter(list[FeedComponentIn])


def comps(*raw):
    return _adapter.validate_python(list(raw))


def test_mixed_bottle_breast_milk_plus_metabolic_powder():
    out, totals = compute_components(
        comps(
            {"kind": "liquid", "food_id": "bm", "volume_ml": 60},
            {"kind": "powder", "food_id": "mp", "scoops": 1},
        ),
        FOODS,
    )
    assert totals.total_ml == 60  # powder adds no volume
    assert totals.breast_milk_ml == 60
    assert totals.metabolic_formula_scoops == 1
    assert totals.natural_protein_g == 0.6
    assert totals.lysine_mg == 42  # 0.6 * 70
    assert out[1]["effective_ml"] == 0
    assert out[1]["natural_protein_g"] == 0  # lysine-free formula contributes zero


def test_latch_estimate_from_minutes_and_rate():
    out, totals = compute_components(
        comps({"kind": "latch", "food_id": "bm", "minutes": 20, "rate_ml_per_10min": 25}),
        FOODS,
    )
    assert out[0]["effective_ml"] == 50
    assert out[0]["is_estimated"] is True
    assert totals.breast_milk_ml == 50
    assert totals.natural_protein_g == 0.5
    assert totals.lysine_mg == 35


def test_latch_measured_ml_overrides_estimate():
    out, _ = compute_components(
        comps(
            {
                "kind": "latch", "food_id": "bm", "minutes": 20,
                "rate_ml_per_10min": 25, "measured_ml": 42,
            }
        ),
        FOODS,
    )
    assert out[0]["effective_ml"] == 42
    assert out[0]["is_estimated"] is False


def test_triple_mix_totals():
    _, totals = compute_components(
        comps(
            {"kind": "liquid", "food_id": "bm", "volume_ml": 50},
            {"kind": "liquid", "food_id": "fl", "volume_ml": 40},
            {"kind": "powder", "food_id": "fp", "scoops": 0.5},
        ),
        FOODS,
    )
    assert totals.total_ml == 90
    assert totals.breast_milk_ml == 50
    assert totals.formula_ml == 40
    assert totals.formula_scoops == 0.5
    # 0.5*1.0 + 0.4*1.4 + 0.5*1.0
    assert totals.natural_protein_g == pytest.approx(1.56)
    # 0.5*70 + 0.4*115 + 0.5*80
    assert totals.lysine_mg == pytest.approx(121)


def test_unit_basis_mismatch_rejected():
    with pytest.raises(NutritionError):
        compute_components(
            comps({"kind": "liquid", "food_id": "fp", "volume_ml": 60}), FOODS
        )
    with pytest.raises(NutritionError):
        compute_components(
            comps({"kind": "powder", "food_id": "bm", "scoops": 1}), FOODS
        )


def test_unknown_food_rejected():
    with pytest.raises(NutritionError):
        compute_components(
            comps({"kind": "liquid", "food_id": "nope", "volume_ml": 60}), FOODS
        )
