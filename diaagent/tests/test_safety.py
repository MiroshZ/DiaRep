import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from safety import check_safety  # noqa: E402


def test_hypoglycemia_warning_for_low_glucose() -> None:
    warnings = check_safety(current_glucose_mmol=3.5, total_bolus=1, carbs_g=10)

    assert any("гипогликемии" in warning for warning in warnings)


def test_high_glucose_warning() -> None:
    warnings = check_safety(current_glucose_mmol=14.5, total_bolus=1, carbs_g=10)

    assert any("выше целевого диапазона" in warning for warning in warnings)


def test_high_dose_warning() -> None:
    warnings = check_safety(current_glucose_mmol=7, total_bolus=21, carbs_g=10)

    assert any("доза выглядит высокой" in warning for warning in warnings)


def test_information_warning_is_always_present() -> None:
    warnings = check_safety(current_glucose_mmol=7, total_bolus=1, carbs_g=10)

    assert any("информационный расчёт" in warning for warning in warnings)
