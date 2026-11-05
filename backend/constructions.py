"""Deterministic constructions; no problem IDs or precomputed coordinates.

Adds relations justified by explicit wording. Proof conclusions are removed by
text_normalization before this module sees the condition.
"""

import math
import re

NUM = r"\d+(?:[.,]\d+)?"


def enrich_schema(raw, text):
    p, lines, figures, circles, cs = (
        raw[k] for k in ("points", "lines", "figures", "circles", "constraints")
    )
    low = text.lower()

    def point(n):
        if n not in p:
            p.append(n)

    def line(a, b):
        point(a)
        point(b)
        if a != b and [a, b] not in lines and [b, a] not in lines:
            lines.append([a, b])

    def add(t, args, value=None):
        def refs(xs):
            for x in xs:
                if isinstance(x, list):
                    refs(x)
                else:
                    point(x)

        refs(args)
        c = dict(type=t, args=args)
        if value is not None:
            c["value"] = value
        if c not in cs:
            cs.append(c)

    def figure(t, name):
        for a, b in zip(name, name[1:] + name[:1]):
            line(a, b)
        item = dict(type=t, name=name, points=list(name))
        if not any(f["points"] == list(name) and f["type"] == t for f in figures):
            figures.append(item)

    def circle(center="O", vertices=None, radius=None):
        point(center)
        c = next((c for c in circles if c["center"] == center), None)
        if c is None:
            c = dict(name="omega", center=center, passing_through=[])
            circles.append(c)
        if radius is not None:
            c["radius"] = radius
        for v in vertices or []:
            point(v)
            if v not in c.setdefault("passing_through", []):
                c["passing_through"].append(v)
        return c

    val = lambda m, g=1: float(m.group(g).replace(",", "."))

    # Do not read the last two letters of a named angle as a segment.
    numeric_spans = []
    for m in re.finditer(
        r"(?:угол|∠|sin|cos|tg)\s*(?:угла\s*)?[A-Z]{1,3}\s*(?:=|равен|составляет)\s*(" + NUM + ")",
        text,
        re.I,
    ):
        numeric_spans.append((m.start(), m.end()))
    safe_distances = []
    for m in re.finditer(
        r"(?<![A-Za-z])([A-Z]{2})\s*(?:=|равен|равна|равно|составляет)\s*(" + NUM + ")", text
    ):
        if not any(a <= m.start() < b for a, b in numeric_spans) and not re.match(
            r"\s*:", text[m.end() :]
        ):
            safe_distances.append((m[1], val(m, 2)))
    # Legacy extraction may have matched AD in BAD or CB in ACB.
    suspect_segments = set()
    for m in re.finditer(
        r"(?:угол|∠|sin|cos|tg)\s*(?:угла\s*)?([A-Z]{3})\s*(?:=|равен|составляет)", text, re.I
    ):
        suspect_segments.add(m[1].upper()[-2:])
    cs[:] = [
        c
        for c in cs
        if c["type"] != "distance"
        or "".join(c["args"]) not in suspect_segments
        or any(
            set(c["args"]) == set(seg) and math.isclose(c["value"], v) for seg, v in safe_distances
        )
    ]
    for seg, v in safe_distances:
        line(*seg)
        add("distance", list(seg), v)

    # Anonymous elementary figures have a documented default naming convention.
    if not figures:
        if re.search(r"правильн\w*\s+треугольник", low):
            figure("equilateral_triangle", "ABC")
        elif re.search(r"ромб", low):
            figure("rhombus", "ABCD")
        elif re.search(r"трапец", low):
            figure("trapezoid", "ABCD")
    for f in list(figures):
        pts = f["points"]
        if len(pts) == 3 and re.search(r"правильн\w*\s+треугольник", low):
            f["type"] = "equilateral_triangle"
        if f["type"] == "square":
            m = re.search(r"со\s+стороной\s*(" + NUM + ")", text, re.I)
            if m:
                add("distance", pts[:2], val(m))
        if f["type"] == "rhombus":
            m = re.search(r"диагонали\s+равны\s*(" + NUM + ")\s*и\s*(" + NUM + ")", text, re.I)
            if m:
                for seg, v in [(pts[::2], val(m)), (pts[1::2], val(m, 2))]:
                    line(*seg)
                    add("distance", seg, v)
        if f["type"] == "equilateral_triangle":
            a, b, c = pts
            m = re.search(r"высота\s+(?:которого\s+)?равна\s*(" + NUM + ")", text, re.I)
            if m:
                line(c, "H")
                add("projection", ["H", c, a, b])
                add("distance", [c, "H"], val(m))
        if f["type"] == "trapezoid":
            a, b, c, d = pts
            # Default bases AB and CD; named bases in legacy parser override.
            bases = next((q["args"] for q in cs if q["type"] == "parallel"), [[a, b], [c, d]])
            legs = [
                [pts[i], pts[(i + 1) % 4]]
                for i in range(4)
                if set([pts[i], pts[(i + 1) % 4]]) not in [set(s) for s in bases]
            ]
            if (
                "равнобедрен" in low
                or "равнобок" in low
                or re.search(r"около\s+трапец\w*\s+описана\s+окружность", low)
            ):
                add("equal_segments", legs)
                add("equal_segments", [[a, c], [b, d]])
            add("parallel", bases)
            m = re.search(r"большее\s+основание.*?равно\s*(" + NUM + ")", text, re.I)
            if m:
                add("distance", bases[0], val(m))
            m = re.search(r"боковая\s+сторона\s+равна\s*(" + NUM + ")", text, re.I)
            if m:
                add("distance", legs[0], val(m))
            m = re.search(r"sin\s+острого\s+угла\s+равен\s*(" + NUM + ")", text, re.I)
            if m:
                add("angle", [d, a, b], math.degrees(math.asin(val(m))))
                # Keep the declared larger base larger (not its crossed branch).
                add("segment_difference", bases, 0.001)
            m = re.search(r"периметр\s+трапец\w*\s+равен\s*(" + NUM + ")", text, re.I)
            if m:
                add("perimeter", pts, val(m))
            m = re.search(r"средняя\s+линия\s+равна\s*(" + NUM + ")", text, re.I)
            if m:
                add("segment_sum", bases, 2 * val(m))

    for m in re.finditer(r"(?:угол|∠)\s*([A-Z]{3})\s+(?:прямой|равен\s+90)", text, re.I):
        add("right_angle", list(m[1].upper()))
    triangles = [f["points"] for f in figures if len(f["points"]) == 3]
    # Alt text may separate letters in AM=MC; normalize before invoking parser.
    for m in re.finditer(
        r"на\s+стороне\s+([A-Z]{2}).{0,90}?(?:выбрана|отмечена|взята)\s+(?:такая\s+)?точка\s+([A-Z])",
        text,
        re.I,
    ):
        seg, n = m[1].upper(), m[2].upper()
        if n not in seg:
            add("point_on_segment", [n, *seg])
    for m in re.finditer(r"([A-Z])\s*[- ]*\s*середина\s+стороны\s+([A-Z]{2})", text):
        add("midpoint", [m[1], *m[2]])
    for m in re.finditer(r"биссектрис\w*\s+([A-Z]{2})", text, re.I):
        v, k = m[1].upper()
        tri = next((tri for tri in triangles if v in tri), None)
        if tri:
            side = [n for n in tri if n != v]
            line(v, k)
            add("point_on_segment", [k, *side])
            add("bisector", [v, k, *side])
    # A list followed by «высоты», and singular heights (including a requested CH).
    heights = []
    for m in re.finditer(r"([A-Z]{2})\s*,\s*([A-Z]{2})\s+и\s+([A-Z]{2})\s*-?\s*высоты", text):
        heights.extend(m.groups())
    heights.extend(m[1].upper() for m in re.finditer(r"высот\w*\s+([A-Z]{2})", text, re.I))
    for seg in set(heights):
        v, h = seg
        tri = next((tri for tri in triangles if v in tri and h not in tri), None)
        if tri:
            side = [n for n in tri if n != v]
            line(v, h)
            add("projection", [h, v, *side])
            # A height in an obtuse triangle may end on the extension.
            cs[:] = [q for q in cs if not (q["type"] == "point_on_segment" and q["args"][0] == h)]
    m = re.search(r"высоты,\s*пересекающиеся\s+в\s+точке\s+([A-Z])", text, re.I)
    if m:
        for seg in set(heights):
            add("point_on_line", [m[1].upper(), *seg])

    # Inscribed circle wording in both directions; only the specified triangle.
    target = None
    m = re.search(r"вписанн\w*\s+в\s+(?:него\s+|треугольник\s+([A-Z]{3})\s+)?окружност", text, re.I)
    if m:
        target = list(m[1].upper()) if m[1] else (triangles[0] if triangles else None)
    if re.search(r"окружност\w*,?\s+вписанн\w*\s+в\s+правильн", text, re.I):
        target = triangles[0] if triangles else None
    if target:
        # Remove incorrect legacy selection of the enclosing triangle.
        cs[:] = [q for q in cs if q["type"] != "inscribed_circle"]
        center_match = re.search(r"точка\s+([A-Z])\s*-\s*центр\s+вписанн", text, re.I)
        center = center_match[1].upper() if center_match else "I"
        circles[:] = [c for c in circles if c.get("name") != "inscribed" or c["center"] == center]
        circle(center)
        add("inscribed_circle", [center, *target])

    # Circumcircle of trapezoid / cyclic polygon. A radius is determined by vertices.
    cyclic = []
    for f in figures:
        if (
            re.search(r"около\s+трапец\w*\s+описана\s+окружность", low) and f["type"] == "trapezoid"
        ) or re.search(r"четыр[её]хугольник\s+" + f["name"] + r"\s+вписан", text, re.I):
            cyclic = f["points"]
    if cyclic:
        circle("O", cyclic)
        add("circumscribed_circle", ["O", *cyclic])

    # Chord and tangent: central angle equals minor arc; BC is the tangent ray.
    m = re.search(
        r"хорда\s+([A-Z]{2})\s+стягивает\s+дугу\s+окружности\s+в\s*(" + NUM + ")", text, re.I
    )
    if m:
        a, b = m[1].upper()
        circle("O", [a, b])
        line(a, b)
        add("angle", [a, "O", b], val(m, 2))
        target_angle = re.search(r"угол\s+([A-Z]{3})\s+между", text, re.I)
        if target_angle:
            x, v, z = target_angle[1].upper()
            line(v, z)
            add("perpendicular", [[v, z], ["O", v]])
            # Tangent ray chosen by the explicitly requested acute chord angle.
            add("angle", [x, v, z], val(m, 2) / 2)
    # Two diameters and an inscribed angle.
    m = re.search(r"([A-Z]{2})\s+и\s+([A-Z]{2})\s*-\s*диаметры", text)
    if m:
        center = re.search(r"центром\s+([A-Z])", text)
        o = center[1] if center else "O"
        for seg in m.groups():
            circle(o, list(seg))
            line(*seg)
            add("midpoint", [o, *seg])
    # Arc AC not containing B can be reflex: encode its cosine as central angle,
    # plus the equivalent inscribed angle to select the correct branch.
    arcs = list(
        re.finditer(
            r"дуга\s+окружности\s+([A-Z]{2})\s*,?\s*не\s+содержащая\s+точки\s+([A-Z])\s*,?\s*составляет\s*("
            + NUM
            + ")",
            text,
            re.I,
        )
    )
    if arcs:
        for m in arcs:
            a, b = m[1].upper()
            v = m[2].upper()
            degrees = val(m, 3)
            if not 0 < degrees < 360:
                raise ValueError("Дуга должна быть в (0, 360)")
            circle("O", [a, b, v])
            line(a, b)
            line(a, v)
            line(b, v)
            add("angle", [a, v, b], degrees / 2)

    from backend.extended_constructions import enrich_extended

    raw["points"] = sorted(p)
    return enrich_extended(raw, text)
