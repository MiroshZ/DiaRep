"""SQLite-хранилище истории учебных расчётов."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


def _resolve_db_path(db_path: str) -> Path:
    path = Path(db_path)
    if not path.is_absolute():
        path = Path(__file__).parent / path
    return path


def init_db(db_path: str = "diaagent.db") -> None:
    """Создаёт таблицу истории расчётов, если её ещё нет."""
    path = _resolve_db_path(db_path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS calculations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT,
                carbs_g REAL,
                insulin_to_carb_ratio REAL,
                current_glucose_mmol REAL,
                target_glucose_mmol REAL,
                correction_factor_mmol REAL,
                active_insulin REAL,
                meal_bolus REAL,
                correction_bolus REAL,
                total_bolus REAL,
                warnings TEXT
            )
            """
        )
        connection.commit()


def _to_dict(data: Any) -> dict:
    if hasattr(data, "model_dump"):
        return data.model_dump()
    if hasattr(data, "dict"):
        return data.dict()
    return dict(data)


def save_calculation(
    data: Any,
    result: dict,
    warnings: list[str],
    db_path: str = "diaagent.db",
) -> None:
    """Сохраняет один учебный расчёт в SQLite."""
    init_db(db_path)
    input_data = _to_dict(data)
    path = _resolve_db_path(db_path)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO calculations (
                created_at,
                carbs_g,
                insulin_to_carb_ratio,
                current_glucose_mmol,
                target_glucose_mmol,
                correction_factor_mmol,
                active_insulin,
                meal_bolus,
                correction_bolus,
                total_bolus,
                warnings
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                input_data["carbs_g"],
                input_data["insulin_to_carb_ratio"],
                input_data["current_glucose_mmol"],
                input_data["target_glucose_mmol"],
                input_data["correction_factor_mmol"],
                input_data.get("active_insulin", 0),
                result["meal_bolus"],
                result["correction_bolus"],
                result["total_bolus"],
                json.dumps(warnings, ensure_ascii=False),
            ),
        )
        connection.commit()


def get_history(limit: int = 20, db_path: str = "diaagent.db") -> list[dict]:
    """Возвращает последние учебные расчёты."""
    init_db(db_path)
    path = _resolve_db_path(db_path)

    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                id,
                created_at,
                carbs_g,
                insulin_to_carb_ratio,
                current_glucose_mmol,
                target_glucose_mmol,
                correction_factor_mmol,
                active_insulin,
                meal_bolus,
                correction_bolus,
                total_bolus,
                warnings
            FROM calculations
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]
