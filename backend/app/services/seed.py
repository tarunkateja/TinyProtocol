"""Default food catalog + med preset copied into every new family at registration.

ALL nutrition values here are ballpark estimates and are flagged
needs_dietitian_verification=True. Scoop weights and per-scoop values vary by
brand — parents must confirm every number with their metabolic dietitian.
"""

from app.models.food import FoodIn, MedPresetIn

DEFAULT_FOODS: list[FoodIn] = [
    FoodIn(
        name="Breast milk",
        category="breast_milk",
        unit_basis="per_100ml",
        natural_protein_g_per_unit=1.0,
        lysine_mg_per_unit=70,
        description=(
            "Mature human milk, approximate values. Confirm with your dietitian."
        ),
    ),
    FoodIn(
        name="Infant formula (prepared)",
        category="formula",
        unit_basis="per_100ml",
        natural_protein_g_per_unit=1.4,
        lysine_mg_per_unit=115,
        description=(
            "Generic standard infant formula, prepared/ready-to-feed. "
            "Replace values with your brand's label."
        ),
    ),
    FoodIn(
        name="Infant formula (powder)",
        category="formula",
        unit_basis="per_scoop",
        natural_protein_g_per_unit=1.0,
        lysine_mg_per_unit=80,
        description=(
            "Generic formula powder, per scoop. Scoop sizes vary by brand — "
            "replace with your brand's numbers."
        ),
    ),
    FoodIn(
        name="GA1 metabolic formula (powder)",
        category="metabolic_formula",
        unit_basis="per_scoop",
        natural_protein_g_per_unit=0,
        lysine_mg_per_unit=0,
        description=(
            "Lysine-free amino acid formula. Intentionally contributes ZERO to "
            "natural protein/lysine totals; tracked separately in scoops. "
            "Confirm with your metabolic dietitian."
        ),
    ),
]

DEFAULT_MED_PRESETS: list[MedPresetIn] = [
    MedPresetIn(
        name="Levocarnitine",
        dose_unit="ml",
        concentration_mg_per_ml=100,
        notes=(
            "Common oral solution is 100 mg/mL (Carnitor-style). Set the dose "
            "your metabolic team prescribed."
        ),
    ),
]
