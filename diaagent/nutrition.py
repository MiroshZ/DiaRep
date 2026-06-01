"""Оценка БЖУ продуктов через внешние API."""

import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ALL_THE_NUTRIENTS_FOOD_URL = "https://allthenutrients.com/api/v1/foods"
OPENFOODFACTS_SEARCH_URL = "https://ru.openfoodfacts.org/api/v2/search"
USER_AGENT = "DiaRep/1.0 (nutrition lookup; contact: github.com/MiroshZ/DiaRep)"

API_SLUG_HINTS = {
    "пепперон": "pizza-pepperoni-topping-regular-crust-frozen-cooked",
    "pepperoni": "pizza-pepperoni-topping-regular-crust-frozen-cooked",
    "пицц": "pizza-cheese-topping-regular-crust-frozen-cooked",
    "pizza": "pizza-cheese-topping-regular-crust-frozen-cooked",
    "греч": "buckwheat-groats-roasted-cooked",
    "рис": "rice-white-medium-grain-cooked-unenriched",
    "банан": "bananas-raw",
    "яблок": "apples-raw-golden-delicious-with-skin",
    "яйц": "egg-whole-cooked-hard-boiled",
    "молок": "milk-whole-3-25-milkfat-with-added-vitamin-d",
    "йогурт": "yogurt-plain-whole-milk",
    "хлеб": "bread-white-commercially-prepared",
    "карто": "potatoes-boiled-cooked-without-skin-flesh-without-salt",
    "овсян": "oats-whole-grain-rolled-old-fashioned",
    "арахис": "peanuts-raw",
    "черник": "blueberries-raw",
}

MEAL_ITEM_PATTERN = re.compile(
    r"([а-яёa-z\s-]+?)\s*(?:[-—–]\s*)?(\d+(?:[,.]\d+)?)\s*(?:г|гр|грамм|граммов)\b",
    re.IGNORECASE,
)
QUANTITY_WORDS = {
    "пол": 0.5,
    "половина": 0.5,
    "половинку": 0.5,
    "один": 1,
    "одна": 1,
    "одно": 1,
    "два": 2,
    "две": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
    "шесть": 6,
    "семь": 7,
    "восемь": 8,
    "девять": 9,
    "десять": 10,
}
QUANTITY_VALUE_PATTERN = (
    r"\d+(?:[,.]\d+)?|"
    + "|".join(sorted(QUANTITY_WORDS, key=len, reverse=True))
)
QUANTITY_BEFORE_PATTERN = re.compile(
    rf"^(?P<quantity>{QUANTITY_VALUE_PATTERN})\s+"
    r"(?P<name>[а-яёa-z][а-яёa-z\s-]*?)"
    r"(?:\s+(?:шт\.?|штук|штуки|штука|порция|порции|кусок|куска|кусочка))?$",
    re.IGNORECASE,
)
QUANTITY_AFTER_PATTERN = re.compile(
    r"^(?P<name>[а-яёa-z][а-яёa-z\s-]*?)\s+"
    rf"(?P<quantity>{QUANTITY_VALUE_PATTERN})"
    r"\s*(?:шт\.?|штук|штуки|штука|порция|порции|кусок|куска|кусочка)?$",
    re.IGNORECASE,
)
COMPACT_HALF_PATTERN = re.compile(
    r"^пол(?P<name>[а-яёa-z-]{3,})$",
    re.IGNORECASE,
)
PORTION_WEIGHT_HINTS_G = {
    "банан": 120,
    "яблок": 180,
    "яйц": 50,
    "хлеб": 30,
    "карто": 120,
    "пицц": 450,
    "йогурт": 125,
    "творог": 180,
    "молок": 200,
    "курин": 120,
    "грудк": 120,
    "котлет": 80,
    "сырник": 70,
    "блин": 60,
}


def parse_meal_text(meal_text: str) -> list[dict]:
    """Разбирает фразу вида 'гречки 50 грамм, один банан, 2 яйца'."""
    items = []
    parts = split_meal_parts(meal_text)

    for part in parts:
        gram_items = parse_gram_items(part)
        if gram_items:
            items.extend(gram_items)
            continue

        quantity_item = parse_quantity_item(part)
        if quantity_item:
            items.append(quantity_item)

    return items


