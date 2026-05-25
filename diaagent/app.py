"""Streamlit-интерфейс DiaAgent."""

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from calculator import calculate_total_bolus
from database import get_history, init_db, save_calculation
from llm_agent import generate_explanation
from models import BolusInput
from nutrition import load_foods
from safety import check_safety


def use_estimated_carbs(estimated_carbs: float) -> None:
    """Переносит рассчитанные углеводы в форму болюса."""
    st.session_state.estimated_carbs_g = estimated_carbs
    st.session_state.carbs_g = estimated_carbs


st.set_page_config(
    page_title="DiaAgent",
    page_icon="D",
    layout="wide",
)

init_db()

st.markdown(
    """
    <style>
        .main .block-container {
            max-width: 1180px;
            padding-top: 2rem;
            padding-bottom: 3rem;
        }

        h1, h2, h3 {
            letter-spacing: 0;
        }

        div[data-testid="stMetric"] {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 1rem;
        }

        div[data-testid="stAlert"] {
            border-radius: 8px;
        }

        .stButton > button {
            border-radius: 8px;
            border: 1px solid #0f766e;
            background: #0f766e;
            color: white;
            font-weight: 600;
        }

        .stButton > button:hover {
            border-color: #115e59;
            background: #115e59;
            color: white;
        }

        .diaagent-note {
            color: #475569;
            font-size: 1rem;
            line-height: 1.55;
            margin-bottom: 1rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("DiaAgent")
st.markdown(
    '<div class="diaagent-note">'
    "Анализ питания и расчёт болюса по индивидуальным параметрам."
    "</div>",
    unsafe_allow_html=True,
)
st.warning(
    "Приложение не является медицинским изделием. Расчёт не является "
    "медицинской рекомендацией, не заменяет врача и должен использовать "
    "только индивидуальные параметры, которые пользователь уже получил "
    "от медицинского специалиста."
)

if "estimated_carbs_g" not in st.session_state:
    st.session_state.estimated_carbs_g = 60.0

if "carbs_g" not in st.session_state:
    st.session_state.carbs_g = float(st.session_state.estimated_carbs_g)

foods_df = load_foods()
calc_tab, foods_tab, history_tab = st.tabs(
    ["Расчёт болюса", "База продуктов", "История"]
)

with calc_tab:
    st.subheader("Параметры расчёта")

    with st.form("bolus_form"):
        col_left, col_right = st.columns(2)

        with col_left:
            carbs_g = st.number_input(
                "Углеводы, г",
                min_value=0.0,
                step=1.0,
                key="carbs_g",
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

        submitted = st.form_submit_button("Рассчитать болюс")

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

            st.subheader("Результат")
            metric_cols = st.columns(4)
            metric_cols[0].metric("Болюс на еду", f"{result['meal_bolus']} ед.")
            metric_cols[1].metric("Коррекционный болюс", f"{result['correction_bolus']} ед.")
            metric_cols[2].metric("Активный инсулин", f"{result['active_insulin']} ед.")
            metric_cols[3].metric("Итоговый болюс", f"{result['total_bolus']} ед.")

            st.subheader("Важные предупреждения")
            for warning in warnings:
                st.warning(warning)

            st.subheader("Пояснение")
            st.write(explanation)

with foods_tab:
    st.subheader("Расчёт углеводов по продукту")

    food_col, weight_col, result_col = st.columns(3)
    with food_col:
        selected_food = st.selectbox("Продукт", foods_df["name"].tolist())
    with weight_col:
        weight_g = st.number_input(
            "Масса продукта, г",
            min_value=0.0,
            value=100.0,
            step=10.0,
        )

    food_row = foods_df.loc[foods_df["name"] == selected_food].iloc[0]
    estimated_carbs = round(float(food_row["carbs_per_100g"]) * weight_g / 100, 2)

    with result_col:
        st.metric("Примерные углеводы", f"{estimated_carbs} г")
        if st.button(
            "Перенести в расчёт",
            on_click=use_estimated_carbs,
            args=(estimated_carbs,),
        ):
            st.success("Количество углеводов перенесено в форму расчёта.")

    with st.expander("Таблица продуктов", expanded=True):
        st.dataframe(foods_df, use_container_width=True, hide_index=True)

with history_tab:
    st.subheader("Последние расчёты")
    history = get_history(limit=20)
    if history:
        history_df = pd.DataFrame(history)
        st.dataframe(history_df, use_container_width=True, hide_index=True)
    else:
        st.info("История расчётов пока пуста.")
