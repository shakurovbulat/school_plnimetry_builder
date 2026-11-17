"""Offline regression tests: python -m unittest discover -s tests -v."""

import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from streamlit.testing.v1 import AppTest

from backend.editing import delete_point_schema
from backend.main import PointDeleteRequest, delete_point
from backend.models import GeometrySchema


def sample():
    return GeometrySchema.model_validate({
        "points": ["A", "B", "C", "M"],
        "lines": [["A", "B"], ["B", "C"], ["C", "A"], ["A", "M"]],
        "figures": [{"type": "triangle", "name": "ABC", "points": ["A", "B", "C"]}],
        "constraints": [
            {"type": "distance", "args": ["A", "B"], "value": 3},
            {"type": "distance", "args": ["B", "C"], "value": 5},
            {"type": "distance", "args": ["C", "A"], "value": 4},
            {"type": "midpoint", "args": ["M", "B", "C"]},
            {"type": "equal_segments", "args": [["B", "M"], ["M", "C"]]},
        ],
        "givens": [{"text": "M — середина BC"}, {"text": "AB = 3"}],
        "targets": [{"object": "AM"}, {"object": "AB"}],
    })


POINTS = {"A": [0, 0], "B": [3, 0], "C": [0, 4], "M": [1.5, 2]}


class DeletionTests(unittest.TestCase):
    def test_midpoint_removal_preserves_triangle(self):
        schema = sample()
        result = delete_point(PointDeleteRequest(schema_data=schema, points=POINTS, point_name="M"))
        self.assertEqual(set(result["points"]), {"A", "B", "C"})
        self.assertEqual(len(result["figures"]), 1)
        self.assertNotIn(["A", "M"], result["lines"])
        self.assertEqual(len(result["schema"]["constraints"]), 3)
        self.assertEqual(result["schema"]["targets"], [{"object": "AB"}])
        self.assertEqual(result["schema"]["givens"], [{"text": "AB = 3"}])
        self.assertEqual(len(schema.points), 4)  # immutable preview
        self.assertLessEqual(result["diagnostics"]["max_residual"], 2e-5)

    def test_vertex_removes_figure(self):
        schema, removed = delete_point_schema(sample(), "A")
        self.assertEqual(schema.figures, [])
        self.assertEqual(len(removed["figures"]), 1)
        self.assertEqual(schema.lines, [["B", "C"]])

    def test_circle_dependency_cleanup(self):
        schema = GeometrySchema.model_validate({
            "points": ["O", "A", "B"],
            "circles": [{"name": "omega", "center": "O", "radius": 2, "passing_through": ["A"]}],
            "constraints": [
                {"type": "circle_radius", "args": ["O"], "value": 2},
                {"type": "point_on_circle", "args": ["B", "O"]},
                {"type": "distance", "args": ["O", "B"], "value": 2},
            ],
            "targets": [{"object": "omega"}],
        })
        updated, _ = delete_point_schema(schema, "A")
        self.assertEqual(updated.circles, [])
        self.assertEqual([c.type.value for c in updated.constraints], ["distance"])
        self.assertEqual(updated.targets, [])

    def test_indexed_point_names(self):
        schema = GeometrySchema(points=["A", "A1", "B"], targets=[{"object": "A1B"}, {"object": "AB"}])
        updated, _ = delete_point_schema(schema, "A")
        self.assertEqual(updated.targets, [{"object": "A1B"}])

    def test_invalid_requests(self):
        for schema, points, name in [
            (sample(), POINTS, "Z"),
            (GeometrySchema(points=["A"]), {"A": [0, 0]}, "A"),
            (sample(), {**POINTS, "M": [100, 100]}, "M"),
        ]:
            with self.assertRaises(HTTPException) as error:
                delete_point(PointDeleteRequest(schema_data=schema, points=points, point_name=name))
            self.assertEqual(error.exception.status_code, 422)

    def test_two_point_free_drawing_can_be_recomputed(self):
        result = delete_point(PointDeleteRequest(
            schema_data=GeometrySchema(points=["A", "B", "M"]),
            points={"A": [0, 0], "B": [2, 0], "M": [1, 1]}, point_name="M",
        ))
        self.assertEqual(set(result["points"]), {"A", "B"})
        self.assertLessEqual(result["diagnostics"]["max_residual"], 2e-5)

    @patch("frontend.drawing.export_drawing", return_value=b"image")
    def test_ui_cancel_and_confirm(self, _export):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "frontend/app.py"))
        app.session_state["solution"] = {
            "schema": sample().model_dump(mode="json"), "points": POINTS,
            "lines": sample().lines, "figures": [], "circles": [], "warnings": [],
        }
        app.session_state["solution_text"] = "test"
        app.session_state["task_text"] = "test"
        app.run(timeout=20)
        self.assertEqual(len(app.exception), 0)
        app.button(key="delete-0-M").click().run()
        self.assertTrue(any("Удалить точку M" in w.value for w in app.warning))
        app.button(key="cancel-delete-0").click().run()
        self.assertIn("M", app.session_state["solution"]["points"])
        app.button(key="delete-0-M").click().run()
        with patch("requests.post") as post:
            post.return_value.ok = False
            post.return_value.json.return_value = {"detail": "Ошибка пересчёта"}
            app.button(key="confirm-delete-0").click().run()
        self.assertIn("M", app.session_state["solution"]["points"])
        self.assertTrue(any("сохранён прежний чертёж" in e.value for e in app.error))
        response = delete_point(PointDeleteRequest(schema_data=sample(), points=POINTS, point_name="M"))
        with patch("requests.post") as post:
            post.return_value.ok = True
            post.return_value.json.return_value = response
            app.button(key="confirm-delete-0").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertNotIn("M", app.session_state["solution"]["points"])
        self.assertEqual(app.session_state["drawing_version"], 1)


if __name__ == "__main__":
    unittest.main()
