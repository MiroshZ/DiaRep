"""FastAPI-версия сайта DiaAgent."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from calculator import calculate_total_bolus
from database import get_history, init_db, save_calculation
from gemini_agent import GeminiFoodRecognitionError, recognize_food_from_image
from llm_agent import generate_explanation
from models import BolusInput
from nightscout import NightscoutError, fetch_current_glucose
from nutrition import estimate_nutrition_from_text
from safety import check_safety

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "site" / "static"
INDEX_PATH = BASE_DIR / "site" / "index.html"

class BolusRequest(BaseModel):
    meal_text: str = Field(min_length=1)
    insulin_to_carb_ratio: float = Field(gt=0)
    target_glucose_mmol: float = Field(gt=0)
    correction_factor_mmol: float = Field(gt=0)
    active_insulin: float = Field(default=0, ge=0)
    current_glucose_mmol: Optional[float] = Field(default=None, gt=0)
    use_nightscout: bool = False
    nightscout_url: str = ""
    nightscout_api_key: str = ""


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="DiaAgent", version="0.2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(INDEX_PATH)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/history")
def history(limit: int = 20) -> dict:
    return {"items": get_history(limit=limit)}


@app.post("/api/nightscout/current")
def nightscout_current(payload: dict) -> dict:
    try:
        return fetch_current_glucose(
            payload.get("nightscout_url", ""),
            payload.get("nightscout_api_key", ""),
        )
    except NightscoutError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/recognize-food-photo")
async def recognize_food_photo(file: UploadFile = File(...)) -> dict:
    image_bytes = await file.read()
    try:
        return recognize_food_from_image(
            image_bytes,
            file.content_type or "application/octet-stream",
        )
    except GeminiFoodRecognitionError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/calculate")
def calculate(payload: BolusRequest) -> dict:
    nutrition = estimate_nutrition_from_text(payload.meal_text)
    current_glucose_mmol = payload.current_glucose_mmol
    glucose_data = None

    if payload.use_nightscout:
        try:
            glucose_data = fetch_current_glucose(
                payload.nightscout_url,
                payload.nightscout_api_key,
            )
        except NightscoutError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        current_glucose_mmol = glucose_data["glucose_mmol"]

    if current_glucose_mmol is None:
        raise HTTPException(
            status_code=422,
            detail="Укажите текущую глюкозу или подключите Nightscout.",
        )

    input_data = BolusInput(
        carbs_g=nutrition["total_carbs"],
        insulin_to_carb_ratio=payload.insulin_to_carb_ratio,
        current_glucose_mmol=current_glucose_mmol,
        target_glucose_mmol=payload.target_glucose_mmol,
        correction_factor_mmol=payload.correction_factor_mmol,
        active_insulin=payload.active_insulin,
    )
    result = calculate_total_bolus(**input_data.model_dump())
    warnings = check_safety(
        input_data.current_glucose_mmol,
        result["total_bolus"],
        input_data.carbs_g,
    )
    explanation = generate_explanation(input_data, result, warnings)
    save_calculation(input_data, result, warnings)

    return {
        "input": input_data.model_dump(),
        "nutrition": nutrition,
        "glucose": glucose_data,
        "result": result,
        "warnings": warnings,
        "explanation": explanation,
    }
