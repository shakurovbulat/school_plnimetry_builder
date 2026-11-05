"""API regressions for all built-in examples."""

import unittest

import test_geometry

from backend.sample_tasks import EXERCISES


class SampleApiTests(unittest.TestCase):
    setUp = test_geometry.ApiTests.setUp

    def test_sample_requests(self):
        for title, text in EXERCISES.items():
            with self.subTest(title=title):
                response = self.client.post("/solve", json={"text": text, "parser_mode": "rules"})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["diagnostics"]["status"], "solved")


if __name__ == "__main__":
    unittest.main()
