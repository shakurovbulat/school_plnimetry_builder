"""Further graph extraction; explicit incidences, never theorem conclusions."""

import re


def complete_graph(raw, text, ops):
    point, line, add, triangle, circle, incircle, height, bisector, intersection, distinct = ops
    recognized = False
    # A quadrilateral with diagonals and four circumcentres.
    q = re.search(r"четыр[её]хугольник\w*\s+([A-Z]{4})", text, re.I)
    if q and "диагонали" in text:
        recognized = True
        ns = list(q[1].upper())
        raw["figures"].append(dict(type="quadrilateral", name="".join(ns), points=ns))
        for a, b in zip(ns, ns[1:] + ns[:1]):
            line(a, b)
        o = re.search(r"точке\s+([A-Z])", text)
        o = o[1] if o else "O"
        intersection(o, ns[::2], ns[1::2])
        add("point_on_segment", [o, *ns[::2]])
        add("point_on_segment", [o, *ns[1::2]])
        m = re.search(r"([A-Z]{2})·([A-Z]{2})\s*=\s*([A-Z]{2})·([A-Z]{2})", text)
        if m:
            add("product_equal", [list(s) for s in m.groups()])
        triples = re.search(
            r"треугольников\s+([A-Z]{3}),\s*([A-Z]{3}),\s*([A-Z]{3})\s+и\s+([A-Z]{3})", text
        )
        if triples:
            centers = re.search(
                r"центры\s+([A-Z]\d+),\s*([A-Z]\d+),\s*([A-Z]\d+)\s+и\s+([A-Z]\d+)", text
            )
            if centers:
                for tri, c in zip(triples.groups(), centers.groups()):
                    circle(c, tri=list(tri))
        pairs = re.search(
            r"окружности\s+треугольников\s+([A-Z]{3})\s+и\s+([A-Z]{3}).*?точке\s+([A-Z])", text
        )
        if pairs:
            for i, tri in enumerate(pairs.groups()[:2], 1):
                c = "O" + str(i)
                circle(c, tri=list(tri))
                add("point_on_circle", [pairs[3], c])
                add("distinct", [pairs[3], o])
    tri_match = re.search(r"треугольник\w*\s+([A-Z]{3})", text)
    tri = list(tri_match[1]) if tri_match else None
    if tri:
        # Incircles of two subtriangles, named contacts on their common side.
        m = re.search(
            r"[Оо]кружности,\s*вписанные\s+в\s+треугольники\s+([A-Z]{3})\s+и\s+([A-Z]{3}).*?стороны\s+([A-Z]{2})\s+в\s+точках\s+([A-Z])\s+и\s+([A-Z])",
            text,
        )
        if m:
            recognized = True
            triangle(tri)
            membership = re.search(r"точка\s+([A-Z])\s+лежит\s+на\s+стороне\s+([A-Z]{2})", text)
            if membership:
                add("point_on_segment", [membership[1], *membership[2]])
            for i, (sub, contact) in enumerate(zip(m.groups()[:2], m.groups()[3:]), 1):
                c = "I" + str(i)
                triangle(list(sub))
                incircle(c, list(sub))
                add("projection", [contact, c, *m[3]])
                add("point_on_circle", [contact, c])
                line(c, contact)
        # Circle through two vertices, second intersections with sides, cevian P.
        m = re.search(
            r"окружность.*?через\s+вершины\s+([A-Z])\s+и\s+([A-Z]).*?пересекает\s+стороны\s+([A-Z]{2})\s+и\s+([A-Z]{2}).*?точках\s+([A-Z])\s+и\s+([A-Z])",
            text,
            re.I,
        )
        if m:
            recognized = True
            triangle(tri)
            circle("O", vertices=[m[1].upper(), m[2].upper()])
            for side, n in [(m[3], m[5]), (m[4], m[6])]:
                add("point_on_segment", [n, *side])
                add("point_on_circle", [n, "O"])
                for a in set(side) & set(m[1] + m[2]):
                    add("distinct", [n, a])
            x = re.search(
                r"прямые\s+([A-Z]{2})\s+и\s+([A-Z]{2})\s+пересекаются\s+в\s+точке\s+([A-Z])",
                text,
                re.I,
            )
            if x:
                intersection(x[3].upper(), list(x[1].upper()), list(x[2].upper()))
        # Median, equal offsets and two secants through its foot.
        m = re.search(r"медиана\s+([A-Z]{2})", text)
        if m and re.search(r"окружност", text, re.I) and re.search(r"[XY]" + m[1][1], text):
            recognized = True
            triangle(tri)
            v, foot = m[1]
            side = [n for n in tri if n != v]
            add("midpoint", [foot, *side])
            line(v, foot)
            circle("O", tri=tri)
            pts = re.search(
                r"на\s+сторонах\s+([A-Z]{2})\s+и\s+([A-Z]{2}).*?точки\s+([A-Z])\s+и\s+([A-Z])",
                text,
                re.I,
            )
            if pts:
                for s, n in [(pts[1], pts[3]), (pts[2], pts[4])]:
                    add("point_on_segment", [n, *s])
            eq = re.search(r"([A-Z]{2})\s*=\s*([A-Z]{2})", text)
            if eq:
                add("equal_segments", [list(eq[1]), list(eq[2])])
            for s, n in [("X" + foot, "P"), ("Y" + foot, "Q")]:
                if s in text:
                    add("point_on_line", [n, *s])
                    add("point_on_circle", [n, "O"])
                    line(*s)
        # Three altitudes and an ambiguous secant: draw both branches.
        m = re.search(r"высоты\s+([A-Z]{2}),\s*([A-Z]{2})\s+и\s+([A-Z]{2})", text)
        if m and re.search(r"прямую\s+[A-Z]{2}", text):
            recognized = True
            triangle(tri)
            circle("O", tri=tri)
            for seg in m.groups():
                height(seg[0], seg[1], tri)
            sec = re.search(r"прямую\s+([A-Z]{2}).*?точке\s+([A-Z])", text)
            if sec:
                side, n = sec.groups()
                line(*side)
                for name in [n, n + "1"]:
                    add("point_on_line", [name, *side])
                    add("point_on_circle", [name, "O"])
                add("distinct", [n, n + "1"])
        # Tangent at a vertex and angular bisector meeting it.
        m = re.search(
            r"касательная\s+к\s+описанной\s+окружности\s+в\s+точке\s+([A-Z]).*?биссектриса\s+угла\s+([A-Z])\s+пересекает\s+([A-Z]{2})\s+в\s+точке\s+([A-Z]).*?точке\s+([A-Z])",
            text,
            re.I,
        )
        if m:
            recognized = True
            triangle(tri)
            circle("O", tri=tri)
            a, v, side, d, e = (s.upper() for s in m.groups())
            bisector(v, d, tri)
            add("point_on_line", [e, v, d])
            add("tangent", ["O", a, e])
            line(a, e)
            line(v, e)
    # Two intersecting circles and a common secant; centre labels are synthetic.
    if re.search(r"две\s+окружности", text, re.I):
        sec = re.search(r"через\s+([A-Z]).*?точке\s+([A-Z]).*?точке\s+([A-Z])", text, re.I)
        if "касаются внешним образом" in text:
            raise ValueError(
                "Несовместимые условия: у двух внешне касающихся окружностей касательные в повторных пересечениях общей прямой через точку касания параллельны. Конечной точки P их пересечения нет."
            )

        else:
            m = re.search(r"пересекаются\s+в\s+точках\s+([A-Z])\s+и\s+([A-Z])", text)
            if m and sec:
                recognized = True
                a, b = m.groups()
                c, d = sec[2].upper(), sec[3].upper()
                circle("O1", vertices=[a, b, c])
                circle("O2", vertices=[a, b, d])
                distinct([a, b, c, d])
                add("point_on_line", [d, a, c])
                line(a, d)
                x = re.search(r"пересекаются\s+в\s+точке\s+([A-Z])", text)
                if x:
                    for o, n in [("O1", c), ("O2", d)]:
                        add("tangent", [o, n, x[1]])
                        line(n, x[1])
    # Three pairwise intersecting circles: six distinct intersection points.
    if re.search(r"три\s+окружности,\s*попарно\s+пересекающиеся", text, re.I):
        recognized = True
        for o, vertices in [("O1", "ABCD"), ("O2", "ABEF"), ("O3", "CDEF")]:
            circle(o, vertices=list(vertices))
        distinct(list("ABCDEF"))
        for s in ["AB", "CD", "EF"]:
            line(*s)
    # Chords of one circle and intersections of their tangent pairs.
    m = re.search(r"с\s+центром\s+([A-Z]).*?хорды\s+([A-Z]{2})\s+и\s+([A-Z]{2})", text)
    if m and "касательные" in text:
        recognized = True
        o, s, t = m.groups()
        circle(o, vertices=list(s + t))
        distinct(list(s + t))
        p = re.search(r"продолжения\s+пересекаются\s+в\s+точке\s+([A-Z])", text)
        if p:
            intersection(p[1], list(s), list(t))
        for match in re.finditer(
            r"(?:в\s+точках\s+)?([A-Z])\s+и\s+([A-Z])\s*(?:пересекаются\s*|[-,]\s*)в\s+точке\s+([A-Z])",
            text,
        ):
            a, b, q = match.groups()
            for n in [a, b]:
                add("tangent", [o, n, q])
                line(n, q)
    return recognized
