"""Default food catalog + med preset copied into every new family at registration.

ALL nutrition values here are ballpark estimates and are flagged
needs_dietitian_verification=True. Scoop weights and per-scoop values vary by
brand — parents must confirm every number with their metabolic dietitian.
"""

from app.models.food import FoodIn, MedPresetIn

USDA_HUMAN_MILK_URL = "https://fdc.nal.usda.gov/fdc-app.html#/food-details/171279/nutrients"

DEFAULT_FOODS: list[FoodIn] = [
    FoodIn(
        name="Breast milk",
        category="breast_milk",
        unit_basis="per_100ml",
        natural_protein_g_per_unit=1.0,
        lysine_mg_per_unit=70,
        description=(
            "Mature human milk. USDA FoodData Central reports 1.03 g protein and "
            "68 mg lysine per 100 g; converted to per-100 ml using density "
            "~1.03 g/ml (≈1.06 g protein, ≈70 mg lysine per 100 ml — seeded "
            "conservatively as 1.0 g / 70 mg). Confirm with your dietitian."
        ),
        source_name="USDA FoodData Central — Milk, human, mature, fluid (FDC 171279)",
        source_url=USDA_HUMAN_MILK_URL,
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
        source_name="Manufacturer label — replace with your product's values",
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
        source_name="Manufacturer label — replace with your product's values",
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
        source_name="Manufacturer label — replace with your product's values",
    ),
    FoodIn(
        name="GA1 metabolic formula (prepared)",
        category="metabolic_formula",
        unit_basis="per_100ml",
        natural_protein_g_per_unit=0,
        lysine_mg_per_unit=0,
        description=(
            "Lysine-free amino acid formula, PREPARED liquid — use this when "
            "logging mixed bottles by ml (e.g. 40 ml breast milk + 20 ml prepared "
            "GA1 formula) so ml volume targets count it. Contributes zero to "
            "natural protein/lysine totals."
        ),
        source_name="Manufacturer label — replace with your product's values",
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
