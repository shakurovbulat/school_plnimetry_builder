"""Regression for a rhombus inscribed in an equilateral triangle."""

import math
import unittest

import test_geometry


class RhombusTests(unittest.TestCase):
    setUp = test_geometry.ApiTests.setUp

    def test_inscribed_rhombus(self):
        text = "В равносторонний треугольник ABC вписан ромб ADKM так, что точки D, K и M принадлежат соответственно сторонам AB, BC и AC. Периметр ромба равен 48 см."
        response = self.client.post("/solve", json={"text": text, "parser_mode": "rules"})
        self.assertEqual(response.status_code, 200, response.text)
        points = response.json()["points"]
        lengths = [math.dist(points[a], points[b]) for a, b in zip("ADKM", "DKMA")]
        self.assertAlmostEqual(sum(lengths), 48, places=3)
        self.assertLess(max(lengths) - min(lengths), 1e-3)


if __name__ == "__main__":
    unittest.main()
