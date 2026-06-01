"""SQLite-хранилище истории учебных расчётов."""

import json
import sqlite3
import hashlib
import secrets
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
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                paid_access_active INTEGER DEFAULT 0,
                nightscout_url TEXT DEFAULT '',
                nightscout_api_key TEXT DEFAULT '',
                insulin_to_carb_ratio REAL DEFAULT 12,
                target_glucose_mmol REAL DEFAULT 6,
                correction_factor_mmol REAL DEFAULT 2,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
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
        "user_id": "INTEGER",
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
    user_id: int | None = None,
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
                user_id,
                warnings
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                user_id,
                json.dumps(warnings, ensure_ascii=False),
            ),
        )
        connection.commit()


def get_history(
    limit: int = 20,
    user_id: int | None = None,
    db_path: str = "diaagent.db",
) -> list[dict]:
    """Возвращает последние учебные расчёты."""
    init_db(db_path)
    path = _resolve_db_path(db_path)

    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        where_clause = ""
        params: tuple = (limit,)
        if user_id is not None:
            where_clause = "WHERE user_id = ?"
            params = (user_id, limit)

        rows = connection.execute(
            f"""
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
                user_id,
                warnings
            FROM calculations
            {where_clause}
            ORDER BY id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    return [dict(row) for row in rows]


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120_000,
    )
    return digest.hex()


def create_user(
    name: str,
    email: str,
    password: str,
    db_path: str = "diaagent.db",
) -> dict:
    """Создаёт пользователя для личного кабинета."""
    init_db(db_path)
    path = _resolve_db_path(db_path)
    salt = secrets.token_hex(16)
    password_hash = _hash_password(password, salt)

    with sqlite3.connect(path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO users (created_at, name, email, password_salt, password_hash)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                name.strip(),
                _normalize_email(email),
                salt,
                password_hash,
            ),
        )
        user_id = cursor.lastrowid
        connection.execute(
            "INSERT INTO user_profiles (user_id) VALUES (?)",
            (user_id,),
        )
        connection.commit()

    return {"id": user_id, "name": name.strip(), "email": _normalize_email(email)}


def authenticate_user(
    email: str,
    password: str,
    db_path: str = "diaagent.db",
) -> dict | None:
    """Проверяет логин и пароль пользователя."""
    init_db(db_path)
    path = _resolve_db_path(db_path)

    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT id, name, email, password_salt, password_hash
            FROM users
            WHERE email = ?
            """,
            (_normalize_email(email),),
        ).fetchone()

    if row is None:
        return None

    expected_hash = _hash_password(password, row["password_salt"])
    if not secrets.compare_digest(expected_hash, row["password_hash"]):
        return None

    return {"id": row["id"], "name": row["name"], "email": row["email"]}


def create_session(user_id: int, db_path: str = "diaagent.db") -> str:
    """Создаёт токен сессии."""
    init_db(db_path)
    path = _resolve_db_path(db_path)
    token = secrets.token_urlsafe(32)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO sessions (token, user_id, created_at)
            VALUES (?, ?, ?)
            """,
            (token, user_id, datetime.now().isoformat(timespec="seconds")),
        )
        connection.commit()

    return token


def get_user_by_token(token: str, db_path: str = "diaagent.db") -> dict | None:
    """Возвращает пользователя по токену сессии."""
    if not token:
        return None

    init_db(db_path)
    path = _resolve_db_path(db_path)
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT users.id, users.name, users.email
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ?
            """,
            (token,),
        ).fetchone()

    if row is None:
        return None

    return {"id": row["id"], "name": row["name"], "email": row["email"]}


def delete_session(token: str, db_path: str = "diaagent.db") -> None:
    """Удаляет токен сессии."""
    init_db(db_path)
    path = _resolve_db_path(db_path)
    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM sessions WHERE token = ?", (token,))
        connection.commit()


def save_user_profile(
    user_id: int,
    profile: dict,
    db_path: str = "diaagent.db",
) -> None:
    """Сохраняет профиль Nightscout и личные коэффициенты пользователя."""
    init_db(db_path)
    path = _resolve_db_path(db_path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO user_profiles (
                user_id,
                paid_access_active,
                nightscout_url,
                nightscout_api_key,
                insulin_to_carb_ratio,
                target_glucose_mmol,
                correction_factor_mmol
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                paid_access_active = excluded.paid_access_active,
                nightscout_url = excluded.nightscout_url,
                nightscout_api_key = excluded.nightscout_api_key,
                insulin_to_carb_ratio = excluded.insulin_to_carb_ratio,
                target_glucose_mmol = excluded.target_glucose_mmol,
                correction_factor_mmol = excluded.correction_factor_mmol
            """,
            (
                user_id,
                1 if profile.get("paid_access_active") else 0,
                profile.get("nightscout_url", "").strip(),
                profile.get("nightscout_api_key", "").strip(),
                float(profile.get("insulin_to_carb_ratio", 12)),
                float(profile.get("target_glucose_mmol", 6)),
                float(profile.get("correction_factor_mmol", 2)),
            ),
        )
        connection.commit()


def get_user_profile(user_id: int, db_path: str = "diaagent.db") -> dict:
    """Возвращает профиль пользователя."""
    init_db(db_path)
    path = _resolve_db_path(db_path)
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT
                paid_access_active,
                nightscout_url,
                nightscout_api_key,
                insulin_to_carb_ratio,
                target_glucose_mmol,
                correction_factor_mmol
            FROM user_profiles
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

    if row is None:
        return {
            "paid_access_active": False,
            "nightscout_url": "",
            "nightscout_api_key": "",
            "insulin_to_carb_ratio": 12,
            "target_glucose_mmol": 6,
            "correction_factor_mmol": 2,
        }

    return {
        "paid_access_active": bool(row["paid_access_active"]),
        "nightscout_url": row["nightscout_url"],
        "nightscout_api_key": row["nightscout_api_key"],
        "insulin_to_carb_ratio": row["insulin_to_carb_ratio"],
        "target_glucose_mmol": row["target_glucose_mmol"],
        "correction_factor_mmol": row["correction_factor_mmol"],
    }


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
