"""Readable labels for the geometry inspector."""

FIGURES = {
    "triangle": "Треугольник",
    "right_triangle": "Прямоугольный треугольник",
    "isosceles_triangle": "Равнобедренный треугольник",
    "equilateral_triangle": "Равносторонний треугольник",
    "quadrilateral": "Четырёхугольник",
    "parallelogram": "Параллелограмм",
    "rectangle": "Прямоугольник",
    "square": "Квадрат",
    "rhombus": "Ромб",
    "trapezoid": "Трапеция",
    "circle": "Окружность",
    "segment": "Отрезок",
    "regular_polygon": "Правильный многоугольник",
    "line": "Прямая",
}
LABELS = {
    "distance": "Длина",
    "angle": "Угол",
    "right_angle": "Прямой угол",
    "equal_segments": "Равные отрезки",
    "equal_angles": "Равные углы",
    "ratio": "Отношение",
    "parallel": "Параллельность",
    "perpendicular": "Перпендикулярность",
    "midpoint": "Середина",
    "projection": "Основание перпендикуляра",
    "bisector": "Биссектриса",
    "external_bisector": "Внешняя биссектриса",
    "point_on_segment": "Точка на отрезке",
    "point_on_line": "Точка на прямой",
    "point_between": "Точка между",
    "collinear": "Коллинеарность",
    "tangent": "Касательная",
    "external_tangency": "Внешнее касание",
    "point_on_circle": "Точка на окружности",
    "circle_radius": "Радиус",
    "circle_center": "Центр",
    "circumscribed_circle": "Описанная окружность",
    "inscribed_circle": "Вписанная окружность",
    "inscribed_polygon": "Окружность в многоугольнике",
    "perimeter": "Периметр",
    "segment_sum": "Сумма длин",
    "segment_difference": "Разность длин",
    "product_equal": "Равенство произведений",
    "ratio_equal": "Равенство отношений",
    "inside_triangle": "Точка внутри треугольника",
    "distinct": "Различные точки",
    "acute_angle": "Острый угол",
    "obtuse_angle": "Тупой угол",
    "sin": "Синус",
    "cos": "Косинус",
    "tg": "Тангенс",
}


def constraint_label(constraint):
    kind, args = constraint["type"], constraint["args"]
    objects = ", ".join("".join(a) if isinstance(a, list) else a for a in args)
    if kind in {
        "distance",
        "angle",
        "right_angle",
        "sin",
        "cos",
        "tg",
        "acute_angle",
        "obtuse_angle",
    }:
        objects = "".join(args)
    value = constraint.get("value")
    if isinstance(value, list):
        value = " : ".join(f"{v:g}" for v in value)
    elif isinstance(value, (int, float)):
        value = f"{value:g}" + ("°" if kind == "angle" else "")
    suffix = f" = {value}" if value is not None else ""
    return f"{LABELS.get(kind, kind)} · {objects}{suffix}"
