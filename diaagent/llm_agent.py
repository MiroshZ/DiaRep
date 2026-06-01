"""Безопасное объяснение результата расчёта DiaAgent."""

import json
import os
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from dotenv import load_dotenv

POLZA_CHAT_COMPLETIONS_URL = "https://polza.ai/api/v1/chat/completions"
DEFAULT_EXPLANATION_MODEL = "google/gemini-3.1-flash-lite"
FORBIDDEN_MEDICAL_PHRASES = (
    "вам нужно ввести",
    "рекомендуется ввести",
    "сделайте инъекцию",
    "введите инсулин",
    "доза для введения",
    "*",
    "#",
    "→",
    "=>",
)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")


class ExplanationAgentError(Exception):
    """Ошибка безопасного ИИ-объяснения."""


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
        "В еде получилось так: "
        f"углеводы {carbs} г, белки {protein} г, жиры {fat} г, "
        f"примерно {kcal} ккал."
    )
    if item_names:
        comment += f" Учтены продукты: {item_names}."

    if protein >= 25 or fat >= 20:
        comment += (
            " Белков или жиров здесь довольно много. Они не меняют этот "
            "расчёт болюса, но иногда сахар из-за такой еды может меняться "
            "позже. Лучше проверить данные и обсудить такие случаи с врачом."
        )
    else:
        comment += (
            " Белки и жиры показаны для понимания еды. Сам расчёт болюса "
            "сейчас смотрит на углеводы и ваши коэффициенты."
        )

    return f"{comment}\n\n"


def generate_local_explanation(
    input_data: Any,
    result: dict,
    warnings: list[str],
    nutrition: dict | None = None,
) -> str:
    """Формирует локальное нейтральное объяснение расчёта на русском языке."""
    data = _to_dict(input_data)
    warnings_text = "\n".join(f"- {warning}" for warning in warnings)
    nutrition_text = _nutrition_comment(nutrition)

    return (
        "Вот что получилось простыми словами.\n\n"
        f"В еде найдено {data['carbs_g']} г углеводов. "
        f"Текущая глюкоза: {data['current_glucose_mmol']} ммоль/л. "
        f"Цель: {data['target_glucose_mmol']} ммоль/л. "
        f"Активный инсулин: {data.get('active_insulin', 0)} ед.\n\n"
        f"{nutrition_text}"
        "Сначала считается часть на еду. "
        f"{data['carbs_g']} / {data['insulin_to_carb_ratio']} = "
        f"{result['meal_bolus']} ед.\n\n"
        "Потом считается часть для сахара выше цели. "
        f"({data['current_glucose_mmol']} - {data['target_glucose_mmol']}) / "
        f"{data['correction_factor_mmol']} = {result['correction_bolus']} ед. "
        "Если сахар ниже цели, эта часть становится 0.\n\n"
        "Потом учитывается активный инсулин. "
        f"{result['meal_bolus']} + {result['correction_bolus']} - "
        f"{result['active_insulin']} = {result['total_bolus']} ед.\n\n"
        f"Итог этого информационного расчёта: {result['total_bolus']} ед.\n\n"
        "Предупреждения:\n"
        f"{warnings_text}\n\n"
        "Проверьте данные. Любые изменения лечения обсуждайте с врачом."
    )


def _number_variants(value: Any) -> set[str]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return {str(value)}

    variants = {
        str(value),
        f"{number:.2f}",
        f"{number:.1f}",
        f"{number:g}",
    }
    return variants | {variant.replace(".", ",") for variant in variants}


def _build_agent_payload(
    input_data: Any,
    result: dict,
    warnings: list[str],
    nutrition: dict | None,
) -> dict:
    data = _to_dict(input_data)
    nutrition = nutrition or {}
    return {
        "input": {
            "carbs_g": data["carbs_g"],
            "insulin_to_carb_ratio": data["insulin_to_carb_ratio"],
            "current_glucose_mmol": data["current_glucose_mmol"],
            "target_glucose_mmol": data["target_glucose_mmol"],
            "correction_factor_mmol": data["correction_factor_mmol"],
            "active_insulin": data.get("active_insulin", 0),
        },
        "nutrition": {
            "items": nutrition.get("items", []),
            "total_protein": nutrition.get("total_protein", 0),
            "total_fat": nutrition.get("total_fat", 0),
            "total_carbs": nutrition.get("total_carbs", data["carbs_g"]),
            "total_kcal": nutrition.get("total_kcal", 0),
        },
        "result": {
            "meal_bolus": result["meal_bolus"],
            "correction_bolus": result["correction_bolus"],
            "active_insulin": result.get("active_insulin", data.get("active_insulin", 0)),
            "total_bolus": result["total_bolus"],
        },
        "formulas": {
            "meal_bolus": "carbs_g / insulin_to_carb_ratio",
            "correction_bolus": "max((current_glucose_mmol - target_glucose_mmol) / correction_factor_mmol, 0)",
            "total_bolus": "max(meal_bolus + correction_bolus - active_insulin, 0)",
        },
        "warnings": warnings,
    }


