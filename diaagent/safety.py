"""Правила безопасности для DiaAgent."""


HYPOGLYCEMIA_WARNING = (
    "Обнаружен риск гипогликемии. При низкой глюкозе расчёт инсулина "
    "может быть опасен. Следуйте плану, назначенному врачом."
)

HIGH_GLUCOSE_WARNING = (
    "Глюкоза значительно выше целевого диапазона. Проверьте кетоны при "
    "необходимости и следуйте рекомендациям врача."
)

CARBS_WARNING = (
    "Количество углеводов должно быть больше 0 для расчёта болюса на еду."
)

HIGH_DOSE_WARNING = (
    "Расчётная доза выглядит высокой. Проверьте введённые коэффициенты и данные."
)

EDUCATIONAL_WARNING = (
    "Это информационный расчёт, а не медицинская рекомендация. Не изменяйте "
    "лечение без консультации с врачом."
)


def check_safety(
    current_glucose_mmol: float,
    total_bolus: float,
    carbs_g: float,
) -> list[str]:
    """Возвращает список предупреждений для информационного расчёта."""
    warnings = []

    if current_glucose_mmol < 3.9:
        warnings.append(HYPOGLYCEMIA_WARNING)

    if current_glucose_mmol > 13.9:
        warnings.append(HIGH_GLUCOSE_WARNING)

    if carbs_g <= 0:
        warnings.append(CARBS_WARNING)

    if total_bolus > 20:
        warnings.append(HIGH_DOSE_WARNING)

    warnings.append(EDUCATIONAL_WARNING)
    return warnings
