"""Распознавание еды по фото через Gemini."""

import json
import os

from google import genai
from google.genai import types

DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
MAX_IMAGE_BYTES = 8 * 1024 * 1024


class GeminiFoodRecognitionError(Exception):
    """Ошибка распознавания еды по фото."""


def _extract_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise GeminiFoodRecognitionError("Gemini вернул ответ без JSON.")

    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as error:
        raise GeminiFoodRecognitionError("Не удалось разобрать JSON от Gemini.") from error


def _normalize_items(payload: dict) -> list[dict]:
    items = payload.get("items")
    if not isinstance(items, list):
        return []

    normalized_items = []
    for item in items:
        if not isinstance(item, dict):
            continue

        name = str(item.get("name", "")).strip().lower()
        try:
            weight_g = float(item.get("weight_g", 0))
        except (TypeError, ValueError):
            weight_g = 0

        if not name or weight_g <= 0:
            continue

        confidence = item.get("confidence", "средняя")
        if confidence not in ("низкая", "средняя", "высокая"):
            confidence = "средняя"

        normalized_items.append(
            {
                "name": name,
                "weight_g": round(weight_g),
                "confidence": confidence,
            }
        )

    return normalized_items


def build_meal_text(items: list[dict]) -> str:
    """Собирает строку еды для основного расчёта."""
    return ", ".join(f"{item['name']} {item['weight_g']} г" for item in items)


def recognize_food_from_image(
    image_bytes: bytes,
    mime_type: str,
    api_key: str | None = None,
    model: str | None = None,
) -> dict:
    """Возвращает примерный список продуктов и веса по фото."""
    if not image_bytes:
        raise GeminiFoodRecognitionError("Файл изображения пустой.")

    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise GeminiFoodRecognitionError("Изображение больше 8 МБ.")

    if not mime_type.startswith("image/"):
        raise GeminiFoodRecognitionError("Загрузите изображение еды.")

    api_key = api_key or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise GeminiFoodRecognitionError(
            "Не задан GEMINI_API_KEY. Добавьте ключ Gemini API в переменные окружения."
        )

    model = model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    client = genai.Client(api_key=api_key)
    prompt = (
        "Ты анализируешь фото еды для приложения подсчёта углеводов. "
        "Определи видимые продукты и примерный вес каждого продукта в граммах. "
        "Если вес нельзя оценить точно, дай осторожную приблизительную оценку. "
        "Не давай медицинских советов. Ответь строго JSON без markdown: "
        '{"items":[{"name":"название продукта на русском","weight_g":120,'
        '"confidence":"низкая|средняя|высокая"}],"notes":"короткое пояснение"}'
    )

    try:
        response = client.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                prompt,
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
    except Exception as error:  # noqa: BLE001
        raise GeminiFoodRecognitionError(f"Gemini API недоступен: {error}") from error

    payload = _extract_json(response.text or "")
    items = _normalize_items(payload)
    if not items:
        raise GeminiFoodRecognitionError("Не удалось распознать продукты на фото.")

    return {
        "items": items,
        "meal_text": build_meal_text(items),
        "notes": str(payload.get("notes", "")).strip(),
        "model": model,
    }
