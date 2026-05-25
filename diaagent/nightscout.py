"""Клиент для чтения текущей глюкозы из Nightscout."""

import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

MGDL_TO_MMOLL = 18.0182
USER_AGENT = "DiaAgent-MVP/0.1 (Nightscout glucose read)"


class NightscoutError(Exception):
    """Ошибка получения данных Nightscout."""


def normalize_nightscout_url(base_url: str) -> str:
    """Приводит URL Nightscout к базовому виду без завершающего слеша."""
    normalized = base_url.strip()
    if not normalized:
        raise NightscoutError("Укажите адрес Nightscout.")

    if not normalized.startswith(("http://", "https://")):
        normalized = f"https://{normalized}"

    return normalized.rstrip("/")


def mgdl_to_mmol(value_mgdl: float) -> float:
    """Переводит глюкозу из мг/дл в ммоль/л."""
    return round(float(value_mgdl) / MGDL_TO_MMOLL, 1)


def _load_json(url: str, api_key: str | None = None, use_header: bool = False) -> object:
    headers = {"User-Agent": USER_AGENT}
    if api_key and use_header:
        headers["api-secret"] = hashlib.sha1(api_key.encode("utf-8")).hexdigest()

    request = Request(url, headers=headers)
    with urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def _extract_entry(payload: object) -> dict | None:
    if isinstance(payload, list) and payload:
        return payload[0]

    if isinstance(payload, dict):
        if "sgv" in payload:
            return payload
        entries = payload.get("entries")
        if isinstance(entries, list) and entries:
            return entries[0]

    return None


def _entry_age_minutes(entry: dict) -> int | None:
    entry_date = entry.get("date")
    if entry_date is None:
        return None

    try:
        entry_dt = datetime.fromtimestamp(float(entry_date) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None

    delta = datetime.now(timezone.utc) - entry_dt
    return max(round(delta.total_seconds() / 60), 0)


def fetch_current_glucose(base_url: str, api_key: str | None = None) -> dict:
    """Получает последнее значение SGV из Nightscout."""
    normalized_url = normalize_nightscout_url(base_url)
    api_key = (api_key or "").strip()

    query = urlencode({"count": 1, "token": api_key}) if api_key else "count=1"
    endpoints = [
        f"{normalized_url}/api/v1/entries/current.json",
        f"{normalized_url}/api/v1/entries/sgv.json?{query}",
        f"{normalized_url}/api/v1/entries.json?{query}",
    ]

    errors = []
    for endpoint in endpoints:
        for use_header in (False, True):
            if use_header and not api_key:
                continue
            try:
                payload = _load_json(endpoint, api_key=api_key, use_header=use_header)
            except Exception as error:  # noqa: BLE001
                errors.append(str(error))
                continue

            entry = _extract_entry(payload)
            if not entry or entry.get("sgv") is None:
                continue

            glucose_mgdl = float(entry["sgv"])
            return {
                "glucose_mgdl": round(glucose_mgdl, 0),
                "glucose_mmol": mgdl_to_mmol(glucose_mgdl),
                "direction": entry.get("direction") or "нет данных",
                "date_string": entry.get("dateString") or "",
                "age_minutes": _entry_age_minutes(entry),
                "source_url": normalized_url,
            }

    details = "; ".join(errors[-2:]) if errors else "нет данных SGV"
    raise NightscoutError(f"Не удалось получить текущую глюкозу: {details}")
