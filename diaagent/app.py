"""Streamlit-интерфейс DiaAgent."""

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from calculator import calculate_total_bolus
from database import get_history, get_user_settings, init_db, save_calculation, save_user_settings
from llm_agent import generate_explanation
from models import BolusInput
from nightscout import NightscoutError, fetch_current_glucose
from nutrition import estimate_nutrition_from_text
from safety import check_safety


def format_meal_items(items: list[dict]) -> pd.DataFrame:
    """Готовит аккуратную таблицу распознанных продуктов."""
    return pd.DataFrame(
        [
            {
                "Продукт": item["name"],
                "Масса, г": item["weight_g"],
                "Белки, г": item["protein_g"],
                "Жиры, г": item["fat_g"],
                "Углеводы на 100 г": item["carbs_per_100g"],
                "Углеводы, г": item["carbs_g"],
                "Ккал": item["kcal"],
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

if "meal_estimate" not in st.session_state:
    st.session_state.meal_estimate = None

if "nightscout_glucose" not in st.session_state:
    st.session_state.nightscout_glucose = None

user_settings = get_user_settings()
nightscout_connected = bool(
    user_settings.get("paid_access_active")
    and user_settings.get("nightscout_url")
    and user_settings.get("nightscout_api_key")
)

calc_tab, history_tab, account_tab = st.tabs(["Главная", "История", "Личный кабинет"])

with calc_tab:
    st.subheader("Еда и параметры расчёта")
    st.markdown(
        '<div class="diaagent-note">'
        "Опишите еду с массой в граммах и укажите индивидуальные коэффициенты. "
        "Если Nightscout подключён, текущая глюкоза будет получена автоматически."
        "</div>",
        unsafe_allow_html=True,
    )

    if nightscout_connected:
        st.success("Nightscout подключён. Текущая глюкоза будет взята из профиля.")
    else:
        st.info(
            "Для автоматического получения текущей глюкозы подключите Nightscout "
            "в личном кабинете."
        )

    with st.form("bolus_form"):
        meal_text = st.text_area(
            "Что планируется съесть",
            value="гречки 50 грамм",
            height=110,
            help="Можно указать несколько продуктов: гречки 50 грамм, банан 120 г.",
        )

        col_left, col_right = st.columns(2)

        with col_left:
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
            if not nightscout_connected:
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

        submitted = st.form_submit_button("Оценить еду и рассчитать болюс")

    if submitted:
        with st.spinner("Получаю БЖУ и считаю болюс..."):
            meal_estimate = estimate_nutrition_from_text(meal_text)
            st.session_state.meal_estimate = meal_estimate
            carbs_g = meal_estimate["total_carbs"]

            if nightscout_connected:
                try:
                    glucose_data = fetch_current_glucose(
                        user_settings["nightscout_url"],
                        user_settings["nightscout_api_key"],
                    )
                except NightscoutError as error:
                    st.error(str(error))
                    st.stop()

                st.session_state.nightscout_glucose = glucose_data
                current_glucose_mmol = glucose_data["glucose_mmol"]

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

            if nightscout_connected and st.session_state.nightscout_glucose:
                glucose_data = st.session_state.nightscout_glucose
                st.subheader("Глюкоза из Nightscout")
                glucose_cols = st.columns(3)
                glucose_cols[0].metric(
                    "Текущая глюкоза",
                    f"{glucose_data['glucose_mmol']} ммоль/л",
                )
                glucose_cols[1].metric(
                    "Nightscout SGV",
                    f"{glucose_data['glucose_mgdl']:.0f} мг/дл",
                )
                glucose_cols[2].metric("Тренд", glucose_data["direction"])
                if glucose_data["age_minutes"] is not None:
                    st.caption(
                        f"Последнее значение получено примерно "
                        f"{glucose_data['age_minutes']} мин. назад."
                    )

            st.subheader("Распознанная еда")
            if meal_estimate["items"]:
                meal_items_df = format_meal_items(meal_estimate["items"])
                st.dataframe(
                    meal_items_df,
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info(
                    "Не удалось распознать продукты и массу. Попробуйте написать "
                    "проще, например: гречки 50 грамм."
                )

            if meal_estimate["not_found"]:
                missing_names = ", ".join(
                    item["query"] for item in meal_estimate["not_found"]
                )
                st.info(
                    "Не удалось найти углеводы для: "
                    f"{missing_names}. Проверьте название или укажите продукт проще."
                )

            st.caption(
                "Данные БЖУ получены из внешних источников: All The Nutrients "
                "или Open Food Facts. Значения стоит проверять по упаковке продукта."
            )

            st.subheader("Результат")
            nutrition_cols = st.columns(4)
            nutrition_cols[0].metric("Белки", f"{meal_estimate['total_protein']} г")
            nutrition_cols[1].metric("Жиры", f"{meal_estimate['total_fat']} г")
            nutrition_cols[2].metric("Углеводы", f"{input_data.carbs_g} г")
            nutrition_cols[3].metric("Ккал", f"{meal_estimate['total_kcal']}")

            metric_cols = st.columns(4)
            metric_cols[0].metric("Болюс на еду", f"{result['meal_bolus']} ед.")
            metric_cols[1].metric(
                "Коррекционный болюс",
                f"{result['correction_bolus']} ед.",
            )
            metric_cols[2].metric("Активный инсулин", f"{result['active_insulin']} ед.")
            metric_cols[3].metric("Итоговый болюс", f"{result['total_bolus']} ед.")

            st.subheader("Важные предупреждения")
            for warning in warnings:
                st.warning(warning)

            st.subheader("Пояснение")
            st.write(explanation)

with history_tab:
    st.subheader("Последние расчёты")
    history = get_history(limit=20)
    if history:
        history_df = format_history(history)
        st.dataframe(history_df, use_container_width=True, hide_index=True)
    else:
        st.info("История расчётов пока пуста.")

with account_tab:
    st.subheader("Личный кабинет")
    st.markdown(
        '<div class="diaagent-note">'
        "Здесь можно активировать доступ к интеграции и привязать Nightscout. "
        "Ключ сохраняется только в локальной SQLite-базе этого проекта."
        "</div>",
        unsafe_allow_html=True,
    )

    with st.form("account_form"):
        paid_access_active = st.checkbox(
            "Платный доступ активен",
            value=bool(user_settings.get("paid_access_active")),
        )
        nightscout_url = st.text_input(
            "Адрес Nightscout",
            value=user_settings.get("nightscout_url", ""),
            placeholder="https://example-nightscout.ru",
        )
        nightscout_api_key = st.text_input(
            "API key / token Nightscout",
            value=user_settings.get("nightscout_api_key", ""),
            type="password",
        )
        save_account = st.form_submit_button("Сохранить настройки")

    if save_account:
        save_user_settings(
            {
                "paid_access_active": str(paid_access_active).lower(),
                "nightscout_url": nightscout_url.strip(),
                "nightscout_api_key": nightscout_api_key.strip(),
            }
        )
        st.success("Настройки сохранены локально. Обновите страницу, чтобы применить их.")

    if user_settings.get("nightscout_url") and user_settings.get("nightscout_api_key"):
        if st.button("Проверить подключение Nightscout"):
            try:
                glucose_data = fetch_current_glucose(
                    user_settings["nightscout_url"],
                    user_settings["nightscout_api_key"],
                )
            except NightscoutError as error:
                st.error(str(error))
            else:
                st.success(
                    "Подключение работает. "
                    f"Последняя глюкоза: {glucose_data['glucose_mmol']} ммоль/л."
                )

    st.warning(
        "Не публикуйте API key Nightscout в открытом доступе. Для внешних приложений "
        "лучше использовать read-only token с ограниченными правами."
    )
