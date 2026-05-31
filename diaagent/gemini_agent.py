"""Распознавание еды по фото через Gemini в Polza.ai."""

import base64
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

from dotenv import load_dotenv

POLZA_CHAT_COMPLETIONS_URL = "https://polza.ai/api/v1/chat/completions"
DEFAULT_GEMINI_MODEL = "google/gemini-3.1-flash-lite"
MAX_IMAGE_BYTES = 8 * 1024 * 1024

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")


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

    api_key = api_key or os.getenv("POLZA_AI_API_KEY")
    if not api_key:
        raise GeminiFoodRecognitionError(
            "Не задан POLZA_AI_API_KEY. Добавьте ключ Polza.ai в переменные окружения."
        )

    model = model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    image_base64 = base64.b64encode(image_bytes).decode("ascii")
    image_url = f"data:{mime_type};base64,{image_base64}"
    prompt = (
        "Ты анализируешь фото еды для приложения подсчёта углеводов. "
        "Определи видимые продукты и примерный вес каждого продукта в граммах. "
        "Если вес нельзя оценить точно, дай осторожную приблизительную оценку. "
        "Не давай медицинских советов. Ответь строго JSON без markdown: "
        '{"items":[{"name":"название продукта на русском","weight_g":120,'
        '"confidence":"низкая|средняя|высокая"}],"notes":"короткое пояснение"}'
    )
    request_payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url, "detail": "low"},
                    },
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 600,
        "response_format": {"type": "json_object"},
    }
    request = Request(
        POLZA_CHAT_COMPLETIONS_URL,
        data=json.dumps(request_payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=35) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except Exception as error:  # noqa: BLE001
        raise GeminiFoodRecognitionError(f"Polza.ai API недоступен: {error}") from error

    choices = response_payload.get("choices") or []
    if not choices:
        raise GeminiFoodRecognitionError("Polza.ai вернул ответ без результата.")

    message = choices[0].get("message") or {}
    payload = _extract_json(str(message.get("content") or ""))
    items = _normalize_items(payload)
    if not items:
        raise GeminiFoodRecognitionError("Не удалось распознать продукты на фото.")

    return {
        "items": items,
        "meal_text": build_meal_text(items),
        "notes": str(payload.get("notes", "")).strip(),
        "model": model,
    }
