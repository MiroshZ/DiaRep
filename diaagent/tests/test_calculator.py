import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calculator import (  # noqa: E402
    calculate_correction_bolus,
    calculate_meal_bolus,
    calculate_total_bolus,
)


def test_calculate_meal_bolus() -> None:
    assert calculate_meal_bolus(60, 12) == 5


def test_calculate_correction_bolus() -> None:
    assert calculate_correction_bolus(10, 6, 2) == 2


def test_correction_bolus_cannot_be_negative() -> None:
    assert calculate_correction_bolus(5, 6, 2) == 0


def test_calculate_total_bolus() -> None:
    result = calculate_total_bolus(
        carbs_g=60,
        insulin_to_carb_ratio=12,
        current_glucose_mmol=10,
        target_glucose_mmol=6,
        correction_factor_mmol=2,
        active_insulin=1,
    )

    assert result["total_bolus"] == 6
