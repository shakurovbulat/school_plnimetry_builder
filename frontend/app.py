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
from frontend.presentation import FIGURES, constraint_label

st.set_page_config(
    page_title="Планиметрия · Построитель чертежей", page_icon="📐", layout="wide"
)
st.markdown(
    f"<style>{Path(__file__).with_name('styles.css').read_text(encoding='utf-8')}</style>",
    unsafe_allow_html=True,
)
API = os.getenv("GEOMETRY_API_URL", "http://127.0.0.1:8000").rstrip("/")
canvas = components.declare_component(
    "geometry_canvas", path=str(Path(__file__).parent / "geometry_component")
)


def post(endpoint, payload):
    response = requests.post(f"{API}/{endpoint}", json=payload, timeout=240)
    if not response.ok:
        detail = response.json().get("detail", "Ошибка запроса")
        raise ValueError(
            detail
            if isinstance(detail, str)
            else "Некорректные данные. Проверьте условие задачи."
        )
    return response.json()


with st.sidebar:
    st.markdown("### 📐 Планиметрия")
    st.divider()
    st.markdown("#### Библиотека примеров")
    preset = st.selectbox("Выберите задачу", list(EXERCISES))
    if st.button("Загрузить пример", use_container_width=True):
        st.session_state["task_text"] = EXERCISES[preset]
    st.divider()
    st.markdown("#### История построений")
    if st.button("Обновить историю", use_container_width=True):
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
        if st.button("Открыть построение", use_container_width=True):
            try:
                response = requests.get(
                    f"{API}/history/{history[selected]['id']}", timeout=10
                )
                response.raise_for_status()
                item = response.json()
                st.session_state.update(
                    solution=item["result"],
                    task_text=item["text"],
                    solution_text=item["text"],
                )
                st.session_state["drawing_version"] = (
                    st.session_state.get("drawing_version", 0) + 1
                )
            except (requests.RequestException, ValueError):
                st.error("Не удалось открыть чертёж")


st.title("Построитель чертежей")
with st.container(border=True):
    st.subheader("Условие задачи")
    text = st.text_area(
        "Условие задачи",
        key="task_text",
        height=135,
        max_chars=6000,
        placeholder="Например: в треугольнике ABC AB = 5, AC = 6, BC = 7. AM — медиана.",
        label_visibility="collapsed",
    )
    generate = st.button("Построить", type="primary")
    st.caption("Текст отправляется внешнему API Apilsin.")
    if generate:
        if not text.strip():
            st.warning("Поле ввода не может быть пустым")
        else:
            try:
                with st.spinner("Распознаю условие и проверяю геометрию…"):
                    st.session_state["solution"] = post("solve", {"text": text})
                    st.session_state["solution_text"] = text
                st.session_state["drawing_version"] = (
                    st.session_state.get("drawing_version", 0) + 1
                )
            except (requests.RequestException, ValueError) as exc:
                st.session_state.pop("solution", None)
                st.error(f"Не удалось построить чертёж: {exc}")

if "solution" in st.session_state:
    sol = st.session_state["solution"]
    source_text = st.session_state.get("solution_text", text)
    if text != source_text:
        st.warning("Условие изменено. Нажмите «Построить» для обновления чертежа.")
    for warning in sol.get("warnings", []):
        st.warning(warning)
    left, right = st.columns([2.4, 1], gap="large")
    with left:
        event = canvas(
            solution=sol,
            key=f"drawing-{st.session_state.get('drawing_version', 0)}",
            default=None,
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
        for col, fmt in zip(st.columns(2), ["png", "svg"]):
            col.download_button(
                f"Скачать {fmt.upper()}",
                export_drawing(sol, fmt),
                file_name=f"geometry_drawing_{stamp}.{fmt}",
                mime="image/png" if fmt == "png" else "image/svg+xml",
                use_container_width=True,
            )
    with right, st.container(border=True):
        st.subheader("Объекты и связи")
        st.write("**Точки:** " + ", ".join(sol["points"]))
        for figure in sol.get("figures", []):
            st.write(f"{FIGURES.get(figure['type'], figure['type'])} {figure['name']}")
        st.divider()
        for constraint in sol["schema"].get("constraints", []):
            st.write(constraint_label(constraint))
