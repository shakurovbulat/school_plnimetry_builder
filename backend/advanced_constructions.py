"""Compositional construction graph for advanced triangle/circle wording.

No theorem conclusion is used as a premise. Unknown configurations return None
so the regular parser can handle them (or issue a coverage error).
"""

import re

from backend.text_normalization import given_text


def parse_advanced(text):
    text = given_text(text).replace("—", "-").replace("–", "-")
    raw = {
        k: [] for k in ("points", "lines", "figures", "circles", "constraints", "givens", "targets")
    }

    def point(n):
        if n not in raw["points"]:
            raw["points"].append(n)

    def line(a, b):
        point(a)
        point(b)
        if [a, b] not in raw["lines"] and [b, a] not in raw["lines"]:
            raw["lines"].append([a, b])

    def add(t, args):
        def visit(xs):
            for x in xs:
                if isinstance(x, list):
                    visit(x)
                else:
                    point(x)

        visit(args)
        q = dict(type=t, args=args)
        if q not in raw["constraints"]:
            raw["constraints"].append(q)

    def triangle(names):
        for a, b in zip(names, names[1:] + names[:1]):
            line(a, b)
        raw["figures"].append(dict(type="triangle", name="".join(names), points=list(names)))

    def circle(o, vertices=(), tri=None, diameter=None):
        point(o)
        c = dict(name="omega" + o, center=o, passing_through=list(vertices))
        raw["circles"].append(c)
        for n in vertices:
            point(n)
        if tri:
            add("circumscribed_circle", [o, *tri])
        if diameter:
            add("midpoint", [o, *diameter])
            c["passing_through"] = list(diameter)

    def incircle(o, tri):
        circle(o)
        add("inscribed_circle", [o, *tri])

    def height(v, h, tri):
        side = [n for n in tri if n != v]
        line(v, h)
        add("projection", [h, v, *side])

    def bisector(v, h, tri):
        side = [n for n in tri if n != v]
        line(v, h)
        add("bisector", [v, h, *side])
        add("point_on_segment", [h, *side])

    def intersection(p, a, b):
        line(*a)
        line(*b)
        add("point_on_line", [p, *a])
        add("point_on_line", [p, *b])

    def distinct(names):
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                add("distinct", [a, b])

    tri_match = re.search(r"треугольник\w*\s+([A-Z]{3})(?![A-Z0-9])", text)
    tri = list(tri_match[1]) if tri_match else None
    recognized = False
    if tri:
        # Indexed altitude list (AA1, BB1, CC1) with a named orthocentre.
        m = re.search(
            r"высоты\s+([A-Z])([A-Z]\d+)\s*,\s*([A-Z])([A-Z]\d+)\s+и\s+([A-Z])([A-Z]\d+).*?точке\s+([A-Z])",
            text,
        )
        if m:
            triangle(tri)
            recognized = True
            for v, h in zip(m.groups()[:6:2], m.groups()[1:6:2]):
                height(v, h, tri)
                add("point_on_line", [m[7], v, h])
            if "остроугольн" in text:
                for i, v in enumerate(tri):
                    add("acute_angle", [tri[i - 1], v, tri[(i + 1) % 3]])
            d = re.search(
                r"окружность\s+с\s+диаметром\s+([A-Z]{2})\s+пересекает\s+([A-Z]{2})\s+и\s+([A-Z]{2})\s+в\s+точках\s+([A-Z])\s+и\s+([A-Z])",
                text,
                re.I,
            )
            if d:
                circle("O1", diameter=list(d[1]))
                for seg, q in [(d[2], d[4]), (d[3], d[5])]:
                    add("point_on_circle", [q, "O1"])
                    add("point_on_segment", [q, *seg])
                    shared = set(seg) & set(d[1])
                    for n in shared:
                        add("distinct", [q, n])
        # Bisector feet assigned in corresponding vertex order.
        m = re.search(
            r"точки\s+([A-Z]),\s*([A-Z])\s+и\s+([A-Z])\s+являются\s+основаниями\s+биссектрис",
            text,
            re.I,
        )
        if m:
            triangle(tri)
            recognized = True
            for v, h in zip(tri, [n.upper() for n in m.groups()]):
                bisector(v, h, tri)
        # Two angular bisectors meeting at a named point, plus ABI circumcircle.
        m = re.search(r"биссектрисы\s+углов\s+([A-Z])\s+и\s+([A-Z]).*?точке\s+([A-Z])", text)
        if m:
            triangle(tri)
            recognized = True
            i = m[3]
            incircle(i, tri)
            for v in m.groups()[:2]:
                sides = [n for n in tri if n != v]
                line(v, i)
                add("bisector", [v, i, *sides])
            c = re.search(
                r"окружность\s+треугольника\s+([A-Z]{3})\s+пересекает\s+стороны\s+([A-Z]{2})\s+и\s+([A-Z]{2}).*?точках\s+([A-Z])\s+и\s+([A-Z])",
                text,
            )
            if c and set(c[1]) == {m[1], m[2], i}:
                raise ValueError(
                    "Несовместимые условия: окружность через две вершины и инцентр не имеет двух различных повторных пересечений на обеих противоположных сторонах треугольника. Уточните: стороны или их прямые/продолжения. Почти вырожденный чертёж не считается решением."
                )
            if c:
                circle("O1", tri=list(c[1]))
                for seg, q in [(c[2], c[4]), (c[3], c[5])]:
                    add("point_on_circle", [q, "O1"])
                    add("point_on_segment", [q, *seg])
                    for old in set(seg) & set(c[1]):
                        add("distinct", [q, old])
        # Incentre and three named contacts, line through it parallel to a side.
        m = re.search(
            r"вписанная\s+окружность\s+с\s+центром\s+([A-Z]).*?в\s+точках\s+([A-Z]),\s*([A-Z])\s+и\s+([A-Z])",
            text,
        )
        if m:
            triangle(tri)
            recognized = True
            o = m[1]
            incircle(o, tri)
            sides = re.search(
                r"касающаяся\s+сторон\s+([A-Z]{2}),\s*([A-Z]{2})\s+и\s+([A-Z]{2})", text
            )
            if sides:
                for q, seg in zip(m.groups()[1:], sides.groups()):
                    add("projection", [q, o, *seg])
                    add("point_on_circle", [q, o])
                    line(o, q)
            c = re.search(
                r"параллельная\s+([A-Z]{2}).*?пересекает\s+([A-Z]{2})\s+и\s+([A-Z]{2})\s+в\s+точках\s+([A-Z])\s+и\s+([A-Z])",
                text,
            )
            if c:
                a, b = c[4], c[5]
                line(a, b)
                add("point_on_line", [o, a, b])
                add("parallel", [[a, b], list(c[1])])
                add("point_on_segment", [a, *c[2]])
                add("point_on_segment", [b, *c[3]])
        # Equal cyclic angles define a Brocard point, not a fabricated numeric alpha.
        m = re.search(r"∠([A-Z]{3})\s*=\s*∠([A-Z]{3})\s*=\s*∠([A-Z]{3})", text)
        if m:
            triangle(tri)
            recognized = True
            add("equal_angles", [list(m[1]), list(m[2])])
            add("equal_angles", [list(m[2]), list(m[3])])
            p = m[1][0]
            add("inside_triangle", [p, *tri])
            for v in tri:
                line(p, v)
        # Paired side points, cevian intersection and equality of ratios.
        m = re.search(
            r"точки\s+([A-Z])\s+и\s+([A-Z])\s+лежат\s+на\s+сторонах\s+([A-Z]{2})\s+и\s+([A-Z]{2})",
            text,
        )
        ratio = re.search(r"([A-Z]{2})/([A-Z]{2})\s*=\s*([A-Z]{2})/([A-Z]{2})", text)
        if m and ratio:
            triangle(tri)
            recognized = True
            add("point_on_segment", [m[1], *m[3]])
            add("point_on_segment", [m[2], *m[4]])
            add("ratio_equal", [list(seg) for seg in ratio.groups()])
            x = re.search(
                r"прямые\s+([A-Z]{2})\s+и\s+([A-Z]{2})\s+пересекаются\s+в\s+точке\s+([A-Z])",
                text,
                re.I,
            )
            if x:
                intersection(x[3].upper(), list(x[1].upper()), list(x[2].upper()))
        # Explicit Euler line centres; both intersections are constructed.
        m = re.search(
            r"ортоцентр\s+([A-Z]),\s*центр\s+описанной\s+окружности\s+([A-Z])\s+и\s+центр\s+вписанной\s+окружности\s+([A-Z])",
            text,
        )
        if m:
            triangle(tri)
            recognized = True
            h, o, i = m.groups()
            circle(o, tri=tri)
            incircle(i, tri)
            for k, v in enumerate(tri):
                side = [n for n in tri if n != v]
                line(v, h)
                add("perpendicular", [[v, h], side])
                if "остроугольн" in text:
                    add("acute_angle", [tri[k - 1], v, tri[(k + 1) % 3]])
            q = re.search(r"прямая\s+[A-Z]{2}\s+пересекает.*?точке\s+([A-Z])", text, re.I)
            if q:
                n = q[1].upper()
                line(o, h)
                add("point_on_line", [n, o, h])
                add("point_on_circle", [n, o])
                # A second branch is explicitly named rather than called unique.
                add("point_on_line", [n + "1", o, h])
                add("point_on_circle", [n + "1", o])
                add("distinct", [n, n + "1"])
    # Orthogonal chords through an interior point of a circle.
    m = re.search(
        r"внутри\s+окружности.*?точка\s+([A-Z]).*?перпендикулярные\s+хорды\s+([A-Z]{2})\s+и\s+([A-Z]{2})",
        text,
        re.I,
    )
    if m:
        recognized = True
        q = m[1].upper()
        s = m[2].upper()
        t = m[3].upper()
        circle("O", vertices=list(s + t))
        line(*s)
        line(*t)
        add("point_between", [q, *s])
        add("point_between", [q, *t])
        add("perpendicular", [list(s), list(t)])
    from backend.advanced_graphs import complete_graph

    recognized = (
        complete_graph(
            raw,
            text,
            (
                point,
                line,
                add,
                triangle,
                circle,
                incircle,
                height,
                bisector,
                intersection,
                distinct,
            ),
        )
        or recognized
    )
    if not recognized:
        return None
    raw["points"] = sorted(raw["points"])
    raw["source_text"] = text
    raw["clean_text"] = text
    return raw
