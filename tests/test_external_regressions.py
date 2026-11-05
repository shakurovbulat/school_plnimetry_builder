"""Independent regressions for external geometry statements (no network)."""

import json
import math
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend.llm_parser import parse_hybrid
from backend.models import GeometrySchema
from backend.sympy_solver import SympyGeometrySolver
from backend.text_normalization import given_text, normalize_text, numeric_expression

TASKS = json.loads(
    (Path(__file__).parent / "fixtures/ege_93749202.json").read_text(encoding="utf-8")
)
SUPPORTED = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 17, 18)


def angle(p, a, b, c):
    u = [p[a][i] - p[b][i] for i in range(2)]
    v = [p[c][i] - p[b][i] for i in range(2)]
    return math.degrees(
        math.acos(
            max(-1, min(1, sum(x * y for x, y in zip(u, v)) / math.hypot(*u) / math.hypot(*v)))
        )
    )


def distance_line(p, q, a, b):
    u = [p[b][i] - p[a][i] for i in range(2)]
    v = [p[q][i] - p[a][i] for i in range(2)]
    return abs(u[0] * v[1] - u[1] * v[0]) / math.hypot(*u)


def verify_case(n, schema, sol):
    """Checks from source statements, not solver-reported residuals."""
    p = sol["points"]
    d = lambda a, b: math.dist(p[a], p[b])

    def close(actual, expected):
        if not math.isclose(actual, expected, rel_tol=2e-4, abs_tol=2e-4):
            raise AssertionError(f"№{n}: {actual} != {expected}")

    def on(q, a, b):
        close(distance_line(p, q, a, b), 0)
        close(d(a, q) + d(q, b), d(a, b))

    def incircle(center, tri):
        assert len(sol["circles"]) == 1
        r = sol["circles"][0]["radius"]
        for a, b in zip(tri, tri[1:] + tri[:1]):
            close(distance_line(p, center, a, b), r)

    if n == 1:
        close(d("A", "B"), 18)
        close(d("C", "D"), 14)
        close(d("B", "C"), 3)
        close(d("A", "D"), 3)
        close(math.sin(math.radians(angle(p, "D", "A", "B"))), math.sqrt(5) / 3)
    elif n == 2:
        close(d("C", "H"), 6)
        close(d("A", "B"), d("B", "C"))
        close(d("A", "B"), d("A", "C"))
        incircle("I", "ABC")
        close(sol["circles"][0]["radius"], 2)
    elif n == 3:
        close(angle(p, "A", "C", "B"), 90)
        close(d("A", "C"), 8)
        close(d("A", "B"), 12)
        close(math.cos(math.radians(angle(p, "B", "A", "C"))), 2 / 3)
    elif n == 4:
        close(d("A", "C"), 4)
        close(d("B", "D"), 12)
        sides = [d(a, b) for a, b in zip("ABCD", "BCDA")]
        for side in sides:
            close(side, sides[0])
        area = abs(sum(p[a][0] * p[b][1] - p[a][1] * p[b][0] for a, b in zip("ABCD", "BCDA"))) / 2
        close(area, 24)
    elif n == 5:
        close(d("A", "B"), d("B", "C"))
        close(d("A", "C"), 6)
        close(math.sin(math.radians(angle(p, "A", "C", "B"))), 0.6)
        close(distance_line(p, "H", "A", "B"), 0)
        close(angle(p, "C", "H", "A"), 90)
        close(d("C", "H"), 3.6)
    elif n == 6:
        close(angle(p, "C", "A", "B"), 60)
        close(angle(p, "A", "B", "C"), 82)
        for v, h, a, b in [("A", "D", "B", "C"), ("B", "E", "A", "C"), ("C", "F", "A", "B")]:
            close(distance_line(p, h, a, b), 0)
            close(distance_line(p, "O", v, h), 0)
            u = [p[v][i] - p[h][i] for i in range(2)]
            w = [p[b][i] - p[a][i] for i in range(2)]
            close(sum(x * y for x, y in zip(u, w)), 0)
        close(angle(p, "A", "O", "F"), 82)
    elif n == 7:
        close(sum(d(a, b) for a, b in zip("ABCD", "BCDA")), 48)
        close((d("A", "B") + d("C", "D")) / 2, 19)
        close(d("B", "C"), 5)
        close(d("D", "A"), 5)
        for a in "ABCD":
            close(d("O", a), sol["circles"][0]["radius"])
    elif n == 8:
        close(angle(p, "A", "O", "B"), 70)
        close(angle(p, "O", "B", "C"), 90)
        close(angle(p, "A", "B", "C"), 35)
        close(d("O", "A"), d("O", "B"))
        assert ["B", "C"] in sol["lines"]
    elif n == 9:
        on("O", "A", "C")
        on("O", "B", "D")
        close(d("O", "A"), d("O", "C"))
        close(d("O", "B"), d("O", "D"))
        close(angle(p, "A", "C", "B"), 9)
        close(angle(p, "A", "O", "D"), 162)
    elif n == 10:
        close(angle(p, "A", "B", "C"), 105)
        close(angle(p, "B", "A", "C"), 15)
        close(angle(p, "A", "C", "B"), 60)
        for a in "ABC":
            close(d("O", a), sol["circles"][0]["radius"])
    elif n == 12:
        close(d("A", "B"), 5)
        close(d("B", "C"), 10)
        close(angle(p, "B", "A", "D"), 60)
        close(d("A", "M"), d("M", "C"))
        on("M", "B", "C")
        incircle("I", "AMD")
        close(distance_line(p, "I", "A", "C"), 0)
    elif n == 17:
        close(d("A", "C"), 4)
        close(angle(p, "A", "C", "B"), 90)
        on("M", "B", "C")
        close(d("C", "M"), d("A", "C"))
        close(d("B", "M"), d("A", "O"))
        incircle("O", "ABC")
        close(distance_line(p, "M", "B", "C"), 0)
        # O is inside ABC, not on its circumcircle.
        assert d("O", "A") > sol["circles"][0]["radius"]
    elif n == 18:
        close(d("A", "B"), 13)
        close(d("B", "C"), 7)
        close(d("B", "K"), 7 * math.sqrt(13) / 4)
        on("K", "A", "C")
        close(angle(p, "A", "B", "K"), angle(p, "K", "B", "C"))
    else:
        raise AssertionError("No independent oracle for this case")


