"""Additional text-driven constructions for heights, tangencies and bisectors."""

import re

N = r"\d+(?:[.,]\d+)?"


def enrich_extended(raw, text):
    ps, ls, fs, cs, circles = [
        raw[k] for k in ("points", "lines", "figures", "constraints", "circles")
    ]

    def point(n):
        if n not in ps:
            ps.append(n)

    def line(a, b):
        point(a)
        point(b)
        if [a, b] not in ls and [b, a] not in ls:
            ls.append([a, b])

    def add(t, args, v=None):
        def visit(xs):
            for x in xs:
                if isinstance(x, list):
                    visit(x)
                else:
                    point(x)

        visit(args)
        q = dict(type=t, args=args)
        if v is not None:
            q["value"] = v
        if q not in cs:
            cs.append(q)

    def fig(t, name):
        if not any(f["name"] == name for f in fs):
            fs.append(dict(type=t, name=name, points=list(name)))
        for a, b in zip(name, name[1:] + name[:1]):
            line(a, b)

    def circle(o, vertices=(), radius=None):
        point(o)
        c = next((c for c in circles if c["center"] == o), None)
        if c is None:
            c = dict(name="omega", center=o, passing_through=[])
            circles.append(c)
        for v in vertices:
            point(v)
            if v not in c.setdefault("passing_through", []):
                c["passing_through"].append(v)
        if radius is not None:
            c["radius"] = radius
        return c

    def v(m, i=1):
        return float(m[i].replace(",", "."))

    def height(h, q, a, b, length=None):
        line(q, h)
        add("projection", [h, q, a, b])
        if length is not None:
            add("distance", [q, h], length)

    low = text.lower()
    if not fs:
        if "параллелограмм" in low:
            fig("parallelogram", "ABCD")
        elif "равнобедренного треугольника" in low:
            fig("triangle", "ABC")
    # Chain equalities retain the terminal length for all members.
    for m in re.finditer(r"(?<![A-Z])([A-Z]{2}(?:\s*=\s*[A-Z]{2})+)\s*=\s*(" + N + ")", text):
        for seg in re.findall("[A-Z]{2}", m[1]):
            add("distance", list(seg), v(m, 2))
    # «Острый угол B ... равен 61» with words between label and value.
    for m in re.finditer(
        r"угол\s+([A-Z])\s+(?:прямоугольного\s+треугольника\s+[A-Z]{3}\s+)?равен\s*(" + N + ")",
        text,
        re.I,
    ):
        vertex = m[1].upper()
        tri = next(
            (f["points"] for f in fs if len(f["points"]) == 3 and vertex in f["points"]), None
        )
        if tri:
            others = [n for n in tri if n != vertex]
            add("angle", [others[0], vertex, others[1]], v(m, 2))
    for f in list(fs):
        p = f["points"]
        if f["type"] == "parallelogram":
            a, b, c, d = p
            for trig in re.finditer(r"(sin|cos|tg)\s+([A-Z])\s*=\s*(" + N + ")", text):
                vertex = trig[2]
                i = p.index(vertex)
                add(trig[1], [p[i - 1], vertex, p[(i + 1) % 4]], v(trig, 3))
            m = re.search(
                r"стороны\s+параллелограмма\s+равны\s*(" + N + r")\s+и\s*(" + N + ")", text, re.I
            )
            if m:
                add("distance", [a, b], v(m))
                add("distance", [a, d], v(m, 2))
            if re.search(r"высот", text, re.I):
                m = re.search(r"высота.*?на\s+первую\s+сторону.*?равна\s*(" + N + ")", text, re.I)
                height("H", d, a, b, v(m) if m else None)
                height("K", b, a, d)
        if f["type"] == "trapezoid":
            a, b, c, d = p
            m = re.search(r"средняя\s+линия\s+трапеции\s+равна\s*(" + N + ")", text, re.I)
            if m:
                add("segment_sum", [[a, b], [c, d]], 2 * v(m))
            m = re.search(r"меньшее\s+основание\s+равно\s*(" + N + ")", text, re.I)
            if m:
                add("distance", [c, d], v(m))
                add("segment_difference", [[a, b], [c, d]], 0.001)
            m = re.search(
                r"перпендикуляр.*?делит\s+его\s+на\s+части.*?длины\s*("
                + N
                + r")\s+и\s*("
                + N
                + ")",
                text,
                re.I,
            )
            if m:
                height("H", d, a, b)
                add("point_on_segment", ["H", a, b])
                add("distance", [a, "H"], min(v(m), v(m, 2)))
                add("distance", ["H", b], max(v(m), v(m, 2)))
        if len(p) == 3:
            a, b, c = p
            if "тупоугольном" in low:
                # Equal sides identify their common obtuse apex.
                eq = next(
                    (
                        q
                        for q in cs
                        if q["type"] == "equal_segments" and len(set(sum(q["args"], []))) == 3
                    ),
                    None,
                )
                if eq:
                    apex = next(iter(set(eq["args"][0]) & set(eq["args"][1])))
                    ends = [n for n in p if n != apex]
                    add("obtuse_angle", [ends[0], apex, ends[1]])
            if "равнобедренного треугольника" in low:
                m = re.search(r"боковая\s+сторона.*?равна\s*(" + N + ")", text, re.I)
                if m:
                    add("distance", [a, c], v(m))
                    add("distance", [b, c], v(m))
                m = re.search(r"угол\s+при\s+вершине.*?равен\s*(" + N + ")", text, re.I)
                if m:
                    add("angle", [a, c, b], v(m))
                if re.search(r"описанн\w*\s+окружност", text, re.I):
                    circle("O", p)
                    add("circumscribed_circle", ["O", *p])
            # Height written «CH — высота» rather than «высота CH».
            for m in re.finditer(r"([A-Z]{2})\s*-\s*высота", text):
                q, h = m[1]
                if q in p:
                    ends = [n for n in p if n != q]
                    height(h, q, *ends)
            # «AD — биссектриса» (internal; external handled separately).
            for m in re.finditer(r"([A-Z]{2})\s*-\s*биссектриса(?!\s+внешнего)", text):
                q, h = m[1]
                if q in p:
                    ends = [n for n in p if n != q]
                    line(q, h)
                    add("bisector", [q, h, *ends])
                    add("point_on_segment", [h, *ends])
            m = re.search(r"([A-Z]{2})\s*-\s*биссектриса\s+внешнего", text)
            if m:
                q, h = m[1]
                ends = [n for n in p if n != q]
                line(q, h)
                add("external_bisector", [q, h, *ends])
                add("point_on_line", [h, *ends])
                cs[:] = [
                    r for r in cs if not (r["type"] == "point_on_segment" and r["args"][0] == h)
                ]
            m = re.search(
                r"на\s+продолжении\s+стороны\s+([A-Z]{2})\s+за\s+точку\s+([A-Z]).*?точка\s+([A-Z])",
                text,
                re.I,
            )
            if m:
                x, y = m[1].upper()
                end = m[2].upper()
                e = m[3].upper()
                other = x if y == end else y
                line(end, e)
                add("point_between", [end, other, e])
            if f["type"] == "equilateral_triangle":
                m = re.search(r"радиус\s+окружности.*?равен\s*(" + N + ")", text, re.I)
                if m:
                    circle("I")
                    add("inscribed_circle", ["I", *p])
                    add("circle_radius", ["I"], v(m))
                    height("H", c, a, b)
    # Incircle of a convex polygon, not its circumcircle.
    for f in fs:
        name = f["name"]
        p = f["points"]
        inscribed = (
            re.search(
                r"(?:в|B)\s+четыр[её]хугольник\s+" + name + r"\s+вписана\s+окружность", text, re.I
            )
            or f["type"] == "rhombus"
            and re.search(r"вписанн\w*\s+в\s+этот\s+ромб\s+окружност", text, re.I)
        )
        if inscribed:
            circles.clear()
            cs[:] = [q for q in cs if q["type"] not in ("circumscribed_circle", "point_on_circle")]
            circle("O")
            add("inscribed_polygon", ["O", *p])
            m = re.search(r"радиус.*?равен\s*(" + N + ")", text, re.I)
            if m:
                add("circle_radius", ["O"], v(m))
            m = re.search(r"острый\s+угол\s+ромба\s+равен\s*(" + N + ")", text, re.I)
            if m:
                add("angle", [p[-1], p[0], p[1]], v(m))
    # Two tangents sharing the external point.
    m = re.search(
        r"касательные\s+([A-Z]{2})\s+и\s+([A-Z]{2})\s+к\s+окружности.*?равн\w*\s*(" + N + ")",
        text,
        re.I,
    )
    if m:
        s, t = m[1].upper(), m[2].upper()
        common = set(s) & set(t)
        if len(common) == 1:
            q = next(iter(common))
            a = next(n for n in s if n != q)
            b = next(n for n in t if n != q)
            circle("O", [a, b])
            line(q, a)
            line(q, b)
            add("perpendicular", [["O", a], [q, a]])
            add("perpendicular", [["O", b], [q, b]])
            add("angle", [a, q, b], v(m, 3))
    m = re.search(
        r"вписанный\s+угол\s+([A-Z]{3}).*?на\s*("
        + N
        + r")\s*°?\s*меньше\s+центрального\s+угла\s+([A-Z]{3})",
        text,
        re.I,
    )
    if m:
        a, c, b = m[1].upper()
        o = m[3].upper()[1]
        # For a common arc, central angle=2*inscribed; their difference=inscribed.
        circle(o, [a, b, c])
        line(a, c)
        line(b, c)
        line(o, a)
        line(o, b)
        add("angle", [a, c, b], v(m, 2))
        add("angle", [a, o, b], 2 * v(m, 2))
    # A regular hexagon has centre angles 60 degrees; six is not ID-specific.
    if re.search(r"правильного\s+шестиугольника", text, re.I):
        name = "ABCDEF"
        fig("regular_polygon", name)
        circle("O", name)
        for i, a in enumerate(name):
            b = name[(i + 1) % 6]
            add("angle", [a, "O", b], 60)
            if i:
                add("equal_segments", [[a, b], ["A", "B"]])
        m = re.search(r"периметр.*?равен\s*(" + N + ")", text, re.I)
        if m:
            add("perimeter", list(name), v(m))
    raw["points"] = sorted(ps)
    return raw
