"""Учебные функции расчёта болюсного инсулина."""


def calculate_meal_bolus(carbs_g: float, insulin_to_carb_ratio: float) -> float:
    """Рассчитывает болюс на еду по количеству углеводов."""
    meal_bolus = carbs_g / insulin_to_carb_ratio
    return round(meal_bolus, 2)


def calculate_correction_bolus(
    current_glucose_mmol: float,
    target_glucose_mmol: float,
    correction_factor_mmol: float,
) -> float:
    """Рассчитывает коррекционный болюс с глюкозой в ммоль/л."""
    correction_bolus = (
        current_glucose_mmol - target_glucose_mmol
    ) / correction_factor_mmol
    return round(max(correction_bolus, 0), 2)


def calculate_total_bolus(
    carbs_g: float,
    insulin_to_carb_ratio: float,
    current_glucose_mmol: float,
    target_glucose_mmol: float,
    correction_factor_mmol: float,
    active_insulin: float = 0,
) -> dict:
    """Возвращает учебную детализацию расчёта итогового болюса."""
    meal_bolus = calculate_meal_bolus(carbs_g, insulin_to_carb_ratio)
    correction_bolus = calculate_correction_bolus(
        current_glucose_mmol,
        target_glucose_mmol,
        correction_factor_mmol,
    )
    total_bolus = meal_bolus + correction_bolus - active_insulin

    return {
        "meal_bolus": round(meal_bolus, 2),
        "correction_bolus": round(correction_bolus, 2),
        "active_insulin": round(active_insulin, 2),
        "total_bolus": round(max(total_bolus, 0), 2),
    }
