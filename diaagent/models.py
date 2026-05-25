"""Pydantic-модели входных данных DiaAgent."""

from pydantic import BaseModel, Field


class BolusInput(BaseModel):
    """Входные параметры учебного расчёта болюса."""

    carbs_g: float = Field(ge=0)
    insulin_to_carb_ratio: float = Field(gt=0)
    current_glucose_mmol: float = Field(gt=0)
    target_glucose_mmol: float = Field(gt=0)
    correction_factor_mmol: float = Field(gt=0)
    active_insulin: float = Field(default=0, ge=0)
