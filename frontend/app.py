"""Local interface for building and editing planimetry drawings."""

import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import requests
import streamlit as st
import streamlit.components.v1 as components

from backend.sample_tasks import EXERCISES
from frontend.drawing import export_drawing
from frontend.highlight import highlight_condition

st.set_page_config(page_title="Построитель чертежей", page_icon="📐", layout="wide")
API = os.getenv("GEOMETRY_API_URL", "http://127.0.0.1:8000").rstrip("/")
canvas = components.declare_component(
    "geometry_canvas", path=str(Path(__file__).parent / "geometry_component")
)


def post(endpoint, payload):
    response = requests.post(f"{API}/{endpoint}", json=payload, timeout=240)
    if not response.ok:
        detail = response.json().get("detail", "Ошибка запроса")
        raise ValueError(
            detail if isinstance(detail, str) else "Некорректные данные. Проверьте условие задачи."
        )
    return response.json()


st.title("📐 Построитель чертежей для школьной планиметрии")
st.caption("Локальная нейросеть распознаёт условие, геометрическое ядро проверяет построение.")
with st.sidebar:
    st.header("Готовые примеры")
    preset = st.selectbox("Задача", list(EXERCISES))
    if st.button("Загрузить пример"):
        st.session_state["task_text"] = EXERCISES[preset]
    st.info(
        "Данные обрабатываются локально. Сложные и неоднозначные условия могут потребовать уточнения."
    )
    if st.button("Обновить историю"):
        try:
            response = requests.get(f"{API}/history", timeout=10)
            response.raise_for_status()
            st.session_state["history"] = response.json()
        except (requests.RequestException, ValueError):
            st.warning("История недоступна")
    history = st.session_state.get("history", [])
    if history:
        selected = st.selectbox(
            "Сохранённые построения",
            range(len(history)),
            format_func=lambda i: f"#{history[i]['id']} {history[i]['text'][:60]}",
        )
        if st.button("Открыть построение"):
            try:
                response = requests.get(f"{API}/history/{history[selected]['id']}", timeout=10)
                response.raise_for_status()
                item = response.json()
                st.session_state["solution"] = item["result"]
                st.session_state["task_text"] = item["text"]
                st.session_state["solution_text"] = item["text"]
                st.session_state["drawing_version"] = st.session_state.get("drawing_version", 0) + 1
            except (requests.RequestException, ValueError):
                st.error("Не удалось открыть чертёж")
text = st.text_area("Условие задачи", key="task_text", height=140)
if st.button("Сгенерировать чертёж", type="primary"):
    if not text.strip():
        st.warning("Поле ввода не может быть пустым")
    else:
        try:
            with st.spinner("Распознаю условие и проверяю геометрию…"):
                st.session_state["solution"] = post("solve", {"text": text})
                st.session_state["solution_text"] = text
            st.session_state["drawing_version"] = st.session_state.get("drawing_version", 0) + 1
            st.success("Чертёж построен. Ограничения проверены численно.")
        except (requests.RequestException, ValueError) as exc:
            st.session_state.pop("solution", None)
            st.error(f"Не удалось построить чертёж: {exc}")
if "solution" in st.session_state:
    sol = st.session_state["solution"]
    source_text = st.session_state.get("solution_text", text)
    if text != source_text:
        st.warning(
            "Условие изменено. На экране прежний чертёж — нажмите «Сгенерировать чертёж» для обновления."
        )
    with st.expander("Распознанные обозначения и числа в условии"):
        st.markdown(highlight_condition(source_text, sol["schema"]), unsafe_allow_html=True)
        st.caption(
            "Подсветка показывает совпадения обозначений и чисел, а не подтверждает полноту понимания текста."
        )
    for warning in sol.get("warnings", []):
        st.warning(warning)
    left, right = st.columns([3, 1])
    with left:
        event = canvas(
            solution=sol, key=f"drawing-{st.session_state.get('drawing_version', 0)}", default=None
        )
        if event and event.get("id") != st.session_state.get("last_edit"):
            st.session_state["last_edit"] = event["id"]
            try:
                with st.spinner("Пересчитываю зависимые объекты…"):
                    updated = post(
                        "update-point",
                        {
                            "schema_data": sol["schema"],
                            "points": sol["points"],
                            "point_name": event["point_name"],
                            "new_coords": event["new_coords"],
                        },
                    )
                st.session_state["solution"] = {**sol, **updated}
                st.session_state["drawing_version"] += 1
                st.rerun()
            except (requests.RequestException, ValueError) as exc:
                st.warning(f"Перемещение отклонено; сохранён исходный чертёж. {exc}")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        a, b = st.columns(2)
        for col, fmt in [(a, "png"), (b, "svg")]:
            col.download_button(
                f"Скачать {fmt.upper()}",
                export_drawing(sol, fmt),
                file_name=f"geometry_drawing_{stamp}.{fmt}",
                mime="image/png" if fmt == "png" else "image/svg+xml",
            )
    with right:
        st.subheader("Распознанные объекты")
        st.write("Точки: " + ", ".join(sol["points"]))
        for f in sol.get("figures", []):
            st.write(f"{f['name']} — {f['type']}")
        st.caption(sol.get("parser_engine", ""))
        st.subheader("Параметры и отношения")
        for c in sol["schema"].get("constraints", []):
            label = f"{c['type']}: {c['args']}"
            if c.get("value") is not None:
                st.write(f"{label} = {c['value']}")
            else:
                st.success(label)
        st.caption(
            "Численная проверка ограничений не заменяет математическое доказательство. Нераспознанные детали могут отсутствовать: сверьте список с условием."
        )