def _build_strict_prompt(payload: dict) -> list[dict]:
    rules = (
        "Объясни уже выполненный информационный расчёт простым русским языком. "
        "Пиши так, чтобы понял ребёнок 7 лет. Не представляйся. "
        "Не используй markdown, списки со звёздочками, решётки, стрелки, таблицы, "
        "сложные термины и длинные абзацы. Пиши короткими живыми фразами. "
        "Строгие правила: не пересчитывай числа самостоятельно; используй только "
        "готовые значения из JSON; не меняй формулы, единицы измерения и округление; "
        "не добавляй медицинские назначения; не пиши фразы 'вам нужно ввести', "
        "'рекомендуется ввести', 'сделайте инъекцию'. Можно писать только "
        "нейтрально: 'расчёт показывает', 'получилось', 'проверьте данные', "
        "'обсудите с врачом'. Глюкоза только в ммоль/л. "
        "Белки и жиры можно описывать только как факторы наблюдения, которые могут "
        "влиять на динамику глюкозы позже, без изменения итогового болюса."
    )
    user_prompt = (
        "Сформируй понятное объяснение для блока результата. "
        "Скажи: что нашли в еде, как получилась часть на еду, как получилась "
        "коррекция, какой итог, и какие есть предупреждения. "
        "Все числовые значения бери только из JSON ниже. "
        "Не используй спецсимволы для оформления.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
    return [
        {"role": "system", "content": rules},
        {"role": "user", "content": user_prompt},
    ]


def _call_polza_chat_completion(
    messages: list[dict],
    api_key: str,
    model: str,
    timeout_seconds: int = 35,
) -> str:
    request_payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 1100,
    }
    request = Request(
        POLZA_CHAT_COMPLETIONS_URL,
        data=json.dumps(request_payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urlopen(request, timeout=timeout_seconds) as response:
        response_payload = json.loads(response.read().decode("utf-8"))

    choices = response_payload.get("choices") or []
    if not choices:
        raise ExplanationAgentError("Polza.ai вернул ответ без объяснения.")

    message = choices[0].get("message") or {}
    text = str(message.get("content") or "").strip()
    if not text:
        raise ExplanationAgentError("Polza.ai вернул пустое объяснение.")

    return text


def _validate_agent_explanation(text: str, payload: dict) -> None:
    lowered = text.lower()
    if any(phrase in lowered for phrase in FORBIDDEN_MEDICAL_PHRASES):
        raise ExplanationAgentError("ИИ-объяснение содержит медицински опасную фразу.")

    required_values = (
        payload["result"]["meal_bolus"],
        payload["result"]["correction_bolus"],
        payload["result"]["total_bolus"],
        payload["input"]["carbs_g"],
    )
    for value in required_values:
        if not any(variant in text for variant in _number_variants(value)):
            raise ExplanationAgentError("ИИ-объяснение не содержит обязательные числа.")


def generate_ai_explanation(
    input_data: Any,
    result: dict,
    warnings: list[str],
    nutrition: dict | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> str:
    """Формирует объяснение через Gemini в Polza.ai с валидацией результата."""
    api_key = api_key or os.getenv("POLZA_AI_API_KEY")
    if not api_key:
        raise ExplanationAgentError("Не задан POLZA_AI_API_KEY.")

    model = model or os.getenv(
        "DIAAGENT_EXPLANATION_MODEL",
        os.getenv("GEMINI_MODEL", DEFAULT_EXPLANATION_MODEL),
    )
    payload = _build_agent_payload(input_data, result, warnings, nutrition)
    messages = _build_strict_prompt(payload)

    try:
        text = _call_polza_chat_completion(messages, api_key, model)
    except Exception as error:  # noqa: BLE001
        raise ExplanationAgentError(f"ИИ-объяснение недоступно: {error}") from error

    _validate_agent_explanation(text, payload)
    return text


def generate_explanation(
    input_data: Any,
    result: dict,
    warnings: list[str],
    nutrition: dict | None = None,
) -> str:
    """Формирует объяснение через ИИ-агента с безопасным локальным fallback."""
    if os.getenv("DIAAGENT_DISABLE_AI_EXPLANATION", "").lower() in {
        "1",
        "true",
        "yes",
    }:
        return generate_local_explanation(input_data, result, warnings, nutrition)

    try:
        return generate_ai_explanation(input_data, result, warnings, nutrition)
    except ExplanationAgentError:
        return generate_local_explanation(input_data, result, warnings, nutrition)
