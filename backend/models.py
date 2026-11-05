from __future__ import annotations

import math
import re
from enum import Enum

from pydantic import BaseModel, Field, model_validator

POINT_NAME_RE = r"[A-Z](?:[0-9]{1,3})?"


class ConstraintType(str, Enum):
    DISTANCE = "distance"
    EQUAL_SEGMENTS = "equal_segments"
    RATIO = "ratio"
    PERPENDICULAR = "perpendicular"
    PARALLEL = "parallel"
    RIGHT_ANGLE = "right_angle"
    ANGLE = "angle"
    EQUAL_ANGLES = "equal_angles"
    POINT_ON_SEGMENT = "point_on_segment"
    POINT_ON_LINE = "point_on_line"
    POINT_BETWEEN = "point_between"
    MIDPOINT = "midpoint"
    PROJECTION = "projection"
    BISECTOR = "bisector"
    COLLINEAR = "collinear"
    TANGENT = "tangent"
    SIN = "sin"
    COS = "cos"
    TG = "tg"
    CIRCLE_CENTER = "circle_center"
    CIRCLE_RADIUS = "circle_radius"
    POINT_ON_CIRCLE = "point_on_circle"
    CIRCUMSCRIBED_CIRCLE = "circumscribed_circle"
    INSCRIBED_CIRCLE = "inscribed_circle"
    PERIMETER = "perimeter"
    SEGMENT_SUM = "segment_sum"
    SEGMENT_DIFFERENCE = "segment_difference"
    EXTERNAL_BISECTOR = "external_bisector"
    OBTUSE_ANGLE = "obtuse_angle"
    ACUTE_ANGLE = "acute_angle"
    PRODUCT_EQUAL = "product_equal"
    RATIO_EQUAL = "ratio_equal"
    INSIDE_TRIANGLE = "inside_triangle"
    EXTERNAL_TANGENCY = "external_tangency"
    DISTINCT = "distinct"
    INSCRIBED_POLYGON = "inscribed_polygon"


class FigureType(str, Enum):
    TRIANGLE = "triangle"
    RIGHT_TRIANGLE = "right_triangle"
    ISOSCELES_TRIANGLE = "isosceles_triangle"
    EQUILATERAL_TRIANGLE = "equilateral_triangle"
    QUADRILATERAL = "quadrilateral"
    PARALLELOGRAM = "parallelogram"
    RECTANGLE = "rectangle"
    SQUARE = "square"
    RHOMBUS = "rhombus"
    TRAPEZOID = "trapezoid"
    CIRCLE = "circle"
    SEGMENT = "segment"
    REGULAR_POLYGON = "regular_polygon"
    LINE = "line"


class Constraint(BaseModel):
    type: ConstraintType
    args: list[str | list[str]] = Field(
        description="Point names or segment pairs, e.g. ['A', 'B'] or [['A', 'B'], ['C', 'D']]"
    )
    value: float | list[float] | None = Field(
        default=None, description="Numeric value, e.g. length, angle in degrees, or ratio [x, y]"
    )

    @model_validator(mode="after")
    def validate_shape(self):
        def names(items):
            return isinstance(items, list) and all(
                isinstance(p, str) and re.fullmatch(POINT_NAME_RE, p) for p in items
            )

        arities = {
            "distance": 2,
            "angle": 3,
            "right_angle": 3,
            "midpoint": 3,
            "projection": 4,
            "point_on_segment": 3,
            "point_on_line": 3,
            "point_between": 3,
            "bisector": 4,
            "sin": 3,
            "cos": 3,
            "tg": 3,
            "point_on_circle": 2,
            "collinear": 3,
            "circle_radius": 1,
            "inscribed_circle": 4,
            "external_bisector": 4,
            "obtuse_angle": 3,
            "acute_angle": 3,
            "tangent": 3,
            "inside_triangle": 4,
            "external_tangency": 3,
            "distinct": 2,
        }
        kind = self.type.value
        if kind in arities and (len(self.args) != arities[kind] or not names(self.args)):
            raise ValueError(f"Некорректные аргументы {kind}")
        if kind in {"product_equal", "ratio_equal"}:
            if len(self.args) != 4 or not all(
                names(s) and len(s) == 2 and len(set(s)) == 2 for s in self.args
            ):
                raise ValueError("Требуются четыре невырожденных отрезка")
        if kind in {
            "distance",
            "angle",
            "right_angle",
            "sin",
            "cos",
            "tg",
            "distinct",
            "tangent",
            "inside_triangle",
            "external_tangency",
            "acute_angle",
            "obtuse_angle",
        } and len(set(self.args)) != len(self.args):
            raise ValueError(f"{kind}: точки должны различаться")
        if kind == "inscribed_polygon" and (
            not names(self.args) or len(self.args) < 4 or len(set(self.args)) != len(self.args)
        ):
            raise ValueError("Некорректные вершины вписанного в многоугольник круга")
        if kind in {"circumscribed_circle", "perimeter"} and (
            not names(self.args) or len(self.args) < (4 if kind == "circumscribed_circle" else 3)
        ):
            raise ValueError(f"Некорректные вершины {kind}")
        if kind in {"sin", "cos", "tg"}:
            if not isinstance(self.value, (int, float)):
                raise ValueError("Требуется числовое значение тригонометрической функции")
            if kind == "sin" and not 0 < self.value <= 1:
                raise ValueError("Синус внутреннего угла должен быть в (0, 1]")
            if kind == "cos" and not -1 < self.value < 1:
                raise ValueError("Косинус внутреннего угла должен быть в (-1, 1)")
        if kind in (
            "parallel",
            "perpendicular",
            "equal_segments",
            "ratio",
            "equal_angles",
            "segment_sum",
            "segment_difference",
        ):
            size = 3 if kind == "equal_angles" else 2
            if len(self.args) != 2 or not all(
                names(s) and len(s) == size and len(set(s)) == size for s in self.args
            ):
                raise ValueError(f"Некорректные пары объектов {kind}")
        if self.value is not None:
            values = self.value if isinstance(self.value, list) else [self.value]
            if not all(math.isfinite(v) for v in values):
                raise ValueError("Числовые параметры должны быть конечными")
        if kind in ("distance", "angle", "perimeter", "circle_radius"):
            if not isinstance(self.value, (float, int)) or self.value <= 0:
                raise ValueError(f"{kind}: требуется положительное число")
        if kind == "angle" and self.value >= 180:
            raise ValueError("Угол должен быть меньше 180 градусов")
        if kind in ("segment_sum", "segment_difference") and (
            not isinstance(self.value, (int, float)) or self.value <= 0
        ):
            raise ValueError("Требуется положительное значение суммы/разности отрезков")
        if kind == "ratio" and (
            not isinstance(self.value, list) or len(self.value) != 2 or min(self.value) <= 0
        ):
            raise ValueError("Отношение должно содержать два положительных числа")
        return self


