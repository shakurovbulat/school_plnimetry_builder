"""End-to-end schema, solver and HTTP contract checks without Ollama."""

import unittest

import test_geometry

from backend.models import ConstraintType, GeometrySchema
from backend.sympy_solver import SympyGeometrySolver


class EndToEndTests(unittest.TestCase):
    setUp = test_geometry.ApiTests.setUp

    def test_schema_models(self):
        schema = GeometrySchema(
            points=["A", "B", "C"],
            lines=[["A", "B"], ["B", "C"], ["C", "A"]],
            constraints=[
                {"type": "distance", "args": ["A", "B"], "value": 5},
                {"type": "right_angle", "args": ["A", "C", "B"]},
            ],
        )
        self.assertEqual(len(schema.points), 3)
        self.assertEqual(schema.constraints[0].type, ConstraintType.DISTANCE)

    def test_sympy_solver(self):
        schema = GeometrySchema(
            points=["A", "B", "C"],
            lines=[["A", "B"], ["B", "C"], ["C", "A"]],
            constraints=[
                {"type": "distance", "args": ["A", "C"], "value": 3},
                {"type": "distance", "args": ["B", "C"], "value": 4},
                {"type": "right_angle", "args": ["A", "C", "B"]},
            ],
        )
        result = SympyGeometrySolver(schema).solve()
        self.assertEqual(set(result["points"]), set("ABC"))
        self.assertLess(result["diagnostics"]["max_residual"], SympyGeometrySolver.TOLERANCE)

    def test_api_endpoints(self):
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")
        self.assertIn("properties", self.client.get("/schema").json())
        parsed = self.client.post(
            "/parse",
            json={
                "text": "Треугольник ABC. AB = 5, BC = 6, AC = 7.",
                "parser_mode": "rules",
            },
        )
        self.assertEqual(parsed.status_code, 200, parsed.text)
        self.assertIn("schema", parsed.json())
        solved = self.client.post(
            "/solve",
            json={
                "text": "Прямоугольный равнобедренный треугольник ABC с гипотенузой AB = 10.",
                "parser_mode": "rules",
            },
        )
        self.assertEqual(solved.status_code, 200, solved.text)
        self.assertGreaterEqual(len(solved.json()["points"]), 3)
        self.assertTrue(solved.json()["lines"])


if __name__ == "__main__":
    unittest.main()
