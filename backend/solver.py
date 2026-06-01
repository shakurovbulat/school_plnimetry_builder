from __future__ import annotations

import math
from typing import Any

import numpy as np

try:
    from scipy.optimize import minimize
except Exception:  # pragma: no cover - exercised only when scipy is unavailable
    minimize = None


def _dist2(p1: np.ndarray, p2: np.ndarray) -> float:
    diff = p1 - p2
    return float(diff @ diff)


def _safe_points(parsed_data: dict[str, Any]) -> list[str]:
    points = parsed_data.get("points") or []
    if not points:
        points = ["A", "B", "C"]
    return sorted({str(point).upper() for point in points})


def _safe_lines(parsed_data: dict[str, Any], points: list[str]) -> list[list[str]]:
    lines: list[list[str]] = []
    for line in parsed_data.get("lines", []):
        if len(line) == 2 and line[0] in points and line[1] in points and line[0] != line[1]:
            candidate = [line[0], line[1]]
            reverse = [line[1], line[0]]
            if candidate not in lines and reverse not in lines:
                lines.append(candidate)
    return lines


def _initial_layout(points: list[str]) -> np.ndarray:
    count = max(len(points), 3)
    coords: list[float] = []
    for index in range(len(points)):
        angle = math.tau * index / count
        coords.extend([4.0 * math.cos(angle), 3.0 * math.sin(angle)])
    return np.array(coords, dtype=float)


def _fallback_layout(points: list[str], lines: list[list[str]]) -> dict[str, list[float]]:
    values = _initial_layout(points)
    return {
        point: [round(float(values[2 * index]), 2), round(float(values[2 * index + 1]), 2)]
        for index, point in enumerate(points)
    }


def _build_loss(points: list[str], constraints: list[dict[str, Any]]):
    index_by_point = {name: index for index, name in enumerate(points)}

    def point(values: np.ndarray, name: str) -> np.ndarray:
        index = index_by_point[name]
        return values[2 * index : 2 * index + 2]

    def has_all(names: list[str]) -> bool:
        return all(name in index_by_point for name in names)

    def loss(values: np.ndarray) -> float:
        total = 0.0

        # Fix translation and rotation enough to keep the optimizer stable.
        anchor = point(values, points[0])
        total += float(anchor @ anchor) * 20.0
        if len(points) > 1:
            second = point(values, points[1])
            total += second[1] ** 2

        for constraint in constraints:
            kind = constraint.get("type")
            args = constraint.get("args", [])

            if kind == "distance" and len(args) == 2 and has_all(args):
                actual = _dist2(point(values, args[0]), point(values, args[1]))
                expected = float(constraint.get("value", 0)) ** 2
                total += (actual - expected) ** 2

            elif kind == "equal_segments" and len(args) == 2:
                a, b = args
                if len(a) == 2 and len(b) == 2 and has_all(a + b):
                    total += (
                        _dist2(point(values, a[0]), point(values, a[1]))
                        - _dist2(point(values, b[0]), point(values, b[1]))
                    ) ** 2

            elif kind == "ratio" and len(args) == 2:
                a, b = args
                ratio = constraint.get("value", [1, 1])
                if len(a) == 2 and len(b) == 2 and has_all(a + b):
                    total += (
                        _dist2(point(values, a[0]), point(values, a[1])) * float(ratio[1]) ** 2
                        - _dist2(point(values, b[0]), point(values, b[1])) * float(ratio[0]) ** 2
                    ) ** 2

            elif kind == "right_angle" and len(args) == 3 and has_all(args):
                p1, vertex, p2 = [point(values, name) for name in args]
                total += float((p1 - vertex) @ (p2 - vertex)) ** 2

            elif kind == "perpendicular" and len(args) == 2:
                a, b = args
                if len(a) == 2 and len(b) == 2 and has_all(a + b):
                    v1 = point(values, a[1]) - point(values, a[0])
                    v2 = point(values, b[1]) - point(values, b[0])
                    total += float(v1 @ v2) ** 2

            elif kind == "parallel" and len(args) == 2:
                a, b = args
                if len(a) == 2 and len(b) == 2 and has_all(a + b):
                    v1 = point(values, a[1]) - point(values, a[0])
                    v2 = point(values, b[1]) - point(values, b[0])
                    cross = v1[0] * v2[1] - v1[1] * v2[0]
                    total += float(cross) ** 2

            elif kind == "point_on_segment" and len(args) == 3 and has_all(args):
                p, a, b = [point(values, name) for name in args]
                base = b - a
                length = float(base @ base)
                if length > 1e-9:
                    cross = (p[0] - a[0]) * base[1] - (p[1] - a[1]) * base[0]
                    t = float(((p - a) @ base) / length)
                    outside = max(0.0, -t, t - 1.0)
                    total += cross**2 + outside**2 * 25.0

        # Keep coincident points apart unless the input explicitly forces them.
        for i in range(len(points)):
            for j in range(i + 1, len(points)):
                d2 = _dist2(point(values, points[i]), point(values, points[j]))
                if d2 < 0.2:
                    total += (0.2 - d2) ** 2

        return float(total)

    return loss


def build_geometry_schema(parsed_data: dict[str, Any]) -> dict[str, Any]:
    points = _safe_points(parsed_data)
    lines = _safe_lines(parsed_data, points)
    constraints = parsed_data.get("constraints", [])

    if minimize is None:
        return {
            "points": _fallback_layout(points, lines),
            "lines": lines,
            "diagnostics": {
                "status": "fallback",
                "message": "SciPy is not installed; used a simple circular layout.",
                "loss": None,
            },
        }

    objective = _build_loss(points, constraints)
    best_result = None

    for seed in range(5):
        rng = np.random.default_rng(seed)
        start = _initial_layout(points) + rng.normal(0, 0.35, size=len(points) * 2)
        result = minimize(objective, start, method="L-BFGS-B", options={"maxiter": 2000, "ftol": 1e-10})
        if best_result is None or result.fun < best_result.fun:
            best_result = result

    assert best_result is not None
    values = best_result.x
    solved_points = {
        point: [round(float(values[2 * index]), 3), round(float(values[2 * index + 1]), 3)]
        for index, point in enumerate(points)
    }

    return {
        "points": solved_points,
        "lines": lines,
        "diagnostics": {
            "status": "solved" if best_result.success else "approximate",
            "message": str(best_result.message),
            "loss": round(float(best_result.fun), 8),
            "iterations": int(getattr(best_result, "nit", 0)),
        },
    }
