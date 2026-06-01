"""Безопасное объяснение результата расчёта DiaAgent."""

from typing import Any


def _to_dict(data: Any) -> dict:
    if hasattr(data, "model_dump"):
        return data.model_dump()
    if hasattr(data, "dict"):
        return data.dict()
    return dict(data)


def _nutrition_comment(nutrition: dict | None) -> str:
    if not nutrition:
        return ""

    protein = nutrition.get("total_protein", 0)
    fat = nutrition.get("total_fat", 0)
    carbs = nutrition.get("total_carbs", 0)
    kcal = nutrition.get("total_kcal", 0)
    items = nutrition.get("items", [])
    item_names = ", ".join(str(item.get("name", "")) for item in items[:4])
    if len(items) > 4:
        item_names = f"{item_names} и другие продукты"

    comment = (
        "Анализ состава еды: "
        f"углеводы {carbs} г, белки {protein} г, жиры {fat} г, "
        f"энергетическая ценность около {kcal} ккал."
    )
    if item_names:
        comment += f" В расчёте учтены продукты: {item_names}."

    if protein >= 25 or fat >= 20:
        comment += (
            " В этом приёме пищи заметное количество белков или жиров. "
            "Они не входят в базовую формулу болюса на углеводы, но могут "
            "замедлять усвоение еды и влиять на глюкозу позже. Проверьте "
            "данные и обсудите индивидуальную тактику с врачом."
        )
    else:
        comment += (
            " Белки и жиры показаны как дополнительный фактор наблюдения; "
            "базовый учебный расчёт болюса использует углеводы и ваши "
            "индивидуальные коэффициенты."
        )

    return f"{comment}\n\n"


def generate_explanation(
    input_data: Any,
    result: dict,
    warnings: list[str],
    nutrition: dict | None = None,
) -> str:
    """Формирует нейтральное объяснение расчёта на русском языке."""
    data = _to_dict(input_data)
    warnings_text = "\n".join(f"- {warning}" for warning in warnings)
    nutrition_text = _nutrition_comment(nutrition)

    return (
        "Модель получила следующие данные: "
        f"{data['carbs_g']} г углеводов, углеводный коэффициент "
        f"{data['insulin_to_carb_ratio']} г/ед., текущая глюкоза "
        f"{data['current_glucose_mmol']} ммоль/л, целевая глюкоза "
        f"{data['target_glucose_mmol']} ммоль/л, фактор чувствительности "
        f"{data['correction_factor_mmol']} ммоль/л на 1 ед. инсулина, "
        f"активный инсулин {data.get('active_insulin', 0)} ед.\n\n"
        f"{nutrition_text}"
        "Болюс на еду рассчитан как количество углеводов, делённое на "
        "углеводный коэффициент: "
        f"{data['carbs_g']} / {data['insulin_to_carb_ratio']} = "
        f"{result['meal_bolus']} ед.\n\n"
        "Коррекционный болюс рассчитан как разница между текущей и целевой "
        "глюкозой в ммоль/л, делённая на фактор чувствительности: "
        f"({data['current_glucose_mmol']} - {data['target_glucose_mmol']}) / "
        f"{data['correction_factor_mmol']} = {result['correction_bolus']} ед. "
        "Если расчёт коррекции получается ниже нуля, используется 0.\n\n"
        "Расчёт показывает итоговый болюс: "
        f"{result['meal_bolus']} + {result['correction_bolus']} - "
        f"{result['active_insulin']} = {result['total_bolus']} ед.\n\n"
        "Предупреждения:\n"
        f"{warnings_text}\n\n"
        "Проверьте данные и обсудите любые изменения лечения с врачом."
    )
