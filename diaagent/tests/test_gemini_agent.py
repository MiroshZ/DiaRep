import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from gemini_agent import (  # noqa: E402
    GeminiFoodRecognitionError,
    _extract_json,
    _normalize_items,
    build_meal_text,
    recognize_food_from_image,
)


def test_extract_json_from_markdown_block() -> None:
    payload = _extract_json('```json\n{"items": []}\n```')

    assert payload == {"items": []}


def test_normalize_items_skips_invalid_values() -> None:
    items = _normalize_items(
        {
            "items": [
                {"name": "Рис", "weight_g": 150, "confidence": "высокая"},
                {"name": "", "weight_g": 100},
                {"name": "банан", "weight_g": 0},
            ]
        }
    )

    assert items == [{"name": "рис", "weight_g": 150, "confidence": "высокая"}]


def test_build_meal_text() -> None:
    meal_text = build_meal_text(
        [
            {"name": "рис", "weight_g": 150},
            {"name": "банан", "weight_g": 120},
        ]
    )

    assert meal_text == "рис 150 г, банан 120 г"


def test_recognize_food_requires_polza_key(monkeypatch) -> None:
    monkeypatch.delenv("POLZA_AI_API_KEY", raising=False)

    with pytest.raises(GeminiFoodRecognitionError, match="POLZA_AI_API_KEY"):
        recognize_food_from_image(b"fake-image", "image/jpeg")
