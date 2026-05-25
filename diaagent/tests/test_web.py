import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import web  # noqa: E402


client = TestClient(web.app)


def test_index_page_is_served() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "DiaAgent" in response.text


def test_health_endpoint() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_calculate_endpoint(monkeypatch) -> None:
    def fake_estimate_nutrition_from_text(meal_text: str) -> dict:
        return {
            "items": [
                {
                    "name": "Rice",
                    "weight_g": 100,
                    "protein_g": 2.4,
                    "fat_g": 0.2,
                    "carbs_g": 28.6,
                    "kcal": 130,
                    "source": "test",
                }
            ],
            "not_found": [],
            "total_protein": 2.4,
            "total_fat": 0.2,
            "total_carbs": 60,
            "total_kcal": 130,
        }

    monkeypatch.setattr(
        web,
        "estimate_nutrition_from_text",
        fake_estimate_nutrition_from_text,
    )
    response = client.post(
        "/api/calculate",
        json={
            "meal_text": "рис 100 г",
            "insulin_to_carb_ratio": 12,
            "target_glucose_mmol": 6,
            "correction_factor_mmol": 2,
            "active_insulin": 1,
            "current_glucose_mmol": 10,
        },
    )

    assert response.status_code == 200
    assert response.json()["result"]["total_bolus"] == 6
