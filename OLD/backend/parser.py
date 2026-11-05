from __future__ import annotations

import re
from typing import Any


POINT_RE = r"[A-Z]"
SEGMENT_RE = r"[A-Z]{2}"
POLYGON_RE = r"[A-Z]{3,8}"
CYRILLIC_LABEL_MAP = str.maketrans(
    {
        "А": "A",
        "В": "B",
        "Е": "E",
        "К": "K",
        "М": "M",
        "Н": "H",
        "О": "O",
        "Р": "P",
        "С": "C",
        "Т": "T",
        "Х": "X",
        "У": "Y",
    }
)

SHAPE_WORDS = {
    "треугольник": "triangle",
    "четырехугольник": "quadrilateral",
    "четырёхугольник": "quadrilateral",
    "параллелограмм": "parallelogram",
    "прямоугольник": "rectangle",
    "квадрат": "square",
    "ромб": "rhombus",
    "трапеция": "trapezoid",
}

LENGTH_WORDS = (
    "сторона",
    "отрезок",
    "диагональ",
    "гипотенуза",
    "катет",
    "высота",
    "медиана",
    "биссектриса",
    "основание",
)


def _uniq(items: list[Any]) -> list[Any]:
    result = []
    for item in items:
        if item not in result:
            result.append(item)
    return result


def _segment_key(a: str, b: str) -> list[str]:
    return [a, b]


def _as_float(raw: str) -> float:
    return float(raw.replace(",", "."))


def clean_input_text(text: str) -> str:
    """Normalize PDF artifacts while preserving geometry symbols."""
    text = text.replace("\uf03d", "=")
    text = text.replace("−", "-").replace("–", "-").replace("—", " - ")
    text = re.sub(
        r"\b[АВЕКМНОРСТХУ]{2,8}\b",
        lambda match: match.group(0).translate(CYRILLIC_LABEL_MAP),
        text,
    )
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(?<=\w)-\s+(?=\w)", "", text)
    text = re.sub(r"\b(см|мм|дм|м|градусов?|°)\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bрис\.?\s*\d+\b", "", text, flags=re.IGNORECASE)
    return text.strip()