class ExternalRegressions(unittest.TestCase):
    def test_supported_source_conditions(self):
        for n in SUPPORTED:
            with self.subTest(number=n):
                schema, _ = parse_hybrid(TASKS[n - 1]["text"], mode="rules")
                verify_case(n, schema, SympyGeometrySolver(schema).solve())

    def test_unsupported_not_false_success(self):
        for n in set(range(1, 21)) - set(SUPPORTED):
            with (
                self.subTest(number=n),
                self.assertRaisesRegex(ValueError, "не поддерживается|Не удалось сохранить"),
            ):
                parse_hybrid(TASKS[n - 1]["text"], mode="rules")

    def test_normalization(self):
        self.assertAlmostEqual(numeric_expression("7*sqrt(13)/4"), 7 * math.sqrt(13) / 4)
        self.assertIn("ACB", normalize_text("угол AСB прямой"))
        self.assertIn("0.666666", normalize_text("cos A = 2/3"))
        self.assertIn("AM=MC", normalize_text("A M=M C"))
        for source in ['__import__("os")', "2**100000", "sqrt(-1)", "1/0", "[1]", "True"]:
            with self.subTest(source=source), self.assertRaises((ValueError, SyntaxError)):
                numeric_expression(source)

    def test_no_proof_conclusion_in_givens(self):
        text = (
            "В треугольнике ABC AB = 5. а) Докажите, что AC = BC. б) Найдите площадь, если BC = 7."
        )
        schema, _ = parse_hybrid(text, mode="rules")
        self.assertFalse(any(c.type == "equal_segments" for c in schema.constraints))
        self.assertIn("BC = 7", given_text(text))

    def test_angle_not_segment(self):
        schema, _ = parse_hybrid("В параллелограмме ABCD AB=5, BC=10, угол BAD=60.", mode="rules")
        self.assertFalse(any(c.type == "distance" and c.value == 60 for c in schema.constraints))

    def test_corrupt_llm_value_rejected(self):
        schema = GeometrySchema(
            points=list("ABC"), constraints=[dict(type="cos", args=list("BAC"), value=0.2)]
        )
        with patch(
            "backend.llm_parser.requests.post",
            return_value=Mock(json=lambda: {"message": {"content": schema.model_dump_json()}}),
        ):
            with self.assertRaisesRegex(ValueError, "исказила"):
                parse_hybrid(TASKS[2]["text"], mode="ollama")

    def test_missing_llm_facts_transparently_restored(self):
        empty = GeometrySchema(points=list("ABC"))
        with patch(
            "backend.llm_parser.requests.post",
            return_value=Mock(json=lambda: {"message": {"content": empty.model_dump_json()}}),
        ):
            schema, engine = parse_hybrid(TASKS[2]["text"], mode="ollama")
        self.assertIn("конструкции правил", engine)
        verify_case(3, schema, SympyGeometrySolver(schema).solve())

    def test_radius_actually_constrains_incircle(self):
        schema, _ = parse_hybrid(TASKS[1]["text"], mode="rules")
        data = schema.model_dump()
        data["constraints"].append(dict(type="circle_radius", args=["I"], value=3))
        with self.assertRaises(ValueError):
            SympyGeometrySolver(GeometrySchema.model_validate(data)).solve(timeout=1)

    def test_changed_numbers_not_variant_lookup(self):
        text = TASKS[2]["text"].replace("8", "10").replace("2/3", "1/2")
        schema, _ = parse_hybrid(text, mode="rules")
        p = SympyGeometrySolver(schema).solve()["points"]
        self.assertAlmostEqual(math.dist(p["A"], p["B"]), 20, places=3)
