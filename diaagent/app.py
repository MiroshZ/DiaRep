"""Streamlit-интерфейс учебного прототипа DiaAgent."""

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from calculator import calculate_total_bolus
from database import get_history, init_db, save_calculation
from llm_agent import generate_explanation
from models import BolusInput
from nutrition import load_foods
from safety import check_safety


st.set_page_config(
    page_title="DiaAgent",
    page_icon="D",
    layout="wide",
)

init_db()

st.title("DiaAgent — учебный ИИ-агент для анализа питания и расчёта болюса")
st.warning(
    "Приложение является учебным прототипом и не является медицинским изделием. "
    "Расчёт не является медицинской рекомендацией, не заменяет врача и должен "
    "использовать только индивидуальные параметры, которые пользователь уже "
    "получил от медицинского специалиста."
)

if "estimated_carbs_g" not in st.session_state:
    st.session_state.estimated_carbs_g = 60.0

st.header("База продуктов")
foods_df = load_foods()

with st.expander("Посмотреть таблицу продуктов", expanded=True):
    st.dataframe(foods_df, use_container_width=True, hide_index=True)

food_col, weight_col, result_col = st.columns(3)
with food_col:
    selected_food = st.selectbox("Продукт", foods_df["name"].tolist())
with weight_col:
    weight_g = st.number_input("Масса продукта, г", min_value=0.0, value=100.0, step=10.0)

food_row = foods_df.loc[foods_df["name"] == selected_food].iloc[0]
estimated_carbs = round(float(food_row["carbs_per_100g"]) * weight_g / 100, 2)

with result_col:
    st.metric("Примерные углеводы", f"{estimated_carbs} г")
    if st.button("Использовать в расчёте"):
        st.session_state.estimated_carbs_g = estimated_carbs
        st.success("Количество углеводов перенесено в форму расчёта.")

st.header("Учебный расчёт болюса")

with st.form("bolus_form"):
    col_left, col_right = st.columns(2)

    with col_left:
        carbs_g = st.number_input(
            "Углеводы, г",
            min_value=0.0,
            value=float(st.session_state.estimated_carbs_g),
            step=1.0,
        )
        insulin_to_carb_ratio = st.number_input(
            "Углеводный коэффициент, г углеводов на 1 ед. инсулина",
            min_value=0.1,
            value=12.0,
            step=0.5,
        )
        active_insulin = st.number_input(
            "Активный инсулин, ед.",
            min_value=0.0,
            value=0.0,
            step=0.1,
        )

    with col_right:
        current_glucose_mmol = st.number_input(
            "Текущая глюкоза, ммоль/л",
            min_value=0.1,
            value=6.5,
            step=0.1,
        )
        target_glucose_mmol = st.number_input(
            "Целевая глюкоза, ммоль/л",
            min_value=0.1,
            value=6.0,
            step=0.1,
        )
        correction_factor_mmol = st.number_input(
            "Фактор чувствительности, ммоль/л на 1 ед. инсулина",
            min_value=0.1,
            value=2.0,
            step=0.1,
        )

    submitted = st.form_submit_button("Рассчитать учебный болюс")

if submitted:
    try:
        input_data = BolusInput(
            carbs_g=carbs_g,
            insulin_to_carb_ratio=insulin_to_carb_ratio,
            current_glucose_mmol=current_glucose_mmol,
            target_glucose_mmol=target_glucose_mmol,
            correction_factor_mmol=correction_factor_mmol,
            active_insulin=active_insulin,
        )
    except ValidationError as error:
        st.error("Проверьте введённые данные. Значения должны быть положительными.")
        st.code(str(error), language="text")
    else:
        result = calculate_total_bolus(**input_data.model_dump())
        warnings = check_safety(
            input_data.current_glucose_mmol,
            result["total_bolus"],
            input_data.carbs_g,
        )
        explanation = generate_explanation(input_data, result, warnings)
        save_calculation(input_data, result, warnings)

        metric_cols = st.columns(4)
        metric_cols[0].metric("Болюс на еду", f"{result['meal_bolus']} ед.")
        metric_cols[1].metric("Коррекционный болюс", f"{result['correction_bolus']} ед.")
        metric_cols[2].metric("Активный инсулин", f"{result['active_insulin']} ед.")
        metric_cols[3].metric("Итоговый учебный болюс", f"{result['total_bolus']} ед.")

        st.subheader("Предупреждения")
        for warning in warnings:
            st.warning(warning)

        st.subheader("Объяснение агента")
        st.write(explanation)

st.header("История последних расчётов")
history = get_history(limit=20)
if history:
    history_df = pd.DataFrame(history)
    st.dataframe(history_df, use_container_width=True, hide_index=True)
else:
    st.info("История расчётов пока пуста.")
