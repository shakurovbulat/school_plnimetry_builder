"""Offline regression tests: python -m unittest discover -s tests -v."""

import math
import unittest
from unittest.mock import Mock, patch

import requests
from fastapi.testclient import TestClient

from backend.main import app
from backend.models import GeometrySchema
from backend.sympy_solver import SympyGeometrySolver
from frontend.drawing import export_drawing


def triangle(extra=None):
    return GeometrySchema.model_validate(
        {
            "points": ["A", "B", "C"],
            "lines": [["A", "B"], ["B", "C"], ["C", "A"]],
            "figures": [{"type": "triangle", "name": "ABC", "points": ["A", "B", "C"]}],
            "constraints": extra
            or [
                {"type": "distance", "args": ["A", "B"], "value": 3},
                {"type": "distance", "args": ["B", "C"], "value": 4},
                {"type": "distance", "args": ["A", "C"], "value": 5},
            ],
        }
    )


class GeometryTests(unittest.TestCase):
    def test_highlight_escapes_html(self):
        from frontend.highlight import highlight_condition

        marked = highlight_condition("<script>alert(1)</script> AB = 3", triangle().model_dump())
        self.assertNotIn("<script>", marked)
        self.assertIn("&lt;script&gt;", marked)
        self.assertIn("<mark>AB</mark>", marked)

    def test_conflicting_relations_rejected(self):
        schema = GeometrySchema(
            points=list("ABCD"),
            lines=[list("AB"), list("CD")],
            constraints=[
                {"type": "parallel", "args": [list("AB"), list("CD")]},
                {"type": "perpendicular", "args": [list("AB"), list("CD")]},
            ],
        )
        with self.assertRaises(ValueError):
            SympyGeometrySolver(schema).solve(timeout=1)

    def test_all_rule_samples(self):
        from backend.check_samples import run_samples

        report = run_samples()
        self.assertEqual(len(report), 20)
        self.assertTrue(all(row["ok"] for row in report), str(report))

    def test_ratio_not_misread_as_length(self):
        from backend.llm_parser import parse_hybrid

        schema, _ = parse_hybrid(
            "В треугольнике ABC точка K на стороне AC. AK : KC = 2 : 3. AB = 10, BC = 12, AC = 15.",
            mode="rules",
        )
        self.assertFalse(
            any(c.type == "distance" and set(c.args) == {"K", "C"} for c in schema.constraints)
        )

    def test_streamlit_entrypoints(self):
        from streamlit.testing.v1 import AppTest

        for path in ("frontend/app.py",):
            from pathlib import Path

            view = AppTest.from_file(str(Path(__file__).resolve().parents[1] / path)).run()
            self.assertFalse(list(view.exception), path)

    def test_distances_independently(self):
        sol = SympyGeometrySolver(triangle()).solve()
        for a, b, d in [("A", "B", 3), ("B", "C", 4), ("A", "C", 5)]:
            self.assertAlmostEqual(math.dist(sol["points"][a], sol["points"][b]), d, places=4)

    def test_impossible_triangle(self):
        schema = triangle(
            [
                {"type": "distance", "args": a, "value": v}
                for a, v in [(["A", "B"], 1), (["B", "C"], 2), (["A", "C"], 5)]
            ]
        )
        with self.assertRaisesRegex(ValueError, "неравенство"):
            SympyGeometrySolver(schema).solve()

    def test_invalid_arguments(self):
        for c in [
            {"type": "distance", "args": [{}, {}], "value": 3},
            {"type": "distance", "args": ["A", "B"], "value": -1},
            {"type": "angle", "args": ["A", "B", "C"], "value": 180},
        ]:
            with self.assertRaises(ValueError):
                triangle([c])

    def test_midpoint_projection(self):
        schema = triangle().model_dump()
        schema["points"] += ["M", "H"]
        schema["constraints"] += [
            {"type": "midpoint", "args": ["M", "A", "C"]},
            {"type": "projection", "args": ["H", "B", "A", "C"]},
        ]
        sol = SympyGeometrySolver(GeometrySchema.model_validate(schema)).solve()
        p = sol["points"]
        for i in (0, 1):
            self.assertAlmostEqual(p["M"][i], (p["A"][i] + p["C"][i]) / 2, places=4)
        dot = sum((p["B"][i] - p["H"][i]) * (p["C"][i] - p["A"][i]) for i in (0, 1))
        self.assertAlmostEqual(dot, 0, places=4)

    def test_square_properties(self):
        s = GeometrySchema(
            points=list("ABCD"),
            figures=[{"type": "square", "name": "ABCD", "points": list("ABCD")}],
        )
        p = SympyGeometrySolver(s).solve()["points"]
        sides = [math.dist(p[a], p[b]) for a, b in zip("ABCD", "BCDA")]
        self.assertLess(max(sides) - min(sides), 1e-4)
        self.assertAlmostEqual(
            sum((p["A"][i] - p["B"][i]) * (p["C"][i] - p["B"][i]) for i in (0, 1)), 0, places=4
        )

    def test_circle(self):
        s = GeometrySchema(
            points=["O", "A", "B"],
            circles=[{"center": "O", "radius": 3, "passing_through": ["A", "B"]}],
        )
        sol = SympyGeometrySolver(s).solve()
        for n in ["A", "B"]:
            self.assertAlmostEqual(math.dist(sol["points"]["O"], sol["points"][n]), 3, places=4)
        self.assertEqual(sol["circles"][0]["radius"], 3)

    def test_export(self):
        sol = SympyGeometrySolver(triangle()).solve()
        sol["schema"] = triangle().model_dump()
        self.assertTrue(export_drawing(sol, "png").startswith(b"\x89PNG"))
        self.assertIn(b"<svg", export_drawing(sol, "svg"))


