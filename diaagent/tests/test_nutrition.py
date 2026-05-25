import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nutrition import estimate_carbs_from_text, parse_meal_text  # noqa: E402


def test_parse_meal_text_with_grams() -> None:
    items = parse_meal_text("гречки 50 грамм, банан 120 г")

    assert items == [
        {"query": "гречки", "weight_g": 50.0},
        {"query": "банан", "weight_g": 120.0},
    ]


def test_estimate_carbs_from_text_uses_local_foods() -> None:
    foods_df = pd.DataFrame(
        {
            "name": ["гречка варёная"],
            "carbs_per_100g": [20],
        }
    )

    result = estimate_carbs_from_text(
        "гречки 50 грамм",
        foods_df,
        use_openfoodfacts=False,
    )

    assert result["total_carbs"] == 10
    assert result["items"][0]["source"] == "локальный справочник"
