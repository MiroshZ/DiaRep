import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nutrition  # noqa: E402
from nutrition import (  # noqa: E402
    estimate_nutrition_from_text,
    find_api_slug,
    product_matches_query,
    parse_meal_text,
)


def test_parse_meal_text_with_grams() -> None:
    items = parse_meal_text("гречки 50 грамм, банан 120 г")

    assert items == [
        {"query": "гречки", "weight_g": 50.0},
        {"query": "банан", "weight_g": 120.0},
    ]


def test_estimate_nutrition_from_text_uses_api_result(monkeypatch) -> None:
    def fake_fetch_food_nutrition(query: str) -> dict:
        return {
            "name": query,
            "protein_per_100g": 3,
            "fat_per_100g": 1,
            "carbs_per_100g": 20,
            "kcal_per_100g": 100,
            "source": "Open Food Facts",
            "source_url": "https://ru.openfoodfacts.org/",
        }

    monkeypatch.setattr(
        nutrition,
        "fetch_food_nutrition",
        fake_fetch_food_nutrition,
    )

    result = estimate_nutrition_from_text("гречки 50 грамм")

    assert result["total_protein"] == 1.5
    assert result["total_fat"] == 0.5
    assert result["total_carbs"] == 10
    assert result["total_kcal"] == 50
    assert result["items"][0]["source"] == "Open Food Facts"


def test_rice_uses_all_the_nutrients_slug() -> None:
    assert find_api_slug("рис 100 грамм") == "rice-white-medium-grain-cooked-unenriched"


def test_openfoodfacts_rejects_irrelevant_result_name() -> None:
    assert not product_matches_query("Йогурт TEOS 2%", "рис")
