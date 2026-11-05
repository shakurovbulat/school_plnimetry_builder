"""Regressions for constructions fixed during development."""

import unittest

import test_geometry

TASKS = {
    "Перпендикуляры": "В прямоугольном равнобедренном треугольнике ABC гипотенуза AB равна 14 см. Из точки F, принадлежащей отрезку AB, на катеты AC и BC соответственно опущены перпендикуляры FM и FN.",
    "Диагональ": "На диагонали BD параллелограмма ABCD отметили точки M и K так, что ∠BAM = ∠DCK (точка M лежит между точками B и K).",
    "Биссектриса": "Биссектриса угла D параллелограмма ABCD пересекает сторону BC в точке M, BM : MC = 3 : 4. AB = 15.",
    "Медиана и высота": "В треугольнике ABC проведена медиана BM и высота BH к стороне AC.",
}


class ConstructionFixTests(unittest.TestCase):
    setUp = test_geometry.ApiTests.setUp

    def test_fixed_constructions(self):
        for name, text in TASKS.items():
            with self.subTest(name=name):
                response = self.client.post("/solve", json={"text": text, "parser_mode": "rules"})
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertTrue(result["points"])
                self.assertLessEqual(
                    result["diagnostics"]["max_residual"], result["diagnostics"]["tolerance"]
                )


if __name__ == "__main__":
    unittest.main()
