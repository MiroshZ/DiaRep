"""Работа с продуктами и оценкой углеводов."""

import json
import re
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

OPENFOODFACTS_SEARCH_URL = "https://world.openfoodfacts.org/api/v2/search"
USER_AGENT = "DiaAgent-MVP/0.1 (educational prototype)"

LOCAL_ALIASES = {
    "греч": "гречка варёная",
    "рис": "рис варёный",
    "макарон": "макароны варёные",
    "паст": "макароны варёные",
    "яблок": "яблоко",
    "банан": "банан",
    "хлеб": "хлеб белый",
    "карто": "картофель варёный",
    "курин": "куриная грудка",
    "яйц": "яйцо",
    "творог": "творог",
    "молок": "молоко",
    "йогурт": "йогурт натуральный",
}

MEAL_ITEM_PATTERN = re.compile(
    r"([а-яёa-z\s-]+?)\s+(\d+(?:[,.]\d+)?)\s*(?:г|гр|грамм|граммов)\b",
    re.IGNORECASE,
)


def load_foods(path: str = "data/foods.csv") -> pd.DataFrame:
    """Загружает CSV с продуктами и углеводами на 100 г."""
    csv_path = Path(path)
    if not csv_path.is_absolute() and not csv_path.exists():
        csv_path = Path(__file__).parent / path

    return pd.read_csv(csv_path)


def estimate_carbs_from_foods(
    selected_foods: list[str],
    foods_df: pd.DataFrame,
) -> float:
    """Суммирует углеводы на 100 г для выбранных продуктов."""
    selected_rows = foods_df[foods_df["name"].isin(selected_foods)]
    carbs = selected_rows["carbs_per_100g"].sum()
    return round(float(carbs), 2)


def normalize_food_name(value: str) -> str:
    """Приводит название продукта к удобному виду для поиска."""
    normalized = value.lower().replace("ё", "е")
    normalized = re.sub(r"[^а-яa-z\s-]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def parse_meal_text(meal_text: str) -> list[dict]:
    """Разбирает фразу вида 'гречки 50 грамм, яблоко 120 г'."""
    items = []
    for match in MEAL_ITEM_PATTERN.finditer(meal_text):
        raw_name = match.group(1).strip(" ,.;")
        weight_g = float(match.group(2).replace(",", "."))
        if raw_name and weight_g > 0:
            items.append(
                {
                    "query": raw_name,
                    "weight_g": round(weight_g, 2),
                }
            )

    return items


def find_local_food(query: str, foods_df: pd.DataFrame) -> dict | None:
    """Ищет продукт в локальном справочнике по названию или простому синониму."""
    normalized_query = normalize_food_name(query)

    for alias, food_name in LOCAL_ALIASES.items():
        if alias in normalized_query:
            row = foods_df.loc[foods_df["name"] == food_name].iloc[0]
            return {
                "name": str(row["name"]),
                "carbs_per_100g": float(row["carbs_per_100g"]),
                "source": "локальный справочник",
            }

    for _, row in foods_df.iterrows():
        food_name = str(row["name"])
        normalized_name = normalize_food_name(food_name)
        if normalized_name in normalized_query or normalized_query in normalized_name:
            return {
                "name": food_name,
                "carbs_per_100g": float(row["carbs_per_100g"]),
                "source": "локальный справочник",
            }

    return None


def fetch_openfoodfacts_food(query: str, timeout_seconds: int = 4) -> dict | None:
    """Ищет продукт в Open Food Facts и возвращает углеводы на 100 г."""
    params = urlencode(
        {
            "search_terms": query,
            "fields": "product_name,nutriments",
            "page_size": 1,
            "json": 1,
            "lc": "ru",
        }
    )
    request = Request(
        f"{OPENFOODFACTS_SEARCH_URL}?{params}",
        headers={"User-Agent": USER_AGENT},
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, json.JSONDecodeError):
        return None

    products = payload.get("products") or []
    if not products:
        return None

    product = products[0]
    nutriments = product.get("nutriments") or {}
    carbs_per_100g = nutriments.get("carbohydrates_100g")
    product_name = product.get("product_name") or query

    if carbs_per_100g is None:
        return None

    return {
        "name": str(product_name),
        "carbs_per_100g": float(carbs_per_100g),
        "source": "Open Food Facts",
    }


def estimate_carbs_from_text(
    meal_text: str,
    foods_df: pd.DataFrame,
    use_openfoodfacts: bool = True,
) -> dict:
    """Оценивает углеводы по пользовательскому описанию приёма пищи."""
    parsed_items = parse_meal_text(meal_text)
    estimated_items = []
    not_found = []

    for item in parsed_items:
        food = find_local_food(item["query"], foods_df)
        if food is None and use_openfoodfacts:
            food = fetch_openfoodfacts_food(item["query"])

        if food is None:
            not_found.append(item)
            continue

        carbs_g = food["carbs_per_100g"] * item["weight_g"] / 100
        estimated_items.append(
            {
                "query": item["query"],
                "name": food["name"],
                "weight_g": item["weight_g"],
                "carbs_per_100g": round(food["carbs_per_100g"], 2),
                "carbs_g": round(carbs_g, 2),
                "source": food["source"],
            }
        )

    total_carbs = sum(item["carbs_g"] for item in estimated_items)

    return {
        "items": estimated_items,
        "not_found": not_found,
        "total_carbs": round(total_carbs, 2),
    }