def split_meal_parts(meal_text: str) -> list[str]:
    """Делит описание еды на отдельные продукты."""
    return [
        part.strip(" ,.;")
        for part in re.split(r"[,;\n]+|\s+\+\s+|\s+и\s+", meal_text)
        if part.strip(" ,.;")
    ]


def parse_gram_items(text: str) -> list[dict]:
    """Находит продукты с явно указанным весом в граммах."""
    items = []
    for match in MEAL_ITEM_PATTERN.finditer(text):
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


def parse_quantity_value(value: str) -> float:
    """Преобразует число или простое русское числительное в количество."""
    normalized = value.lower().replace(",", ".").strip()
    if normalized in QUANTITY_WORDS:
        return QUANTITY_WORDS[normalized]

    try:
        return float(normalized)
    except ValueError:
        return 0


def estimate_portion_weight_g(query: str) -> float | None:
    """Возвращает примерный вес одной штуки или обычной порции продукта."""
    normalized_query = normalize_food_name(query)
    for keyword, weight_g in PORTION_WEIGHT_HINTS_G.items():
        if keyword in normalized_query:
            return weight_g

    return None


def parse_quantity_item(text: str) -> dict | None:
    """Разбирает продукты, указанные количеством: 'один банан' или 'банан 1 шт'."""
    cleaned = text.strip(" ,.;")
    match = COMPACT_HALF_PATTERN.match(cleaned)
    quantity = 0.5 if match else 0
    raw_name = match.group("name") if match else ""

    if not match:
        match = QUANTITY_BEFORE_PATTERN.match(cleaned) or QUANTITY_AFTER_PATTERN.match(
            cleaned
        )
        if not match:
            return None

        quantity = parse_quantity_value(match.group("quantity"))
        raw_name = match.group("name")

    raw_name = raw_name.strip(" ,.;")
    portion_weight_g = estimate_portion_weight_g(raw_name)
    if not raw_name or quantity <= 0 or portion_weight_g is None:
        return None

    return {
        "query": raw_name,
        "weight_g": round(quantity * portion_weight_g, 2),
        "quantity": quantity,
        "portion_weight_g": portion_weight_g,
    }