class ApiTests(unittest.TestCase):
    def setUp(self):
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool

        from backend.history import Base, History

        self.history = History.__new__(History)
        self.history.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.history.engine)
        self.history_patch = patch("backend.main.history_store", return_value=self.history)
        self.history_patch.start()
        self.addCleanup(self.history_patch.stop)
        self.addCleanup(self.history.engine.dispose)
        self.client = TestClient(app)

    def test_ollama_timeout(self):
        with patch("backend.llm_parser.requests.post", side_effect=requests.Timeout("timeout")):
            response = self.client.post("/solve", json={"text": "Треугольник ABC"})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("points", response.json())

    def test_unknown_point_edit(self):
        schema = triangle()
        points = SympyGeometrySolver(schema).solve()["points"]
        response = self.client.post(
            "/update-point",
            json={
                "schema_data": schema.model_dump(),
                "points": points,
                "point_name": "Z",
                "new_coords": [0, 0],
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_independent_sample_measurements(self):
        from backend.llm_parser import parse_hybrid
        from backend.sample_tasks import EXERCISES

        cases = [
            (6, [("A", "B", 6), ("O", "A", 5)]),
            (10, [("B", "C", 6), ("A", "D", 14), ("A", "B", 5)]),
            (18, [("A", "K", 6), ("K", "C", 9)]),
        ]
        for index, lengths in cases:
            schema, _ = parse_hybrid(list(EXERCISES.values())[index], mode="rules")
            points = SympyGeometrySolver(schema).solve()["points"]
            for a, b, value in lengths:
                self.assertAlmostEqual(math.dist(points[a], points[b]), value, places=3)

    def test_input(self):
        for text in [" ", "\x00", "a" * 6001]:
            self.assertEqual(self.client.post("/solve", json={"text": text}).status_code, 422)

    def test_rules(self):
        r = self.client.post(
            "/solve",
            json={"text": "В треугольнике ABC AB = 3, BC = 4, AC = 5.", "parser_mode": "rules"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["diagnostics"]["status"], "solved")

    @patch("backend.llm_parser.requests.post")
    def test_ollama_success(self, post):
        post.return_value = Mock(
            json=lambda: {"message": {"content": triangle().model_dump_json()}}
        )
        r = self.client.post("/solve", json={"text": "Треугольник ABC"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("Ollama", r.json()["parser_engine"])
        self.assertIsInstance(post.call_args.kwargs["json"]["format"], dict)

    @patch("backend.llm_parser.requests.post", side_effect=requests.ConnectionError("offline"))
    def test_ollama_unavailable(self, post):
        r = self.client.post("/solve", json={"text": "Треугольник ABC"})
        self.assertEqual(r.status_code, 503)
        self.assertNotIn("points", r.json())

    @patch("backend.llm_parser.requests.post")
    def test_ollama_invalid(self, post):
        post.return_value = Mock(json=lambda: {"message": {"content": "not JSON"}})
        r = self.client.post("/parse", json={"text": "Треугольник ABC"})
        self.assertEqual(r.status_code, 422)

    def test_history_roundtrip(self):
        response = self.client.post(
            "/solve", json={"text": "Треугольник ABC", "custom_schema": triangle().model_dump()}
        )
        self.assertEqual(response.status_code, 200, response.text)
        item_id = response.json()["history_id"]
        rows = self.client.get("/history").json()
        self.assertEqual(len(rows), 1)
        item = self.client.get(f"/history/{item_id}").json()
        self.assertEqual(item["result"]["points"], response.json()["points"])
        self.assertEqual(self.client.get("/history/999").status_code, 404)

    def test_export_api(self):
        schema = triangle()
        sol = SympyGeometrySolver(schema).solve()
        payload = {"schema_data": schema.model_dump(), "points": sol["points"]}
        png = self.client.post("/export/png", json=payload)
        self.assertEqual(png.status_code, 200, png.text[:100] if png.status_code != 200 else "")
        self.assertTrue(png.content.startswith(b"\x89PNG"))
        svg = self.client.post("/export/svg", json=payload)
        self.assertIn(b"<svg", svg.content)
        self.assertEqual(self.client.post("/export/jpg", json=payload).status_code, 422)
        payload["points"]["A"] = [100, 100]
        self.assertEqual(self.client.post("/export/png", json=payload).status_code, 422)

    def test_point_recompute(self):
        schema = triangle()
        sol = SympyGeometrySolver(schema).solve()
        desired = [sol["points"]["C"][0] + 1, sol["points"]["C"][1] + 2]
        r = self.client.post(
            "/update-point",
            json={
                "schema_data": schema.model_dump(),
                "points": sol["points"],
                "point_name": "C",
                "new_coords": desired,
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertLess(math.dist(r.json()["points"]["C"], desired), 1e-4)
        for a, b, d in [("A", "B", 3), ("B", "C", 4), ("A", "C", 5)]:
            self.assertAlmostEqual(
                math.dist(r.json()["points"][a], r.json()["points"][b]), d, places=4
            )


if __name__ == "__main__":
    unittest.main()
