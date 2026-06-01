import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_agent import generate_explanation  # noqa: E402
from models import BolusInput  # noqa: E402


def test_explanation_mentions_protein_and_fat_context() -> None:
    input_data = BolusInput(
        carbs_g=40,
        insulin_to_carb_ratio=10,
        current_glucose_mmol=8,
        target_glucose_mmol=6,
        correction_factor_mmol=2,
        active_insulin=0,
    )
    result = {
        "meal_bolus": 4,
        "correction_bolus": 1,
        "active_insulin": 0,
        "total_bolus": 5,
    }
    nutrition = {
        "items": [{"name": "омлет"}],
        "total_protein": 30,
        "total_fat": 22,
        "total_carbs": 40,
        "total_kcal": 520,
    }

    explanation = generate_explanation(input_data, result, [], nutrition)

    assert "белки 30 г" in explanation
    assert "жиры 22 г" in explanation
    assert "могут замедлять усвоение еды" in explanation