class Figure(BaseModel):
    type: FigureType
    name: str = Field(description="Name like 'ABC', 'ABCD', 'omega'")
    points: list[str] = Field(default_factory=list, description="Ordered point names")
    center: str | None = Field(default=None, description="Center point name if circle")
    radius: float | None = Field(default=None, description="Radius if known")


class Circle(BaseModel):
    name: str = Field(default="omega")
    center: str = Field(description="Point name of the center")
    radius: float | None = Field(default=None, description="Numerical radius if specified")
    passing_through: list[str] = Field(
        default_factory=list, description="Points lying on the circle"
    )


class GeometrySchema(BaseModel):
    """
    Formal representation of a planimetry problem parsed from natural language or LLM.
    Strictly validated by Pydantic.
    """

    points: list[str] = Field(
        default_factory=list, description="Unique names of points (single uppercase letters)"
    )
    lines: list[list[str]] = Field(
        default_factory=list, description="Segments to draw, each is [Point1, Point2]"
    )
    figures: list[Figure] = Field(default_factory=list, description="Identified geometric figures")
    circles: list[Circle] = Field(default_factory=list, description="Circles in the problem")
    constraints: list[Constraint] = Field(default_factory=list, description="Geometric constraints")
    givens: list[dict] = Field(default_factory=list, description="Raw givens/facts")
    targets: list[dict] = Field(default_factory=list, description="Quantities to find or prove")

    @model_validator(mode="after")
    def validate_references(self):
        if len(self.points) > 128 or len(set(self.points)) != len(self.points):
            raise ValueError("Имена точек должны быть уникальны (не более 128)")
        if not all(re.fullmatch(POINT_NAME_RE, p) for p in self.points):
            raise ValueError(
                "Имена точек — заглавная латинская буква с необязательным индексом до 999"
            )
        known = set(self.points)
        for line in self.lines:
            if len(line) != 2 or len(set(line)) != 2 or not set(line) <= known:
                raise ValueError("Некорректный отрезок или неизвестная точка")
        for figure in self.figures:
            if not set(figure.points) <= known or len(set(figure.points)) != len(figure.points):
                raise ValueError("Некорректные вершины фигуры")
        for circle in self.circles:
            if circle.center not in known or not set(circle.passing_through) <= known:
                raise ValueError("Неизвестная точка окружности")
            if circle.radius is not None and (
                not math.isfinite(circle.radius) or circle.radius <= 0
            ):
                raise ValueError("Радиус должен быть положительным конечным числом")

        def refs(args):
            for arg in args:
                if isinstance(arg, list):
                    yield from refs(arg)
                elif isinstance(arg, str):
                    yield arg

        for constraint in self.constraints:
            if not set(refs(constraint.args)) <= known:
                raise ValueError("Ограничение ссылается на неизвестную точку")
        if len(self.constraints) > 512:
            raise ValueError("Слишком много ограничений")
        return self
