import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import llm_agent  # noqa: E402
from llm_agent import (  # noqa: E402
    generate_ai_explanation,
    generate_explanation,
    generate_local_explanation,
)
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

    explanation = generate_local_explanation(input_data, result, [], nutrition)

    assert "белки 30 г" in explanation
    assert "жиры 22 г" in explanation
    assert "понять" not in explanation
    assert "может меняться позже" in explanation


def test_ai_explanation_uses_strict_agent_payload(monkeypatch) -> None:
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
    captured = {}

    def fake_call(messages, api_key, model, timeout_seconds=35):
        captured["messages"] = messages
        captured["api_key"] = api_key
        captured["model"] = model
        return (
            "В еде получилось 40 г углеводов. "
            "Часть на еду: 4 ед. Коррекция: 1 ед. "
            "Расчёт показывает итог: 5 ед."
        )

    monkeypatch.setattr(llm_agent, "_call_polza_chat_completion", fake_call)

    explanation = generate_ai_explanation(
        input_data,
        result,
        [],
        nutrition,
        api_key="test-key",
        model="test-model",
    )

    assert "5 ед" in explanation
    assert captured["api_key"] == "test-key"
    assert captured["model"] == "test-model"
    assert "ребёнок 7 лет" in captured["messages"][0]["content"]
    assert "не пересчитывай числа самостоятельно" in captured["messages"][0]["content"]


def test_generate_explanation_falls_back_for_unsafe_ai_text(monkeypatch) -> None:
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

    def fake_call(messages, api_key, model, timeout_seconds=35):
        return "Вам нужно ввести 5 ед."

    monkeypatch.setenv("POLZA_AI_API_KEY", "test-key")
    monkeypatch.setattr(llm_agent, "_call_polza_chat_completion", fake_call)

    explanation = generate_explanation(input_data, result, [], None)

    assert "Вам нужно ввести" not in explanation
    assert "Итог этого информационного расчёта" in explanation


def test_local_explanation_is_plain_and_human_readable() -> None:
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

    explanation = generate_local_explanation(input_data, result, [], None)

    assert "Модель получила" not in explanation
    assert "Вот что получилось простыми словами" in explanation
    assert "*" not in explanation
    assert "#" not in explanation
