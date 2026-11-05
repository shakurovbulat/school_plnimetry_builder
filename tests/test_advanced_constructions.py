"""Independent coordinate oracles for the advanced construction graph.

Conclusions of proposed theorems are deliberately NOT tested as premises.
"""

import json
import math
import unittest
from pathlib import Path

import numpy as np

from backend.models import GeometrySchema
from backend.parser import parse_geometry_text
from backend.sympy_solver import SympyGeometrySolver
from backend.text_normalization import normalize_text

TASKS = json.loads((Path(__file__).parent / "fixtures/advanced_20.json").read_text(encoding="utf8"))


def schema_for(n):
    raw = parse_geometry_text(TASKS[n - 1])
    return GeometrySchema.model_validate({k: raw.get(k, []) for k in GeometrySchema.model_fields})


def verify_source(n, sol):
    p = {k: np.array(v, dtype=float) for k, v in sol["points"].items()}
    scale = max(1, max(np.linalg.norm(v) for v in p.values()))
    eps = 4e-4

    def close(x, y=0):
        if not math.isclose(float(x), float(y), rel_tol=eps, abs_tol=eps):
            raise AssertionError(f"case {n}: {x} != {y}")

    def d(a, b):
        return np.linalg.norm(p[a] - p[b])

    def cross(u, v):
        return float(u[0] * v[1] - u[1] * v[0])

    def col(q, a, b):
        assert d(a, b) > 1e-3
        close(cross(p[b] - p[a], p[q] - p[a]) / (d(a, b) * scale))

    def inside(q, a, b):
        col(q, a, b)
        close((d(a, q) + d(q, b) - d(a, b)) / scale)

    def perp(a, b, c, e):
        assert d(a, b) > 1e-3 and d(c, e) > 1e-3
        close(np.dot(p[b] - p[a], p[e] - p[c]) / (d(a, b) * d(c, e)))

    def eq(x, y):
        close(x / scale, y / scale)

    def circ(o, vs):
        r = next(c["radius"] for c in sol["circles"] if c["center"] == o)
        assert r > 1e-3
        for v in vs:
            eq(d(o, v), r)

    def inc(o, vs):
        distances = []
        signs = []
        for a, b in zip(vs, vs[1:] + vs[:1]):
            val = cross(p[b] - p[a], p[o] - p[a]) / d(a, b)
            distances.append(abs(val))
            signs.append(val)
        for r in distances[1:]:
            eq(r, distances[0])
        assert all(s > 0 for s in signs) or all(s < 0 for s in signs)
        eq(next(c["radius"] for c in sol["circles"] if c["center"] == o), distances[0])

    def bis(v, h, left, right):
        u = (p[left] - p[v]) / d(left, v) + (p[right] - p[v]) / d(right, v)
        close(cross(u, p[h] - p[v]) / (np.linalg.norm(u) * d(v, h)))
        assert np.dot(u, p[h] - p[v]) > 0

    def tangent(o, h, q):
        circ(o, [h])
        perp(o, h, h, q)

    if n == 1:
        for v, h, a, b in [("A", "A1", "B", "C"), ("B", "B1", "A", "C"), ("C", "C1", "A", "B")]:
            col(h, a, b)
            perp(v, h, a, b)
            col("H", v, h)
        circ("O1", "BCEF")
        inside("E", "A", "B")
        inside("F", "A", "C")
        assert d("E", "B") > 0.01 and d("F", "C") > 0.01
        for v, a, b in [("A", "B", "C"), ("B", "A", "C"), ("C", "A", "B")]:
            assert np.dot(p[a] - p[v], p[b] - p[v]) > 0
    elif n == 2:
        circ("O1", "ABC")
        circ("O2", "ABD")
        col("D", "A", "C")
        tangent("O1", "C", "P")
        tangent("O2", "D", "P")
        assert d("O1", "O2") > 0.01
    elif n == 3:
        bis("A", "I", "B", "C")
        bis("B", "I", "A", "C")
        circ("O1", "ABIMN")
        inside("M", "A", "C")
        inside("N", "B", "C")
        assert d("M", "A") > 0.01 and d("N", "B") > 0.01
    elif n == 4:
        inside("O", "A", "C")
        inside("O", "B", "D")
        close(
            d("A", "B") * d("C", "D") / (scale * scale), d("A", "D") * d("B", "C") / (scale * scale)
        )
    elif n == 5:
        inside("D", "B", "C")
        inc("I1", "ABD")
        inc("I2", "ACD")
        for o, h in [("I1", "E"), ("I2", "F")]:
            inside(h, "A", "D")
            perp(o, h, "A", "D")
            circ(o, [h])
    elif n == 6:
        circ("O", "ABMN")
        inside("M", "A", "C")
        inside("N", "B", "C")
        col("P", "A", "N")
        col("P", "B", "M")
        assert d("M", "A") > 0.01 and d("N", "B") > 0.01
    elif n == 7:
        for i in range(2):
            close((p["M"][i] - (p["B"][i] + p["C"][i]) / 2) / scale)
        inside("X", "A", "B")
        inside("Y", "A", "C")
        eq(d("B", "X"), d("C", "Y"))
        col("P", "X", "M")
        col("Q", "Y", "M")
        circ("O", "ABCPQ")
    elif n == 8:
        for o, vs in [("O1", "ABCD"), ("O2", "ABEF"), ("O3", "CDEF")]:
            circ(o, vs)
        for i, a in enumerate("ABCDEF"):
            for b in "ABCDEF"[i + 1 :]:
                assert d(a, b) > 0.01
    elif n == 9:
        inc("I", "ABC")
        for h, a, b in [("D", "A", "B"), ("E", "B", "C"), ("F", "C", "A")]:
            inside(h, a, b)
            perp("I", h, a, b)
            circ("I", [h])
        inside("M", "A", "B")
        inside("N", "A", "C")
        col("I", "M", "N")
        close(cross(p["N"] - p["M"], p["C"] - p["B"]) / (d("M", "N") * d("B", "C")))
    elif n == 10:
        circ("O", "ABCD")
        col("P", "A", "B")
        col("P", "C", "D")
        for o, h, q in [("O", "A", "X"), ("O", "C", "X"), ("O", "B", "Y"), ("O", "D", "Y")]:
            tangent(o, h, q)
    elif n == 11:
        for v, h, left, right in [("A", "D", "B", "C"), ("B", "E", "A", "C"), ("C", "F", "A", "B")]:
            inside(h, left, right)
            bis(v, h, left, right)
    elif n == 12:
        inside("O", "A", "C")
        inside("O", "B", "D")
        circ("O1", "AOBP")
        circ("O2", "CODP")
        assert d("O", "P") > 0.01
    elif n == 13:
        for v, h, a, b in [("A", "D", "B", "C"), ("B", "E", "A", "C"), ("C", "F", "A", "B")]:
            col(h, a, b)
            perp(v, h, a, b)
        circ("O", ["A", "B", "C", "P", "P1"])
        col("P", "E", "F")
        col("P1", "E", "F")
        assert d("P", "P1") > 0.01
    elif n == 14:
        circ("O1", "TA")
        circ("O2", "TB")
        col("B", "T", "A")
        eq(d("O1", "O2"), d("O1", "T") + d("O2", "T"))
        col("T", "O1", "O2")
        tangent("O1", "A", "P")
        tangent("O2", "B", "P")
    elif n == 15:

        def cos(v, a, b):
            return np.dot(p[a] - p[v], p[b] - p[v]) / (d(v, a) * d(v, b))

        close(cos("A", "P", "B"), cos("B", "P", "C"))
        close(cos("B", "P", "C"), cos("C", "P", "A"))
        signs = [cross(p[b] - p[a], p["P"] - p[a]) for a, b in zip("ABC", "BCA")]
        assert all(s > 0 for s in signs) or all(s < 0 for s in signs)
    elif n == 16:
        inside("M", "A", "B")
        inside("N", "A", "C")
        col("P", "B", "N")
        col("P", "C", "M")
        close(d("A", "M") / d("M", "B"), d("A", "N") / d("N", "C"))
    elif n == 17:
        inside("O", "A", "C")
        inside("O", "B", "D")
        for o, vs in [("O1", "AOB"), ("O2", "BOC"), ("O3", "COD"), ("O4", "DOA")]:
            circ(o, vs)
    elif n == 18:
        circ("O", "ABC")
        inside("D", "A", "C")
        bis("B", "D", "A", "C")
        col("E", "B", "D")
        tangent("O", "A", "E")
    elif n == 19:
        circ("O", "ABCD")
        inside("P", "A", "B")
        inside("P", "C", "D")
        perp("A", "B", "C", "D")
    elif n == 20:
        circ("O", "ABC")
        inc("I", "ABC")
        for v, a, b in [("A", "B", "C"), ("B", "A", "C"), ("C", "A", "B")]:
            perp(v, "H", a, b)
        for q in ["M", "M1"]:
            circ("O", [q])
            col(q, "O", "H")
        assert d("M", "M1") > 0.01


class AdvancedPrimitiveTests(unittest.TestCase):
    def test_coordinate_checks(self):
        for n in [n for n in range(1, 21) if n not in (3, 14)]:
            with self.subTest(number=n):
                s = schema_for(n)
                verify_source(n, SympyGeometrySolver(s).solve())

    def test_impossible_incenter_circumcircle_sides(self):
        with self.assertRaisesRegex(ValueError, "Несовместимые"):
            schema_for(3)

    def test_parallel_tangents_have_no_finite_intersection(self):
        with self.assertRaisesRegex(ValueError, "параллельны"):
            schema_for(14)

    def test_index_normalization(self):
        self.assertIn("AA1", normalize_text("AA₁"))
        self.assertIn("O2", normalize_text("O_2"))

    def test_index_schema(self):
        s = GeometrySchema(points=["A", "A1", "O12"], lines=[["A", "A1"]])
        self.assertEqual(len(s.points), 3)

    def test_no_conclusions_as_givens(self):
        s = schema_for(16)
        self.assertFalse(any(c.type == "bisector" for c in s.constraints))
