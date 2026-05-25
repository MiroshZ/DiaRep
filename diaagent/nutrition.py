"""Работа с учебной таблицей продуктов."""

from pathlib import Path

import pandas as pd


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
