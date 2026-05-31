import math
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Импортируем наши модули
from backend.parser import parse_geometry_text
from backend.solver import solve_geometry

app = FastAPI(title="Geometry Solver API")


class TaskRequest(BaseModel):
    text: str


def calculate_coordinates(parsed_data: dict, solved_data: dict) -> tuple:
    points = {}
    lines = []

    # 1. Базовый треугольник ABC (задаем жестко форму, раз длины сторон не важны для отношений)
    A, B, C = "A", "B", "C"
    points[A] = [0.0, 0.0]
    points[B] = [6.0, 0.0]
    points[C] = [4.0, 5.0]

    lines.extend([[A, B], [B, C], [C, A]])

    # 2. Ищем точки, которые делят стороны (M на AC, N на BC)
    ratios = parsed_data.get("ratios", [])

    # Обрабатываем точку M на AC (AM : MC = 2 : 1)
    ratio_m = next((r for r in ratios if "AM" in r["pair"] or "MC" in r["pair"]), None)
    if ratio_m:
        # Лямбда = AM / MC = 2 / 1 = 2.0
        # Координаты точки M: M = (A + lambda*C) / (1 + lambda)
        lmbda = ratio_m["ratio"][0] / ratio_m["ratio"][1]
        x_m = (points[A][0] + lmbda * points[C][0]) / (1 + lmbda)
        y_m = (points[A][1] + lmbda * points[C][1]) / (1 + lmbda)
        points["M"] = [round(x_m, 2), round(y_m, 2)]
        lines.append([B, "M"])  # Отрезок BM

    # Обрабатываем точку N на BC (CN : BN = 3 : 1) -> перевернем как BN : NC = 1 : 3
    ratio_n = next((r for r in ratios if "CN" in r["pair"] or "BN" in r["pair"]), None)
    if ratio_n:
        # Нам нужно отношение от B к C, то есть BN / NC.
        # Из текста CN:BN = 3:1 => BN/NC = 1/3
        lmbda = 1 / 3
        x_n = (points[B][0] + lmbda * points[C][0]) / (1 + lmbda)
        y_n = (points[B][1] + lmbda * points[C][1]) / (1 + lmbda)
        points["N"] = [round(x_n, 2), round(y_n, 2)]
        lines.append([A, "N"])  # Отрезок AN

    # 3. Находим точку пересечения P (пересечение отрезков AN и BM)
    # Используем формулу пересечения двух прямых по четырем точкам
    if "M" in points and "N" in points:
        x1, y1 = points[A]
        x2, y2 = points["N"]
        x3, y3 = points[B]
        x4, y4 = points["M"]

        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if denom != 0:
            px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denom
            py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denom
            points["P"] = [round(px, 2), round(py, 2)]

            # Добавим линии к точке P для красоты отображения треугольников APC и CPB
            lines.extend([["C", "P"]])

    # Фоллбек для непредвиденных точек
    for p in parsed_data.get("points", []):
        if p not in points:
            points[p] = [3.0, 2.5]

    return points, lines


@app.post("/solve")
async def solve_geometry_task(request: TaskRequest):
    print(f"📥 [FastAPI] Получен текст задачи: {request.text}")

    try:
        # Шаг 1: Парсим текст с помощью нашей Yargy-грамматики
        parsed_data = parse_geometry_text(request.text)
        print(f"🧩 Найдено парсером: {parsed_data}")

        # Шаг 2: Передаем структурированные факты в SymPy-солвер
        # По умолчанию пытаемся найти perimeter, если в тексте просят найти что-то другое — переопределим
        target = "perimeter"
        if "площадь" in request.text.lower():
            target = "area"

        solver_result = solve_geometry(parsed_data, target_find=target)
        print(f"⚙️ Результат расчета SymPy: {solver_result}")

        # Шаг 3: Вычисляем плоские декартовы координаты для чертежа Matplotlib
        points, lines = calculate_coordinates(parsed_data, solver_result)

        # Шаг 4: Формируем красивый JSON-ответ для Streamlit
        return {
            "status": "success",
            "parser_data": parsed_data,
            "solver_data": solver_result,
            "points": points,
            "lines": lines
        }

    except Exception as e:
        print(f"❌ Ошибка пайплайна: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    # Запуск сервера: uvicorn запускает экземпляр app из текущего модуля main
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)