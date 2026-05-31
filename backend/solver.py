import numpy as np
import math
from scipy.optimize import minimize


# --- МАТЕМАТИЧЕСКИЕ ФУНКЦИИ-ОГРАНИЧЕНИЯ ДЛЯ SCIPY ---

def c_distance(p1, p2, target_val):
    """ Ошибка расстояния между точками """
    return (p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2 - target_val ** 2


def c_perpendicular(line1_p1, line1_p2, line2_p1, line2_p2):
    """ Ошибка перпендикулярности (скалярное произведение векторов = 0) """
    v1 = [line1_p2[0] - line1_p1[0], line1_p2[1] - line1_p1[1]]
    v2 = [line2_p2[0] - line2_p1[0], line2_p2[1] - line2_p1[1]]
    return v1[0] * v2[0] + v1[1] * v2[1]


def c_point_on_segment(p, seg_p1, seg_p2):
    """ Ошибка нахождения точки строго внутри границ отрезка """
    # Проверка коллинеарности (векторное произведение векторов = 0)
    cross_product = (p[1] - seg_p1[1]) * (seg_p2[0] - seg_p1[0]) - (p[0] - seg_p1[0]) * (seg_p2[1] - seg_p1[1])

    # Контроль границ: точка не должна вылетать за пределы отрезка
    v1 = [p[0] - seg_p1[0], p[1] - seg_p1[1]]
    v2 = [seg_p2[0] - seg_p1[0], seg_p2[1] - seg_p1[1]]
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    seg_len_sq = v2[0] ** 2 + v2[1] ** 2

    t = dot / seg_len_sq if seg_len_sq != 0 else 0
    penalty = 0 if 0 <= t <= 1 else min((t - 0) ** 2, (t - 1) ** 2) * 100

    return cross_product ** 2 + penalty


def c_equal_segments(s1_p1, s1_p2, s2_p1, s2_p2):
    """ Ошибка равенства длин двух разных отрезков """
    len1_sq = (s1_p2[0] - s1_p1[0]) ** 2 + (s1_p2[1] - s1_p1[1]) ** 2
    len2_sq = (s2_p2[0] - s2_p1[0]) ** 2 + (s2_p2[1] - s2_p1[1]) ** 2
    return len1_sq - len2_sq


def c_right_angle(p1, vertex, p2):
    """ Ошибка прямого угла """
    return c_perpendicular(vertex, p1, vertex, p2)


# --- ОСНОВНОЙ ДВИЖОК СБОРКИ СХЕМЫ ---

def build_geometry_schema(parsed_data: dict) -> dict:
    all_points = parsed_data.get("points", ["A", "B", "C"])
    constraints = parsed_data.get("constraints", [])

    # Карта индексов для плоского вектора SciPy
    pt_to_idx = {name: i for i, name in enumerate(all_points)}

    # Целевая функция оптимизации
    def loss_function(X):
        total_loss = 0

        def get_pt(name):
            idx = pt_to_idx[name]
            return [X[2 * idx], X[2 * idx + 1]]

        for constr in constraints:
            c_type = constr["type"]
            args = constr["args"]

            if c_type == "distance":
                total_loss += c_distance(get_pt(args[0]), get_pt(args[1]), constr["value"]) ** 2
            elif c_type == "perpendicular":
                total_loss += c_perpendicular(get_pt(args[0][0]), get_pt(args[0][1]), get_pt(args[1][0]),
                                              get_pt(args[1][1])) ** 2
            elif c_type == "point_on_segment":
                total_loss += c_point_on_segment(get_pt(args[0]), get_pt(args[1]), get_pt(args[2])) ** 2
            elif c_type == "equal_segments":
                total_loss += c_equal_segments(get_pt(args[0][0]), get_pt(args[0][1]), get_pt(args[1][0]),
                                               get_pt(args[1][1])) ** 2
            elif c_type == "right_angle":
                total_loss += c_right_angle(get_pt(args[0]), get_pt(args[1]), get_pt(args[2])) ** 2

        # Базовая фиксация начала координат в точке 'C' для стабилизации плоскости
        if "C" in pt_to_idx:
            c_coords = get_pt("C")
            total_loss += (c_coords[0] - 0) ** 2 + (c_coords[1] - 0) ** 2

        return total_loss

    # Раскидываем точки на старте по тригонометрическому кругу с шумом
    np.random.seed(42)
    X0 = []
    for i in range(len(all_points)):
        angle = i * (2 * math.pi / len(all_points))
        X0.extend([3.0 + 2.0 * math.cos(angle) + np.random.normal(0, 0.1),
                   3.0 + 2.0 * math.sin(angle) + np.random.normal(0, 0.1)])

    # Запуск оптимизатора
    res = minimize(loss_function, X0, method='SLSQP', options={'ftol': 1e-6, 'maxiter': 500})

    # Собираем финальные координаты точек
    final_X = res.x
    response_points = {}
    for name, idx in pt_to_idx.items():
        x_val = round(float(final_X[2 * idx]), 2)
        y_val = round(float(final_X[2 * idx + 1]), 2)
        response_points[name] = [x_val, y_val]

    response_lines = parsed_data.get("lines", [])
    print(f"🎯 Схема успешно построена численный методом. Ошибка Loss: {res.fun}")

    return {
        "points": response_points,
        "lines": response_lines
    }