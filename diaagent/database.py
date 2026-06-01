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
    """Создаёт таблицы приложения, если их ещё нет."""
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
        _ensure_calculation_columns(connection)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        connection.commit()


def _ensure_calculation_columns(connection: sqlite3.Connection) -> None:
    """Добавляет новые поля истории без удаления старых расчётов."""
    rows = connection.execute("PRAGMA table_info(calculations)").fetchall()
    existing_columns = {row[1] for row in rows}
    columns = {
        "meal_text": "TEXT DEFAULT ''",
        "protein_g": "REAL DEFAULT 0",
        "fat_g": "REAL DEFAULT 0",
        "kcal": "REAL DEFAULT 0",
        "glucose_source": "TEXT DEFAULT 'manual'",
    }

    for column, definition in columns.items():
        if column not in existing_columns:
            connection.execute(
                f"ALTER TABLE calculations ADD COLUMN {column} {definition}"
            )


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
    meal_text: str = "",
    nutrition: dict | None = None,
    glucose_source: str = "manual",
    db_path: str = "diaagent.db",
) -> None:
    """Сохраняет один учебный расчёт в SQLite."""
    init_db(db_path)
    input_data = _to_dict(data)
    nutrition = nutrition or {}
    path = _resolve_db_path(db_path)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO calculations (
                created_at,
                meal_text,
                carbs_g,
                protein_g,
                fat_g,
                kcal,
                insulin_to_carb_ratio,
                current_glucose_mmol,
                target_glucose_mmol,
                correction_factor_mmol,
                active_insulin,
                meal_bolus,
                correction_bolus,
                total_bolus,
                glucose_source,
                warnings
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                meal_text,
                input_data["carbs_g"],
                nutrition.get("total_protein", 0),
                nutrition.get("total_fat", 0),
                nutrition.get("total_kcal", 0),
                input_data["insulin_to_carb_ratio"],
                input_data["current_glucose_mmol"],
                input_data["target_glucose_mmol"],
                input_data["correction_factor_mmol"],
                input_data.get("active_insulin", 0),
                result["meal_bolus"],
                result["correction_bolus"],
                result["total_bolus"],
                glucose_source,
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
                meal_text,
                carbs_g,
                protein_g,
                fat_g,
                kcal,
                insulin_to_carb_ratio,
                current_glucose_mmol,
                target_glucose_mmol,
                correction_factor_mmol,
                active_insulin,
                meal_bolus,
                correction_bolus,
                total_bolus,
                glucose_source,
                warnings
            FROM calculations
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def save_user_settings(settings: dict, db_path: str = "diaagent.db") -> None:
    """Сохраняет настройки личного кабинета в локальную SQLite-базу."""
    init_db(db_path)
    path = _resolve_db_path(db_path)

    with sqlite3.connect(path) as connection:
        for key, value in settings.items():
            connection.execute(
                """
                INSERT INTO user_settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, str(value)),
            )
        connection.commit()


def get_user_settings(db_path: str = "diaagent.db") -> dict:
    """Возвращает настройки личного кабинета."""
    init_db(db_path)
    path = _resolve_db_path(db_path)

    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("SELECT key, value FROM user_settings").fetchall()

    settings = {row["key"]: row["value"] for row in rows}
    settings["paid_access_active"] = (
        settings.get("paid_access_active", "false").lower() == "true"
    )
    return settings