def parse_geometry_text(text: str) -> dict[str, Any]:
    clean_text = clean_input_text(text)
    lower_text = clean_text.lower()

    points: list[str] = []
    lines: list[list[str]] = []
    constraints: list[dict[str, Any]] = []
    figures: list[dict[str, Any]] = []
    givens: list[dict[str, Any]] = []
    targets: list[dict[str, Any]] = []

    def register_point(point: str) -> None:
        point = point.upper()
        if re.fullmatch(POINT_RE, point) and point not in points:
            points.append(point)

    def register_line(a: str, b: str) -> None:
        a, b = a.upper(), b.upper()
        if a == b:
            return
        register_point(a)
        register_point(b)
        line = _segment_key(a, b)
        reverse = _segment_key(b, a)
        if line not in lines and reverse not in lines:
            lines.append(line)

    def add_constraint(kind: str, args: list[Any], **extra: Any) -> None:
        item = {"type": kind, "args": args, **extra}
        if item not in constraints:
            constraints.append(item)

    def add_given(kind: str, **payload: Any) -> None:
        item = {"type": kind, **payload}
        if item not in givens:
            givens.append(item)

    # Figures: "равносторонний треугольник ABC", "параллелограмм ABCD".
    shape_pattern = re.compile(
        rf"(?P<mods>(?:(?:равносторонн|равнобедренн|равнобок|прямоугольн)\w*\s+)*)"
        rf"(?P<shape>треугольн\w+|четыр[её]хугольн\w+|параллелограмм\w*|"
        rf"прямоугольник\w*|квадрат\w*|ромб\w*|трапец\w+)\s+(?P<name>{POLYGON_RE})",
        flags=re.IGNORECASE,
    )
    for match in shape_pattern.finditer(clean_text):
        shape_word = match.group("shape").lower().replace("ё", "е")
        name = match.group("name").upper()
        mods = match.group("mods").lower().replace("ё", "е")
        shape_type = next(
            (value for key, value in SHAPE_WORDS.items() if shape_word.startswith(key.replace("ё", "е")[:6])),
            shape_word,
        )

        for index, point in enumerate(name):
            register_line(point, name[(index + 1) % len(name)])

        figure = {"type": shape_type, "name": name, "points": list(name)}
        if figure not in figures:
            figures.append(figure)

        if shape_type in {"parallelogram", "rectangle", "square", "rhombus"} and len(name) == 4:
            add_constraint("parallel", [[name[0], name[1]], [name[2], name[3]]])
            add_constraint("parallel", [[name[1], name[2]], [name[3], name[0]]])

        if shape_type in {"parallelogram", "rectangle", "square", "rhombus"} and len(name) == 4:
            add_constraint("equal_segments", [[name[0], name[1]], [name[2], name[3]]])
            add_constraint("equal_segments", [[name[1], name[2]], [name[3], name[0]]])

        if shape_type in {"rectangle", "square"} and len(name) == 4:
            for index, vertex in enumerate(name):
                add_constraint("right_angle", [name[index - 1], vertex, name[(index + 1) % 4]])

        if shape_type in {"square", "rhombus"} and len(name) == 4:
            add_constraint("equal_segments", [[name[0], name[1]], [name[1], name[2]]])
            add_constraint("equal_segments", [[name[1], name[2]], [name[2], name[3]]])
            add_constraint("equal_segments", [[name[2], name[3]], [name[3], name[0]]])

        if shape_type == "trapezoid" and len(name) == 4:
            add_constraint("parallel", [[name[0], name[1]], [name[2], name[3]]])

        if "равносторон" in mods and len(name) == 3:
            add_constraint("equal_segments", [[name[0], name[1]], [name[1], name[2]]])
            add_constraint("equal_segments", [[name[1], name[2]], [name[2], name[0]]])

        if "равнобедрен" in mods and len(name) == 3:
            add_constraint("equal_segments", [[name[0], name[2]], [name[1], name[2]]])

        if "прямоугольн" in mods and len(name) == 3:
            # In many school tasks ABC has the right angle at C when AB is the hypotenuse.
            add_constraint("right_angle", [name[0], name[2], name[1]])

    # Explicit lengths: "AB = 12", "сторона AB равна 12", "гипотенуза AB равна 14".
    length_pattern = re.compile(
        rf"(?:(?:{'|'.join(LENGTH_WORDS)})\s+)?(?P<seg>{SEGMENT_RE})\s*"
        rf"(?:=|равн\w*|составляет)\s*(?P<value>\d+(?:[,.]\d+)?)",
        flags=re.IGNORECASE,
    )
    for match in length_pattern.finditer(clean_text):
        seg = match.group("seg").upper()
        value = _as_float(match.group("value"))
        register_line(seg[0], seg[1])
        add_constraint("distance", [seg[0], seg[1]], value=value)
        add_given("distance", segment=seg, value=value)

    # Equality of segments: "AE = CF", "BM равен DK".
    equality_pattern = re.compile(
        rf"(?P<a>{SEGMENT_RE})\s*(?:=|равн\w*)\s*(?P<b>{SEGMENT_RE})(?!\s*(?:см|мм|дм|м))",
        flags=re.IGNORECASE,
    )
    for match in equality_pattern.finditer(clean_text):
        a, b = match.group("a").upper(), match.group("b").upper()
        if a != b:
            register_line(a[0], a[1])
            register_line(b[0], b[1])
            add_constraint("equal_segments", [[a[0], a[1]], [b[0], b[1]]])
            add_given("equal_segments", segments=[a, b])

    # Ratios: "BM : MC = 3 : 4".
    ratio_pattern = re.compile(
        rf"(?P<a>{SEGMENT_RE})\s*:\s*(?P<b>{SEGMENT_RE})\s*=\s*"
        rf"(?P<x>\d+(?:[,.]\d+)?)\s*:\s*(?P<y>\d+(?:[,.]\d+)?)",
        flags=re.IGNORECASE,
    )
    for match in ratio_pattern.finditer(clean_text):
        a, b = match.group("a").upper(), match.group("b").upper()
        x, y = _as_float(match.group("x")), _as_float(match.group("y"))
        register_line(a[0], a[1])
        register_line(b[0], b[1])
        add_constraint("ratio", [[a[0], a[1]], [b[0], b[1]]], value=[x, y])
        add_given("ratio", segments=[a, b], value=[x, y])

        common = set(a) & set(b)
        if common:
            mid = sorted(common)[0]
            left = a[0] if a[1] == mid else a[1]
            right = b[0] if b[1] == mid else b[1]
            register_line(left, right)
            add_constraint("point_on_segment", [mid, left, right])

    # Point membership: "точка M лежит на стороне BC", "F, принадлежащей отрезку AB".
    belong_patterns = [
        rf"точк[аи]?\s+(?P<p>{POINT_RE}).{{0,40}}?(?:лежит|принадлеж\w+).{{0,25}}?(?P<seg>{SEGMENT_RE})",
        rf"(?P<p>{POINT_RE})\s*,?\s*принадлеж\w+.{{0,25}}?(?P<seg>{SEGMENT_RE})",
        rf"(?P<p>{POINT_RE})\s+лежит\s+(?:на|между).{{0,35}}?(?P<seg>{SEGMENT_RE})",
    ]
    for pattern in belong_patterns:
        for match in re.finditer(pattern, clean_text, flags=re.IGNORECASE):
            if "соответственно" in match.group(0).lower():
                continue
            point, seg = match.group("p").upper(), match.group("seg").upper()
            if point not in seg:
                register_line(seg[0], seg[1])
                add_constraint("point_on_segment", [point, seg[0], seg[1]])

    # "точки D, K и M принадлежат соответственно сторонам AB, BC и AC".
    correspond_pattern = re.compile(
        rf"точк[аи]\s+(?P<points>{POINT_RE}(?:\s*,\s*{POINT_RE})*(?:\s+и\s+{POINT_RE})?)"
        rf".{{0,80}}?соответственно.{{0,30}}?"
        rf"(?P<segments>{SEGMENT_RE}(?:\s*,\s*{SEGMENT_RE})*(?:\s+и\s+{SEGMENT_RE})?)",
        flags=re.IGNORECASE,
    )
    for match in correspond_pattern.finditer(clean_text):
        point_names = re.findall(POINT_RE, match.group("points").upper())
        segment_names = re.findall(SEGMENT_RE, match.group("segments").upper())
        if len(point_names) > 1:
            for point, seg in zip(point_names, segment_names):
                register_line(seg[0], seg[1])
                add_constraint("point_on_segment", [point, seg[0], seg[1]])

    # Parallel notation: "BC || AD".
    for match in re.finditer(rf"(?P<a>{SEGMENT_RE})\s*\|\|\s*(?P<b>{SEGMENT_RE})", clean_text):
        a, b = match.group("a").upper(), match.group("b").upper()
        register_line(a[0], a[1])
        register_line(b[0], b[1])
        add_constraint("parallel", [[a[0], a[1]], [b[0], b[1]]])

    # Perpendiculars: "перпендикуляры FM и FN", "BD перпендикулярна AC".
    explicit_perp = re.compile(
        rf"(?P<a>{SEGMENT_RE})\s*(?:⊥|перпендикуляр\w*)\s*(?P<b>{SEGMENT_RE})",
        flags=re.IGNORECASE,
    )
    for match in explicit_perp.finditer(clean_text):
        a, b = match.group("a").upper(), match.group("b").upper()
        register_line(a[0], a[1])
        register_line(b[0], b[1])
        add_constraint("perpendicular", [[a[0], a[1]], [b[0], b[1]]])

    dropped_pattern = re.compile(
        rf"на\s+(?:катеты|стороны|основания?)\s+(?P<bases>{SEGMENT_RE}(?:\s+и\s+{SEGMENT_RE})?)"
        rf".{{0,60}}?перпендикуляры\s+(?P<heights>{SEGMENT_RE}(?:\s+и\s+{SEGMENT_RE})?)",
        flags=re.IGNORECASE,
    )
    for match in dropped_pattern.finditer(clean_text):
        bases = re.findall(SEGMENT_RE, match.group("bases").upper())
        heights = re.findall(SEGMENT_RE, match.group("heights").upper())
        for height, base in zip(heights, bases):
            register_line(height[0], height[1])
            register_line(base[0], base[1])
            add_constraint("perpendicular", [[height[0], height[1]], [base[0], base[1]]])
            add_constraint("point_on_segment", [height[1], base[0], base[1]])

    # Intersections: "диагонали AC и BD пересекаются в точке M".
    intersection_pattern = re.compile(
        rf"(?P<a>{SEGMENT_RE})\s+и\s+(?P<b>{SEGMENT_RE})\s+пересека\w+"
        rf".{{0,20}}?точк[еия]\s+(?P<p>{POINT_RE})",
        flags=re.IGNORECASE,
    )
    for match in intersection_pattern.finditer(clean_text):
        a, b, point = match.group("a").upper(), match.group("b").upper(), match.group("p").upper()
        register_line(a[0], a[1])
        register_line(b[0], b[1])
        add_constraint("point_on_segment", [point, a[0], a[1]])
        add_constraint("point_on_segment", [point, b[0], b[1]])

    target_pattern = re.compile(
        rf"(?:найдите|докажите|вычислите).{{0,80}}?(?P<kind>периметр|площадь|сторону|отрезок|радиус|высоту|основания?)"
        rf"(?:.{{0,20}}?(?P<name>{POLYGON_RE}))?",
        flags=re.IGNORECASE,
    )
    for match in target_pattern.finditer(clean_text):
        targets.append(
            {
                "type": match.group("kind").lower(),
                "name": (match.group("name") or "").upper() or None,
            }
        )

    # Last pass: register remaining named uppercase Latin/Cyrillic geometry tokens.
    for token in re.findall(POLYGON_RE, clean_text):
        if token.isupper() and len(token) <= 4:
            for point in token:
                register_point(point)

    return {
        "source_text": text,
        "clean_text": clean_text,
        "points": sorted(points),
        "lines": _uniq(lines),
        "constraints": constraints,
        "figures": figures,
        "givens": givens,
        "targets": _uniq(targets),
    }
