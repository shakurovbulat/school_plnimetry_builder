import streamlit as st
import requests
import matplotlib.pyplot as plt

st.set_page_config(page_title="GeoSolver", layout="wide")

st.title("📐 Интерактивный геометрический решатель")
st.subheader("Автоматический разбор условий и визуализация")

# Поле ввода текста задачи
user_input = st.text_area(
    "Введите условие задачи на русском языке:",
    placeholder="Например: Треугольник ABC. Сторона AB равна 4, сторона BC равна 3..."
)

if st.button("Построить чертёж", type="primary"):
    if user_input.strip() == "":
        st.warning("Пожалуйста, введите текст задачи.")
    else:
        with st.spinner("Разбираем текст и считаем координаты..."):
            try:
                # Отправляем запрос на бэкенд
                response = requests.post(
                    "http://127.0.0.1:8000/solve",
                    json={"text": user_input}
                )

                if response.status_code == 200:
                    data = response.json()
                    points = data["points"]
                    lines = data["lines"]

                    # Отрисовка с помощью Matplotlib
                    fig, ax = plt.subplots(figsize=(6, 6))

                    # Рисуем линии
                    for line in lines:
                        p1, p2 = points[line[0]], points[line[1]]
                        ax.plot([p1[0], p2[0]], [p1[1], p2[1]], 'b-', lw=2)

                    # Рисуем и подписываем точки
                    for name, coords in points.items():
                        ax.plot(coords[0], coords[1], 'ro', markersize=8)
                        ax.text(coords[0] + 0.1, coords[1] + 0.1, name, fontsize=14, fontweight='bold')

                    # Настройки сетки
                    ax.grid(True, linestyle='--', alpha=0.6)
                    ax.set_aspect('equal', adjustable='box')

                    # Отображаем в Streamlit
                    st.pyplot(fig)

                    st.success("Чертёж успешно построен!")
                else:
                    st.error("Ошибка бэкенда при обработке задачи.")
            except requests.exceptions.ConnectionError:
                st.error("Не удалось соединиться с бэкендом. Убедитесь, что FastAPI запущен.")