def normalize_food_name(value: str) -> str:
    """Нормализует название продукта перед запросом к API."""
    normalized = value.lower().replace("ё", "е")
    normalized = re.sub(r"[^а-яa-z\s-]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def build_search_queries(query: str) -> list[str]:
    """Создаёт несколько вариантов поискового запроса без локального справочника."""
    normalized = normalize_food_name(query)
    words = normalized.split()
    variants = [normalized]

    if words:
        first_word = words[0]
        for ending in ("и", "ы", "а", "у", "ю", "е", "ой", "ою", "ом", "ам"):
            if first_word.endswith(ending) and len(first_word) > len(ending) + 2:
                variants.append(" ".join([first_word[: -len(ending)], *words[1:]]))

    unique_variants = []
    for variant in variants:
        if variant and variant not in unique_variants:
            unique_variants.append(variant)

    return unique_variants


def product_matches_query(product_name: str, query: str) -> bool:
    """Проверяет, похож ли найденный продукт на исходный запрос."""
    normalized_name = normalize_food_name(product_name)
    normalized_query = normalize_food_name(query)
    if not normalized_name or not normalized_query:
        return False

    if normalized_query in normalized_name or normalized_name in normalized_query:
        return True

    query_tokens = set(normalized_query.split())
    name_tokens = set(normalized_name.split())
    return bool(query_tokens & name_tokens)


def _to_float(value: object, default: float = 0) -> float:
    if value is None:
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def find_api_slug(query: str) -> str | None:
    """Подбирает slug внешнего API без хранения локальных БЖУ."""
    normalized_query = normalize_food_name(query)
    for keyword, slug in API_SLUG_HINTS.items():
        if keyword in normalized_query:
            return slug

    return None


def _extract_nutrient(nutrients: list[dict], names: tuple[str, ...]) -> float:
    for nutrient in nutrients:
        if nutrient.get("name") in names:
            return _to_float(nutrient.get("amount"))

    return 0


def fetch_allthenutrients_food(query: str, timeout_seconds: int = 5) -> dict | None:
    """Получает БЖУ продукта из All The Nutrients API."""
    slug = find_api_slug(query)
    if slug is None:
        return None

    request = Request(
        f"{ALL_THE_NUTRIENTS_FOOD_URL}/{slug}.json",
        headers={"User-Agent": USER_AGENT},
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, json.JSONDecodeError):
        return None

    food = payload.get("food") or {}
    nutrients = payload.get("nutrients") or []

    return {
        "name": str(food.get("name") or query),
        "protein_per_100g": _extract_nutrient(nutrients, ("Protein",)),
        "fat_per_100g": _extract_nutrient(nutrients, ("Total lipid (fat)",)),
        "carbs_per_100g": _extract_nutrient(
            nutrients,
            ("Carbohydrate, by difference",),
        ),
        "kcal_per_100g": _extract_nutrient(nutrients, ("Energy",)),
        "source": "All The Nutrients",
        "source_url": food.get("sourceUrl") or f"{ALL_THE_NUTRIENTS_FOOD_URL}/{slug}.json",
    }


def fetch_openfoodfacts_food(query: str, timeout_seconds: int = 5) -> dict | None:
    """Ищет продукт в Open Food Facts и возвращает БЖУ на 100 г."""
    for search_query in build_search_queries(query):
        params = urlencode(
            {
                "search_terms": search_query,
                "fields": "product_name,product_name_ru,nutriments,url",
                "page_size": 5,
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
            continue

        products = payload.get("products") or []
        if not products:
            continue

        for product in products:
            nutriments = product.get("nutriments") or {}
            carbs_per_100g = nutriments.get("carbohydrates_100g")
            if carbs_per_100g is None:
                continue

            product_name = (
                product.get("product_name_ru")
                or product.get("product_name")
                or search_query
            )
            if not product_matches_query(str(product_name), search_query):
                continue

            return {
                "name": str(product_name),
                "protein_per_100g": _to_float(nutriments.get("proteins_100g")),
                "fat_per_100g": _to_float(nutriments.get("fat_100g")),
                "carbs_per_100g": _to_float(carbs_per_100g),
                "kcal_per_100g": _to_float(nutriments.get("energy-kcal_100g")),
                "source": "Open Food Facts",
                "source_url": product.get("url") or "https://ru.openfoodfacts.org/",
            }

    return None


def fetch_food_nutrition(query: str) -> dict | None:
    """Получает БЖУ из внешних источников без локального справочника продуктов."""
    return fetch_allthenutrients_food(query) or fetch_openfoodfacts_food(query)


def estimate_nutrition_from_text(meal_text: str) -> dict:
    """Оценивает БЖУ по пользовательскому описанию приёма пищи."""
    parsed_items = parse_meal_text(meal_text)
    estimated_items = []
    not_found = []

    for item in parsed_items:
        food = fetch_food_nutrition(item["query"])
        if food is None:
            not_found.append(item)
            continue

        weight_factor = item["weight_g"] / 100
        estimated_items.append(
            {
                "query": item["query"],
                "name": food["name"],
                "weight_g": item["weight_g"],
                "protein_per_100g": round(food["protein_per_100g"], 2),
                "fat_per_100g": round(food["fat_per_100g"], 2),
                "carbs_per_100g": round(food["carbs_per_100g"], 2),
                "kcal_per_100g": round(food["kcal_per_100g"], 2),
                "protein_g": round(food["protein_per_100g"] * weight_factor, 2),
                "fat_g": round(food["fat_per_100g"] * weight_factor, 2),
                "carbs_g": round(food["carbs_per_100g"] * weight_factor, 2),
                "kcal": round(food["kcal_per_100g"] * weight_factor, 2),
                "source": food["source"],
                "source_url": food["source_url"],
            }
        )

    return {
        "items": estimated_items,
        "not_found": not_found,
        "total_protein": round(sum(item["protein_g"] for item in estimated_items), 2),
        "total_fat": round(sum(item["fat_g"] for item in estimated_items), 2),
        "total_carbs": round(sum(item["carbs_g"] for item in estimated_items), 2),
        "total_kcal": round(sum(item["kcal"] for item in estimated_items), 2),
    }
