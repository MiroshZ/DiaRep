"""Локальная безопасная имитация LLM-агента."""

from typing import Any


def _to_dict(data: Any) -> dict:
    if hasattr(data, "model_dump"):
        return data.model_dump()
    if hasattr(data, "dict"):
        return data.dict()
    return dict(data)


def generate_explanation(input_data: Any, result: dict, warnings: list[str]) -> str:
    """Формирует нейтральное объяснение учебного расчёта на русском языке."""
    data = _to_dict(input_data)
    warnings_text = "\n".join(f"- {warning}" for warning in warnings)

    return (
        "Учебная модель получила следующие данные: "
        f"{data['carbs_g']} г углеводов, углеводный коэффициент "
        f"{data['insulin_to_carb_ratio']} г/ед., текущая глюкоза "
        f"{data['current_glucose_mmol']} ммоль/л, целевая глюкоза "
        f"{data['target_glucose_mmol']} ммоль/л, фактор чувствительности "
        f"{data['correction_factor_mmol']} ммоль/л на 1 ед. инсулина, "
        f"активный инсулин {data.get('active_insulin', 0)} ед.\n\n"
        "Болюс на еду рассчитан как количество углеводов, делённое на "
        "углеводный коэффициент: "
        f"{data['carbs_g']} / {data['insulin_to_carb_ratio']} = "
        f"{result['meal_bolus']} ед.\n\n"
        "Коррекционный болюс рассчитан как разница между текущей и целевой "
        "глюкозой в ммоль/л, делённая на фактор чувствительности: "
        f"({data['current_glucose_mmol']} - {data['target_glucose_mmol']}) / "
        f"{data['correction_factor_mmol']} = {result['correction_bolus']} ед. "
        "Если расчёт коррекции получается ниже нуля, используется 0.\n\n"
        "Расчёт показывает итоговый учебный болюс: "
        f"{result['meal_bolus']} + {result['correction_bolus']} - "
        f"{result['active_insulin']} = {result['total_bolus']} ед.\n\n"
        "Предупреждения:\n"
        f"{warnings_text}\n\n"
        "Проверьте данные и обсудите любые изменения лечения с врачом."
    )
