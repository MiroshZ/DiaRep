"""Streamlit-интерфейс DiaAgent."""

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from calculator import calculate_total_bolus
from database import get_history, init_db, save_calculation
from llm_agent import generate_explanation
from models import BolusInput
from nutrition import estimate_carbs_from_text, load_foods
from safety import check_safety


def use_estimated_carbs(estimated_carbs: float) -> None:
    """Переносит рассчитанные углеводы в форму болюса."""
    st.session_state.estimated_carbs_g = estimated_carbs
    st.session_state.carbs_g = estimated_carbs


def format_meal_items(items: list[dict]) -> pd.DataFrame:
    """Готовит аккуратную таблицу распознанных продуктов."""
    return pd.DataFrame(
        [
            {
                "Продукт": item["name"],
                "Масса, г": item["weight_g"],
                "Углеводы на 100 г": item["carbs_per_100g"],
                "Углеводы, г": item["carbs_g"],
                "Источник": item["source"],
            }
            for item in items
        ]
    )


def format_history(history: list[dict]) -> pd.DataFrame:
    """Показывает историю в пользовательском виде без служебных полей."""
    history_df = pd.DataFrame(history)
    if history_df.empty:
        return history_df

    history_df = history_df[
        [
            "created_at",
            "carbs_g",
            "current_glucose_mmol",
            "target_glucose_mmol",
            "meal_bolus",
            "correction_bolus",
            "active_insulin",
            "total_bolus",
        ]
    ].copy()
    history_df["created_at"] = pd.to_datetime(history_df["created_at"]).dt.strftime(
        "%d.%m.%Y %H:%M"
    )

    return history_df.rename(
        columns={
            "created_at": "Дата",
            "carbs_g": "Углеводы, г",
            "current_glucose_mmol": "Глюкоза, ммоль/л",
            "target_glucose_mmol": "Цель, ммоль/л",
            "meal_bolus": "На еду, ед.",
            "correction_bolus": "Коррекция, ед.",
            "active_insulin": "Активный инсулин, ед.",
            "total_bolus": "Итог, ед.",
        }
    )


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

if "meal_estimate" not in st.session_state:
    st.session_state.meal_estimate = None

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
    st.subheader("Опишите приём пищи")
    st.markdown(
        '<div class="diaagent-note">'
        "Например: гречки 50 грамм, банан 120 г, йогурт 150 г."
        "</div>",
        unsafe_allow_html=True,
    )

    meal_text = st.text_area(
        "Что планируется съесть",
        value="гречки 50 грамм",
        height=110,
    )

    if st.button("Оценить углеводы"):
        with st.spinner("Считаю углеводы по описанию..."):
            st.session_state.meal_estimate = estimate_carbs_from_text(
                meal_text,
                foods_df,
                use_openfoodfacts=True,
            )

    if st.session_state.meal_estimate:
        meal_estimate = st.session_state.meal_estimate

        st.metric("Всего углеводов", f"{meal_estimate['total_carbs']} г")

        if meal_estimate["items"]:
            meal_items_df = format_meal_items(meal_estimate["items"])
            st.dataframe(
                meal_items_df,
                use_container_width=True,
                hide_index=True,
            )

            if st.button(
                "Перенести углеводы в расчёт",
                on_click=use_estimated_carbs,
                args=(meal_estimate["total_carbs"],),
            ):
                st.success("Количество углеводов перенесено в форму расчёта.")

        if meal_estimate["not_found"]:
            missing_names = ", ".join(item["query"] for item in meal_estimate["not_found"])
            st.info(
                "Не удалось найти углеводы для: "
                f"{missing_names}. Проверьте название или укажите продукт проще."
            )

        st.caption(
            "Часть данных может подбираться из Open Food Facts. Значения стоит "
            "проверять по упаковке продукта."
        )

with history_tab:
    st.subheader("Последние расчёты")
    history = get_history(limit=20)
    if history:
        history_df = format_history(history)
        st.dataframe(history_df, use_container_width=True, hide_index=True)
    else:
        st.info("История расчётов пока пуста.")
