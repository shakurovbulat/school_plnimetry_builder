from __future__ import annotations

import re
from typing import Any

from backend.constructions import enrich_schema
from backend.models import ConstraintType

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
    from backend.text_normalization import given_text

    text = given_text(text)
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
    from backend.advanced_constructions import parse_advanced

    advanced = parse_advanced(text)
    if advanced is not None:
        return advanced
    clean_text = clean_input_text(text)
    lower_text = clean_text.lower()

    points: list[str] = []
    lines: list[list[str]] = []
    constraints: list[dict[str, Any]] = []
    figures: list[dict[str, Any]] = []
    circles: list[dict[str, Any]] = []
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
        def register_args(items):
            for item in items:
                if isinstance(item, list):
                    register_args(item)
                elif isinstance(item, str) and re.fullmatch(POINT_RE, item):
                    register_point(item)

        register_args(args)
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
            (
                value
                for key, value in SHAPE_WORDS.items()
                if shape_word.startswith(key.replace("ё", "е")[:6])
            ),
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
            add_constraint("angle", [name[1], name[0], name[2]], value=60.0)
            add_constraint("angle", [name[0], name[1], name[2]], value=60.0)

        if "равнобедрен" in mods and len(name) == 3:
            add_constraint("equal_segments", [[name[0], name[2]], [name[1], name[2]]])

        if "прямоугольн" in mods and len(name) == 3:
            # In general right triangle ABC, check which hypotenuse is specified later or default to C
            add_constraint("right_angle", [name[0], name[2], name[1]])

    # Hypotenuse explicitly stated: "гипотенуза AB" -> right angle at C
    hypot_pattern = re.compile(rf"гипотенуз\w*\s+(?P<h>{SEGMENT_RE})", flags=re.IGNORECASE)
    for match in hypot_pattern.finditer(clean_text):
        h = match.group("h").upper()
        # Find third vertex of the triangle containing h
        for fig in figures:
            if fig.get("type") == "triangle" and h[0] in fig["points"] and h[1] in fig["points"]:
                other = [p for p in fig["points"] if p not in h][0]
                # Replace or enforce right angle at other
                add_constraint("right_angle", [h[0], other, h[1]])

    # Perimeter: "Периметр ромба равен 48", "Периметр треугольника ABC равен 36"
    perim_pattern = re.compile(
        rf"периметр\s+(?:(?P<fig_word>ромба|треугольника|многоугольника|четырехугольника|четырёхугольника)\s*)?(?P<name>{POLYGON_RE})?\s*(?:=|равен|составляет)\s*(?P<val>\d+(?:[,.]\d+)?)",
        flags=re.IGNORECASE,
    )
    for match in perim_pattern.finditer(clean_text):
        fig_w = (match.group("fig_word") or "").lower()
        name = (match.group("name") or "").upper()
        val = _as_float(match.group("val"))

        target_fig = None
        for fig in figures:
            if name and (fig.get("name") == name or name in fig.get("name", "")):
                target_fig = fig
                break
            elif fig_w and ("ромб" in fig_w and fig.get("type") == "rhombus"):
                target_fig = fig
                break
            elif fig_w and ("треугольн" in fig_w and "triangle" in fig.get("type", "")):
                target_fig = fig
                break

        if target_fig:
            pts = target_fig.get("points", [])
            add_constraint("perimeter", pts, value=val)

    # Trig functions: "sin угла A = 0.6", "cos ∠B = 0.8", "tg угла BAC равен 1.5"
    trig_pattern = re.compile(
        r"(?P<fn>sin|cos|tg|tan)\s*(?:угла|∠)?\s*(?P<ang>[A-Z]{1,3})\s*(?:=|равен|составляет)\s*(?P<val>\d+(?:[,.]\d+)?)",
        flags=re.IGNORECASE,
    )
    for match in trig_pattern.finditer(clean_text):
        fn = match.group("fn").lower().replace("tan", "tg")
        ang = match.group("ang").upper()
        val = _as_float(match.group("val"))
        if len(ang) == 1:
            # Look for triangle containing this vertex
            for fig in figures:
                if fig.get("type") in ("triangle", "right_triangle") and ang in fig.get(
                    "points", []
                ):
                    pts = fig.get("points", [])
                    others = [p for p in pts if p != ang]
                    if len(others) == 2:
                        ang = f"{others[0]}{ang}{others[1]}"
                        break
        if len(ang) == 3:
            p1, vertex, p2 = ang[0], ang[1], ang[2]
            register_line(p1, vertex)
            register_line(vertex, p2)
            ctype = (
                ConstraintType.SIN
                if fn == "sin"
                else (ConstraintType.COS if fn == "cos" else ConstraintType.TG)
            )
            add_constraint(ctype.value, [p1, vertex, p2], value=val)

    # Inscribed and Circumscribed circles:
    # "вписанная окружность треугольника ABC", "описанная около треугольника ABC окружность"
    if re.search(r"вписан\w*\s+окружност\w*", clean_text, flags=re.IGNORECASE):
        for fig in figures:
            if fig.get("type") in ("triangle", "right_triangle"):
                pts = fig.get("points", [])
                register_point("I")
                circles.append({"name": "inscribed", "center": "I"})
                add_constraint("inscribed_circle", ["I"] + pts)
                break

    if re.search(r"описан\w*.*окружност\w*", clean_text, flags=re.IGNORECASE):
        for fig in figures:
            if fig.get("type") in ("triangle", "right_triangle", "rectangle", "square"):
                pts = fig.get("points", [])
                register_point("O")
                circles.append({"name": "circumscribed", "center": "O"})
                add_constraint("circumscribed_circle", ["O"] + pts)
                break

    # Circle with center and radius: "окружность с центром в точке O и радиусом 5"
    circ_center_rad = re.compile(
        rf"окружност\w*.{{0,30}}?центр\w*\s+(?:в\s+точке\s+)?(?P<center>{POINT_RE}).{{0,40}}?радиус\w*\s*(?:=|равен|составляет)?\s*(?P<r>\d+(?:[,.]\d+)?)",
        flags=re.IGNORECASE,
    )
    for match in circ_center_rad.finditer(clean_text):
        center_pt = match.group("center").upper()
        r_val = _as_float(match.group("r"))
        register_point(center_pt)
        exists = any(c.get("center") == center_pt for c in circles)
        if not exists:
            circles.append({"name": "omega", "center": center_pt, "radius": r_val})
        else:
            for c in circles:
                if c.get("center") == center_pt:
                    c["radius"] = r_val

    # Point lying on circle: "точка M лежит на окружности с центром O"
    pt_on_circ = re.compile(
        rf"точк[аи]?\s+(?P<pt>{POINT_RE}).{{0,30}}?лежит\s+на\s+окружност\w*.{{0,30}}?центр\w*\s+(?:в\s+точке\s+)?(?P<center>{POINT_RE})",
        flags=re.IGNORECASE,
    )
    for match in pt_on_circ.finditer(clean_text):
        pt = match.group("pt").upper()
        cntr = match.group("center").upper()
        register_point(pt)
        register_point(cntr)
        add_constraint("point_on_circle", [pt, cntr])
    length_pattern = re.compile(
        rf"(?<![A-Za-z])(?:(?:{'|'.join(LENGTH_WORDS)})\s+)?(?P<seg>{SEGMENT_RE})\s*"
        rf"(?:=|равен|равна|равно|равны|составляет)\s*(?P<value>\d+(?:[,.]\d+)?)",
        flags=re.IGNORECASE,
    )
    for match in length_pattern.finditer(clean_text):
        if re.match(r"\s*:", clean_text[match.end() :]):
            continue  # The first number in X:Y is not a segment length.
        seg = match.group("seg").upper()
        value = _as_float(match.group("value"))
        register_line(seg[0], seg[1])
        add_constraint("distance", [seg[0], seg[1]], value=value)
        add_given("distance", segment=seg, value=value)

    # Equal angles: "∠BAM = ∠DCK", "угол A равен углу C"
    eq_angle_pattern = re.compile(
        rf"(?:∠|угол\s*)(?P<a>{POLYGON_RE})\s*(?:=|равен|равна)\s*(?:∠|угол\s*)?(?P<b>{POLYGON_RE})",
        flags=re.IGNORECASE,
    )
    for match in eq_angle_pattern.finditer(clean_text):
        a, b = match.group("a").upper(), match.group("b").upper()
        if len(a) == 3 and len(b) == 3:
            add_constraint("equal_angles", [[a[0], a[1], a[2]], [b[0], b[1], b[2]]])
            register_line(a[0], a[1])
            register_line(a[1], a[2])
            register_line(b[0], b[1])
            register_line(b[1], b[2])

    # Diagonals mentioned: "на диагонали BD", "диагональ AC"
    diag_pattern = re.compile(rf"диагонал\w*\s+(?P<d>{SEGMENT_RE})", flags=re.IGNORECASE)
    for match in diag_pattern.finditer(clean_text):
        d = match.group("d").upper()
        register_line(d[0], d[1])

    # Points on diagonal / segment: "на диагонали BD ... отметили точки M и K"
    on_diag_pattern = re.compile(
        rf"(?:на\s+диагонали|на\s+стороне|на\s+отрезке)\s+(?P<seg>{SEGMENT_RE}).{{0,40}}?отметили\s+точки\s+(?P<pts>{POINT_RE}(?:\s*и\s*{POINT_RE})*)",
        flags=re.IGNORECASE,
    )
    for match in on_diag_pattern.finditer(clean_text):
        seg = match.group("seg").upper()
        pts = re.findall(POINT_RE, match.group("pts").upper())
        register_line(seg[0], seg[1])
        for p in pts:
            register_point(p)
            add_constraint("point_on_segment", [p, seg[0], seg[1]])

    # Point between two points: "точка M лежит между точками B и K"
    between_pattern = re.compile(
        rf"точк[аи]?\s+(?P<p>{POINT_RE})\s+лежит\s+между\s+(?:точками\s+)?(?P<p1>{POINT_RE})\s+и\s+(?P<p2>{POINT_RE})",
        flags=re.IGNORECASE,
    )
    for match in between_pattern.finditer(clean_text):
        p = match.group("p").upper()
        p1 = match.group("p1").upper()
        p2 = match.group("p2").upper()
        add_constraint("point_between", [p, p1, p2])

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
                if "середины" in clean_text[max(0, match.start() - 30) : match.end()]:
                    continue
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

    # Bisector: "биссектриса угла D параллелограмма ABCD пересекает сторону BC в точке M"
    bisector_pattern = re.compile(
        rf"биссектрис\w*\s+угла\s+(?P<v>{POINT_RE}).{{0,50}}?пересекает\s+(?:сторону\s+)?(?P<seg>{SEGMENT_RE})\s+в\s+точке\s+(?P<m>{POINT_RE})",
        flags=re.IGNORECASE,
    )
    for match in bisector_pattern.finditer(clean_text):
        v = match.group("v").upper()
        seg = match.group("seg").upper()
        m = match.group("m").upper()
        register_point(v)
        register_point(m)
        register_line(v, m)
        register_line(seg[0], seg[1])
        add_constraint("point_on_segment", [m, seg[0], seg[1]])
        add_constraint("bisector", [v, m, seg[0], seg[1]])

    # Perpendicular dropped from a point:
    # "Из точки F, принадлежащей отрезку AB, на катеты AC и BC соответственно опущены перпендикуляры FM и FN."
    perp_from_point = re.compile(
        rf"[Ии]з\s+точки\s+(?P<from_pt>{POINT_RE}).{{0,80}}?на\s+(?:катеты|стороны)\s+(?P<base1>{SEGMENT_RE})\s+и\s+(?P<base2>{SEGMENT_RE})\s+соответственно\s+опущены\s+перпендикуляры\s+(?P<perp1>{SEGMENT_RE})\s+и\s+(?P<perp2>{SEGMENT_RE})",
        flags=re.IGNORECASE,
    )
    for match in perp_from_point.finditer(clean_text):
        from_pt = match.group("from_pt").upper()
        b1, b2 = match.group("base1").upper(), match.group("base2").upper()
        p1, p2 = match.group("perp1").upper(), match.group("perp2").upper()

        m_pt = p1[1] if p1[0] == from_pt else p1[0]
        n_pt = p2[1] if p2[0] == from_pt else p2[0]

        register_line(from_pt, m_pt)
        register_line(from_pt, n_pt)
        register_line(b1[0], b1[1])
        register_line(b2[0], b2[1])

        add_constraint("projection", [m_pt, from_pt, b1[0], b1[1]])
        add_constraint("projection", [n_pt, from_pt, b2[0], b2[1]])
        add_constraint("perpendicular", [[from_pt, m_pt], [b1[0], b1[1]]])
        add_constraint("perpendicular", [[from_pt, n_pt], [b2[0], b2[1]]])
        add_constraint("point_on_segment", [m_pt, b1[0], b1[1]])
        add_constraint("point_on_segment", [n_pt, b2[0], b2[1]])

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

    # Circle patterns: "окружность с центром в точке O", "окружность радиуса R", "описанная окружность"
    # Preserve circle properties extracted above.
    circle_pattern = re.compile(
        rf"(?:окружност\w*|круг\w*).{{0,30}}?центр\w*\s+(?:в\s+точке\s+)?(?P<center>{POINT_RE})",
        flags=re.IGNORECASE,
    )
    for match in circle_pattern.finditer(clean_text):
        center_pt = match.group("center").upper()
        register_point(center_pt)
        if not any(c["center"] == center_pt for c in circles):
            circles.append({"name": "omega", "center": center_pt})

    # Radius pattern: "радиус равен 5", "радиусом 6"
    radius_pattern = re.compile(
        r"радиус\w*\s*(?:=|равен|равна|составляет)?\s*(?P<r>\d+(?:[,.]\d+)?)", flags=re.IGNORECASE
    )
    for match in radius_pattern.finditer(clean_text):
        r_val = _as_float(match.group("r"))
        if circles:
            circles[-1]["radius"] = r_val

    # Explicit angles: "угол ABC равен 60", "∠BAC = 45"
    angle_pattern = re.compile(
        r"(?:угол|∠)\s*(?P<ang>[A-Z]{1,3})\s*(?:=|равен|составляет)\s*(?P<deg>\d+(?:[,.]\d+)?)",
        flags=re.IGNORECASE,
    )
    for match in angle_pattern.finditer(clean_text):
        ang = match.group("ang").upper()
        deg = _as_float(match.group("deg"))
        if len(ang) == 1:
            for fig in figures:
                pts = fig["points"]
                if ang in pts:
                    i = pts.index(ang)
                    ang = pts[i - 1] + ang + pts[(i + 1) % len(pts)]
                    break
        if len(ang) == 3:
            p1, vertex, p2 = ang[0], ang[1], ang[2]
            register_line(p1, vertex)
            register_line(vertex, p2)
            add_constraint("angle", [p1, vertex, p2], value=deg)
            add_given("angle", angle=ang, value=deg)

    # Medians, bisectors, heights
    # "медиана BM треугольника ABC" or "проведена медиана BM ... к стороне AC"
    median_pattern = re.compile(
        rf"медиан\w*\s+(?P<m>{SEGMENT_RE})(?:.{{0,30}}?треугольник\w*\s+(?P<tri>{POLYGON_RE}))?(?:.{{0,30}}?к\s+стороне\s+(?P<side>{SEGMENT_RE}))?",
        flags=re.IGNORECASE,
    )
    for match in median_pattern.finditer(clean_text):
        seg = match.group("m").upper()
        v, m = seg[0], seg[1]
        tri = (match.group("tri") or "").upper()
        if not tri:
            tri = next(
                (
                    "".join(f["points"])
                    for f in figures
                    if len(f["points"]) == 3 and v in f["points"]
                ),
                "",
            )
        side = (match.group("side") or "").upper()
        register_line(v, m)
        register_point(m)
        if side and len(side) == 2:
            register_line(side[0], side[1])
            add_constraint("midpoint", [m, side[0], side[1]])
            add_constraint("point_on_segment", [m, side[0], side[1]])
        elif len(tri) == 3 and v in tri:
            others = [p for p in tri if p != v]
            if len(others) == 2:
                register_line(others[0], others[1])
                add_constraint("midpoint", [m, others[0], others[1]])
                add_constraint("point_on_segment", [m, others[0], others[1]])

    # "высота BH треугольника ABC" or "проведена высота BH ... к стороне AC"
    height_pattern = re.compile(
        rf"высот\w*\s+(?P<h>{SEGMENT_RE})(?:.{{0,30}}?треугольник\w*\s+(?P<tri>{POLYGON_RE}))?(?:.{{0,30}}?к\s+стороне\s+(?P<side>{SEGMENT_RE}))?",
        flags=re.IGNORECASE,
    )
    for match in height_pattern.finditer(clean_text):
        seg = match.group("h").upper()
        v, h = seg[0], seg[1]
        tri = (match.group("tri") or "").upper()
        if not tri:
            tri = next(
                (
                    "".join(f["points"])
                    for f in figures
                    if len(f["points"]) == 3 and v in f["points"]
                ),
                "",
            )
        side = (match.group("side") or "").upper()
        register_line(v, h)
        register_point(h)
        if side and len(side) == 2:
            register_line(side[0], side[1])
            add_constraint("projection", [h, v, side[0], side[1]])
            add_constraint("perpendicular", [[v, h], [side[0], side[1]]])
            add_constraint("point_on_segment", [h, side[0], side[1]])
        elif len(tri) == 3 and v in tri:
            others = [p for p in tri if p != v]
            if len(others) == 2:
                register_line(others[0], others[1])
                add_constraint("projection", [h, v, others[0], others[1]])
                add_constraint("perpendicular", [[v, h], [others[0], others[1]]])
                add_constraint("point_on_segment", [h, others[0], others[1]])

    # Explicit plural constructions and circle memberships.
    for match in re.finditer(r"медианы\s+([A-Z]{2}),\s*([A-Z]{2})\s+и\s+([A-Z]{2})", clean_text):
        for seg in match.groups():
            for fig in figures:
                if len(fig["points"]) == 3 and seg[0] in fig["points"]:
                    side = [p for p in fig["points"] if p != seg[0]]
                    register_line(*seg)
                    add_constraint("midpoint", [seg[1]] + side)
    for match in re.finditer(
        r"точки\s+([A-Z])\s+и\s+([A-Z])\s*[-—]?\s*середины\s+сторон\s+([A-Z]{2})\s+и\s+([A-Z]{2})",
        clean_text,
        re.I,
    ):
        m, n, ab, bc = (g.upper() for g in match.groups())
        constraints[:] = [
            c
            for c in constraints
            if not (c["type"] == "point_on_segment" and c["args"][0] in (m, n))
        ]
        add_constraint("midpoint", [m, *ab])
        add_constraint("midpoint", [n, *bc])
        register_line(m, n)
    if len(circles) == 1:
        center = circles[0]["center"]
        for match in re.finditer(
            r"Точки\s+([A-Z])\s+и\s+([A-Z])\s+лежат\s+на\s+окружности", clean_text
        ):
            for point in match.groups():
                add_constraint("point_on_circle", [point, center])
                circles[0].setdefault("passing_through", []).append(point)
        for match in re.finditer(r"касательн\w*\s+([A-Z]{2})", clean_text, re.I):
            seg = match.group(1).upper()
            register_line(*seg)
            register_line(center, seg[1])
            add_constraint("point_on_circle", [seg[1], center])
            add_constraint("perpendicular", [[center, seg[1]], list(seg)])
    for fig in figures:
        pts = fig["points"]
        if fig["type"] == "square":
            side = re.search(r"со\s+стороной\s+(\d+(?:[,.]\d+)?)", clean_text, re.I)
            if side:
                add_constraint("distance", pts[:2], value=_as_float(side.group(1)))
        if len(pts) == 3 and "равнобедрен" in lower_text:
            base = re.search(r"основани\w*\s+([A-Z]{2})", clean_text, re.I)
            if base:
                left, right = base.group(1).upper()
                vertex = next(p for p in pts if p not in (left, right))
                constraints[:] = [
                    c
                    for c in constraints
                    if not (c["type"] == "equal_segments" and set(sum(c["args"], [])) == set(pts))
                ]
                add_constraint("equal_segments", [[vertex, left], [vertex, right]])
        if fig["type"] == "trapezoid":
            bases = re.search(
                r"основани\w*\s+([A-Z]{2}).{0,20}?\sи\s+([A-Z]{2})\s+равны\s+(\d+)\s+и\s+(\d+)",
                clean_text,
                re.I,
            )
            if bases:
                a, b, x, y = bases.groups()
                constraints[:] = [
                    c
                    for c in constraints
                    if not (
                        c["type"] == "distance"
                        and set(c["args"]) in (set(a.upper()), set(b.upper()))
                    )
                ]
                add_constraint("distance", list(a.upper()), value=float(x))
                add_constraint("distance", list(b.upper()), value=float(y))
            explicit = re.findall(r"основани\w*\s+([A-Z]{2})", clean_text, re.I)
            if bases or explicit:
                a = bases.group(1).upper() if bases else explicit[0].upper()
                opposite = "".join(p for p in pts if p not in a)
                constraints[:] = [c for c in constraints if c["type"] != "parallel"]
                add_constraint("parallel", [list(a), list(opposite)])
            if "равнобок" in lower_text:
                add_constraint("equal_segments", [[pts[0], pts[1]], [pts[2], pts[3]]])

    # Last pass: register remaining named uppercase Latin/Cyrillic geometry tokens.
    for token in re.findall(POLYGON_RE, clean_text):
        if token.isupper() and len(token) <= 4:
            for point in token:
                register_point(point)

    return enrich_schema(
        {
            "source_text": text,
            "clean_text": clean_text,
            "points": sorted(points),
            "lines": _uniq(lines),
            "constraints": constraints,
            "figures": figures,
            "circles": circles,
            "givens": givens,
            "targets": _uniq(targets),
        },
        clean_text,
    )
