from __future__ import annotations

import os

import matplotlib.pyplot as plt
import requests
import streamlit as st


DEFAULT_TEXT = (
    "В прямоугольном равнобедренном треугольнике ABC гипотенуза AB равна 14 см. "
    "Из точки F, принадлежащей отрезку AB, на катеты AC и BC соответственно "
    "опущены перпендикуляры FM и FN."
)

API_URL = os.getenv("GEOMETRY_API_URL", "http://127.0.0.1:8000")


def draw_schema(points: dict[str, list[float]], lines: list[list[str]]):
    fig, ax = plt.subplots(figsize=(7, 7))

    for line in lines:
        if line[0] not in points or line[1] not in points:
            continue
        p1, p2 = points[line[0]], points[line[1]]
        ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color="#2563eb", lw=2.2)
        mid_x, mid_y = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        ax.text(mid_x, mid_y, "".join(line), fontsize=9, color="#334155")

    for name, coords in points.items():
        ax.scatter(coords[0], coords[1], s=52, color="#dc2626", zorder=3)
        ax.text(coords[0] + 0.08, coords[1] + 0.08, name, fontsize=13, weight="bold")

    ax.grid(True, linestyle="--", alpha=0.35)
    ax.set_aspect("equal", adjustable="datalim")
    ax.margins(0.2)
    ax.axis("off")
    return fig


st.set_page_config(page_title="GeoSolver", layout="wide")

st.title("Интерактивный построитель планиметрии")
st.caption("Парсит условие, выделяет фигуры и ограничения, строит приближенный чертеж.")

with st.sidebar:
    st.header("Backend")
    api_url = st.text_input("API URL", value=API_URL)
    show_debug = st.checkbox("Показывать JSON парсера", value=True)

user_input = st.text_area(
    "Условие задачи",
    value=DEFAULT_TEXT,
    height=180,
    placeholder="Например: Треугольник ABC. AB = 4, BC = 3, AC = 5.",
)

col_run, col_status = st.columns([1, 4])
run_clicked = col_run.button("Построить", type="primary", use_container_width=True)
status_box = col_status.empty()

if run_clicked:
    text = user_input.strip()
    if not text:
        st.warning("Введите условие задачи.")
    else:
        with st.spinner("Разбираю условие и считаю координаты..."):
            try:
                response = requests.post(f"{api_url.rstrip('/')}/solve", json={"text": text}, timeout=20)
                response.raise_for_status()
                data = response.json()
            except requests.exceptions.ConnectionError:
                st.error("Не удалось подключиться к FastAPI. Запустите backend/main.py на порту 8000.")
                st.stop()
            except requests.RequestException as exc:
                st.error(f"Ошибка запроса к backend: {exc}")
                st.stop()

        points = data.get("points", {})
        lines = data.get("lines", [])
        diagnostics = data.get("diagnostics", {})
        parser_data = data.get("parser_data", {})

        if not points:
            st.warning("Парсер не нашел точек для построения.")
            st.stop()

        status_box.success(
            f"Готово: точек {len(points)}, линий {len(lines)}, "
            f"ограничений {len(parser_data.get('constraints', []))}."
        )

        chart_col, info_col = st.columns([2, 1])
        with chart_col:
            st.pyplot(draw_schema(points, lines), clear_figure=True)

        with info_col:
            st.subheader("Диагностика")
            st.write(diagnostics or {"status": "unknown"})
            st.subheader("Что найдено")
            st.write(
                {
                    "figures": parser_data.get("figures", []),
                    "givens": parser_data.get("givens", []),
                    "targets": parser_data.get("targets", []),
                }
            )

        if show_debug:
            st.subheader("Parser JSON")
            st.json(parser_data)
