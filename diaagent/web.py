"""FastAPI-версия сайта DiaAgent."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
import sqlite3

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from calculator import calculate_total_bolus
from database import (
    authenticate_user,
    create_session,
    create_user,
    delete_session,
    get_history,
    get_user_by_token,
    get_user_profile,
    init_db,
    save_calculation,
    save_user_profile,
)
from gemini_agent import GeminiFoodRecognitionError, recognize_food_from_image
from llm_agent import generate_explanation
from models import BolusInput
from nightscout import NightscoutError, fetch_current_glucose
from nutrition import estimate_nutrition_from_text
from safety import check_safety

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "site" / "static"
INDEX_PATH = BASE_DIR / "site" / "index.html"
CALCULATOR_PATH = BASE_DIR / "site" / "calculator.html"
ACCOUNT_PATH = BASE_DIR / "site" / "account.html"
JOURNAL_PATH = BASE_DIR / "site" / "journal.html"


class AuthRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=6)


class RegisterRequest(AuthRequest):
    name: str = Field(min_length=2)


class ProfileRequest(BaseModel):
    paid_access_active: bool = False
    nightscout_url: str = ""
    nightscout_api_key: str = ""
    insulin_to_carb_ratio: float = Field(default=12, gt=0)
    target_glucose_mmol: float = Field(default=6, gt=0)
    correction_factor_mmol: float = Field(default=2, gt=0)


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


def _token_from_header(authorization: str | None) -> str:
    if not authorization:
        return ""
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return authorization.strip()


def _optional_user(authorization: str | None) -> dict | None:
    return get_user_by_token(_token_from_header(authorization))


def _require_user(authorization: str | None) -> dict:
    user = _optional_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Войдите в личный кабинет.")
    return user


def _public_profile(profile: dict) -> dict:
    return {
        **profile,
        "nightscout_api_key": "",
        "nightscout_connected": bool(
            profile.get("nightscout_url") and profile.get("nightscout_api_key")
        ),
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(INDEX_PATH)


@app.get("/calculator")
def calculator_page() -> FileResponse:
    return FileResponse(CALCULATOR_PATH)


@app.get("/account")
def account_page() -> FileResponse:
    return FileResponse(ACCOUNT_PATH)


@app.get("/journal")
def journal_page() -> FileResponse:
    return FileResponse(JOURNAL_PATH)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/history")
def history(limit: int = 20, authorization: str | None = Header(default=None)) -> dict:
    user = _optional_user(authorization)
    return {
        "items": get_history(limit=limit, user_id=user["id"] if user else None),
        "authenticated": user is not None,
    }


@app.post("/api/auth/register")
def register(payload: RegisterRequest) -> dict:
    try:
        user = create_user(payload.name, payload.email, payload.password)
    except sqlite3.IntegrityError as error:
        raise HTTPException(
            status_code=409,
            detail="Пользователь с таким email уже зарегистрирован.",
        ) from error

    token = create_session(user["id"])
    return {"token": token, "user": user}


@app.post("/api/auth/login")
def login(payload: AuthRequest) -> dict:
    user = authenticate_user(payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Неверный email или пароль.")

    token = create_session(user["id"])
    return {"token": token, "user": user}


@app.get("/api/auth/me")
def me(authorization: str | None = Header(default=None)) -> dict:
    user = _require_user(authorization)
    return {"user": user, "profile": _public_profile(get_user_profile(user["id"]))}


@app.post("/api/auth/logout")
def logout(authorization: str | None = Header(default=None)) -> dict:
    token = _token_from_header(authorization)
    if token:
        delete_session(token)
    return {"status": "ok"}


@app.get("/api/profile")
def profile(authorization: str | None = Header(default=None)) -> dict:
    user = _require_user(authorization)
    return {"profile": _public_profile(get_user_profile(user["id"]))}


@app.post("/api/profile")
def update_profile(
    payload: ProfileRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    user = _require_user(authorization)
    profile_data = payload.model_dump()
    if not profile_data["nightscout_api_key"]:
        existing_profile = get_user_profile(user["id"])
        profile_data["nightscout_api_key"] = existing_profile.get(
            "nightscout_api_key",
            "",
        )
    save_user_profile(user["id"], profile_data)
    return {"profile": _public_profile(get_user_profile(user["id"]))}


@app.post("/api/nightscout/current")
def nightscout_current(
    payload: dict,
    authorization: str | None = Header(default=None),
) -> dict:
    user = _optional_user(authorization)
    profile = get_user_profile(user["id"]) if user else {}
    nightscout_url = payload.get("nightscout_url") or profile.get("nightscout_url", "")
    nightscout_api_key = payload.get("nightscout_api_key") or profile.get(
        "nightscout_api_key",
        "",
    )

    try:
        return fetch_current_glucose(
            nightscout_url,
            nightscout_api_key,
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
def calculate(
    payload: BolusRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    user = _optional_user(authorization)
    user_profile = get_user_profile(user["id"]) if user else {}
    nutrition = estimate_nutrition_from_text(payload.meal_text)
    current_glucose_mmol = payload.current_glucose_mmol
    glucose_data = None

    if payload.use_nightscout:
        try:
            glucose_data = fetch_current_glucose(
                payload.nightscout_url or user_profile.get("nightscout_url", ""),
                payload.nightscout_api_key
                or user_profile.get("nightscout_api_key", ""),
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
    explanation = generate_explanation(input_data, result, warnings, nutrition)
    save_calculation(
        input_data,
        result,
        warnings,
        meal_text=payload.meal_text,
        nutrition=nutrition,
        glucose_source="nightscout" if payload.use_nightscout else "manual",
        user_id=user["id"] if user else None,
    )

    return {
        "input": input_data.model_dump(),
        "nutrition": nutrition,
        "glucose": glucose_data,
        "result": result,
        "warnings": warnings,
        "explanation": explanation,
    }
