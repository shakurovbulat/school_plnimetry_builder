"""Independent source-condition checks for variant 93751277."""

import json
import math
import unittest
from pathlib import Path

from test_external_regressions import angle, distance_line

from backend.llm_parser import parse_hybrid
from backend.sympy_solver import SympyGeometrySolver

TASKS = json.loads(
    (Path(__file__).parent / "fixtures/ege_93751277.json").read_text(encoding="utf8")
)
SUPPORTED = tuple(n for n in range(1, 21) if n not in (7, 16))


def verify_case(n, schema, sol):
    p = sol["points"]
    d = lambda a, b: math.dist(p[a], p[b])

    def close(x, y):
        if not math.isclose(x, y, rel_tol=3e-4, abs_tol=3e-4):
            raise AssertionError(f"№{n}: {x} != {y}")

    def incircle(o, names):
        assert len(sol["circles"]) == 1
        r = sol["circles"][0]["radius"]
        signs = []
        for a, b in zip(names, names[1:] + names[:1]):
            close(distance_line(p, o, a, b), r)
            u = [p[b][i] - p[a][i] for i in range(2)]
            w = [p[o][i] - p[a][i] for i in range(2)]
            signs.append(u[0] * w[1] - u[1] * w[0])
        assert all(s > 0 for s in signs) or all(s < 0 for s in signs)

    def on(q, a, b):
        close(distance_line(p, q, a, b), 0)

    if n == 1:
        close(d("A", "B"), 3)
        close(d("A", "D"), 21)
        close(math.sin(math.radians(angle(p, "D", "A", "B"))), 6 / 7)
        close(d("D", "H"), 18)
        close(angle(p, "D", "H", "B"), 90)
        on("H", "A", "B")
        close(d("B", "K"), 18 / 7)
        on("K", "A", "D")
    elif n == 2:
        close(d("A", "C"), 2 * math.sqrt(3))
        close(d("B", "C"), d("A", "C"))
        close(angle(p, "A", "C", "B"), 120)
        close(d("A", "B"), 6)
    elif n == 3:
        close(angle(p, "A", "O", "B") - angle(p, "A", "C", "B"), 56)
        close(angle(p, "A", "C", "B"), 56)
        for a in "ABC":
            close(d("O", a), sol["circles"][0]["radius"])
    elif n == 4:
        close(angle(p, "A", "C", "B"), 34)
        close(angle(p, "O", "A", "C"), 90)
        close(angle(p, "O", "B", "C"), 90)
        close(d("O", "A"), d("O", "B"))
        close(angle(p, "A", "O", "B"), 146)
    elif n == 5:
        close(angle(p, "A", "C", "B"), 90)
        close(angle(p, "A", "B", "C"), 61)
        close(angle(p, "H", "C", "D"), 16)
        on("H", "A", "B")
        on("D", "A", "B")
        close(angle(p, "A", "C", "D"), 45)
        close(angle(p, "C", "H", "B"), 90)
    elif n == 6:
        on("H", "A", "B")
        close(angle(p, "D", "H", "B"), 90)
        close(d("A", "H"), 23)
        close(d("H", "B"), 38)
        close(d("A", "D"), d("B", "C"))
        close((d("A", "B") + d("C", "D")) / 2, 38)
    elif n == 8:
        incircle("I", "ABC")
        close(sol["circles"][0]["radius"], 31)
        close(d("C", "H"), 93)
        close(d("A", "B"), d("A", "C"))
        close(d("A", "B"), d("B", "C"))
    elif n == 9:
        close(angle(p, "C", "A", "B"), 30)
        close(angle(p, "A", "B", "C"), 86)
        on("D", "A", "B")
        on("E", "A", "C")
        close(d("A", "C") + d("C", "E"), d("A", "E"))
        close(d("C", "E"), d("C", "B"))
        close(angle(p, "B", "C", "D"), angle(p, "D", "C", "E"))
        close(angle(p, "B", "D", "E"), 56)
    elif n == 10:
        close(d("A", "B"), 15)
        close(angle(p, "A", "C", "B"), 90)
        close(math.tan(math.radians(angle(p, "B", "A", "C"))), 4 / 3)
        on("H", "A", "B")
        close(angle(p, "C", "H", "B"), 90)
        close(d("B", "H"), 9.6)
    elif n == 11:
        close(d("A", "B"), 9)
        close(d("A", "D"), 15)
        close(d("D", "H"), 10)
        on("H", "A", "B")
        on("K", "A", "D")
        close(d("B", "K"), 6)
    elif n == 12:
        close(d("A", "C"), 8)
        close(d("B", "C"), 8)
        close(d("A", "H"), 4)
        close(angle(p, "A", "C", "B"), 150)
        close(math.sin(math.radians(angle(p, "A", "C", "B"))), 0.5)
        on("H", "B", "C")
        close(angle(p, "A", "H", "C"), 90)
    elif n == 13:
        incircle("O", "ABCD")
        close(sol["circles"][0]["radius"], 9)
        close(angle(p, "D", "A", "B"), 30)
        for a, b in zip("ABCD", "BCDA"):
            close(d(a, b), 36)
    elif n == 14:
        close(d("C", "D"), 2)
        close((d("A", "B") + d("C", "D")) / 2, 5)
        close(d("A", "B"), 8)
        close(distance_line(p, "C", "A", "B"), distance_line(p, "D", "A", "B"))
    elif n == 15:
        for a, b in zip("ABCDEF", "BCDEFA"):
            close(d(a, b), 18)
        for a in "ABCDEF":
            close(d("O", a), 18)
        close(d("A", "D"), 36)
        for a, b, c in zip("ABCDEF", "BCDEFA", "CDEFAB"):
            close(angle(p, a, b, c), 120)
    elif n == 17:
        close(angle(p, "A", "C", "B"), 23)
        close(angle(p, "B", "A", "D"), 19)
        close(angle(p, "D", "A", "C"), 19)
        on("D", "B", "C")
        close(angle(p, "A", "D", "B"), 42)
    elif n == 18:
        close(angle(p, "A", "O", "B"), 92)
        close(angle(p, "O", "B", "C"), 90)
        close(angle(p, "A", "B", "C"), 46)
        close(d("O", "A"), d("O", "B"))
    elif n == 19:
        close(d("A", "B"), 41)
        close(d("C", "D"), 46)
        incircle("O", "ABCD")
        close(sum(d(a, b) for a, b in zip("ABCD", "BCDA")), 174)
    elif n == 20:
        close(d("A", "C"), 1)
        close(d("B", "C"), 1)
        close(angle(p, "A", "C", "B"), 120)
        for a in "ABC":
            close(d("O", a), 1)
    else:
        raise AssertionError("Missing oracle")


