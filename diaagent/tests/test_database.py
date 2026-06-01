import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import get_history, save_calculation  # noqa: E402
from models import BolusInput  # noqa: E402


def test_save_calculation_keeps_meal_and_macro_history(tmp_path) -> None:
    db_path = str(tmp_path / "diaagent.db")
    input_data = BolusInput(
        carbs_g=45,
        insulin_to_carb_ratio=12,
        current_glucose_mmol=7,
        target_glucose_mmol=6,
        correction_factor_mmol=2,
        active_insulin=0,
    )
    result = {
        "meal_bolus": 3.75,
        "correction_bolus": 0.5,
        "active_insulin": 0,
        "total_bolus": 4.25,
    }
    nutrition = {
        "total_protein": 18,
        "total_fat": 11,
        "total_kcal": 420,
    }

    save_calculation(
        input_data,
        result,
        ["Проверочное предупреждение"],
        meal_text="рис 150 г, яйцо 50 г",
        nutrition=nutrition,
        glucose_source="nightscout",
        db_path=db_path,
    )

    history = get_history(db_path=db_path)

    assert history[0]["meal_text"] == "рис 150 г, яйцо 50 г"
    assert history[0]["protein_g"] == 18
    assert history[0]["fat_g"] == 11
    assert history[0]["kcal"] == 420
    assert history[0]["glucose_source"] == "nightscout"