class Variant93751277Tests(unittest.TestCase):
    def test_source_conditions_independently(self):
        for n in SUPPORTED:
            with self.subTest(number=n):
                s, _ = parse_hybrid(TASKS[n - 1]["text"], mode="rules")
                verify_case(n, s, SympyGeometrySolver(s).solve())

    def test_missing_drawing_not_invented(self):
        with self.assertRaisesRegex(ValueError, "рисунка"):
            parse_hybrid(TASKS[15]["text"], mode="rules")

    def test_large_polygon_explicit_limitation(self):
        with self.assertRaisesRegex(ValueError, "числом вершин"):
            parse_hybrid(TASKS[6]["text"], mode="rules")

    def test_incircle_is_not_circumcircle(self):
        s, _ = parse_hybrid(TASKS[18]["text"], mode="rules")
        self.assertTrue(any(c.type == "inscribed_polygon" for c in s.constraints))
        self.assertFalse(any(c.type == "circumscribed_circle" for c in s.constraints))
        self.assertFalse(s.circles[0].passing_through)

    def test_changed_lengths(self):
        text = TASKS[13]["text"].replace("5", "7").replace("2", "4")
        s, _ = parse_hybrid(text, mode="rules")
        p = SympyGeometrySolver(s).solve()["points"]
        self.assertAlmostEqual(math.dist(p["A"], p["B"]), 10, places=3)
