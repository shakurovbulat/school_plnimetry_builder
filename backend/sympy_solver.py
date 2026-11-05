"""Constraint-based numerical geometry with independently reported residuals.

SymPy is used for exact elementary constructions; SciPy solves the remaining
system. No aesthetic objective is used as evidence of geometric correctness.
"""

from __future__ import annotations

import math
import time
from typing import Any

import numpy as np
import sympy as sp
from scipy.optimize import least_squares

from backend.models import Constraint, GeometrySchema


class GeometryError(ValueError):
    pass


class SympyGeometrySolver:
    TOLERANCE = 2e-5

    def __init__(self, schema: GeometrySchema):
        self.schema = schema
        self.names = list(schema.points)
        if not self.names:
            raise GeometryError("Не удалось распознать геометрические фигуры на чертеже")
        self.index = {p: i for i, p in enumerate(self.names)}
        self.constraints = list(schema.constraints)
        self._expand_figures()
        self.scale = max(
            [
                float(c.value)
                for c in self.constraints
                if c.type == "distance" and isinstance(c.value, (int, float))
            ]
            + [5.0]
        )
        self._check_triangle_inequalities()

    def _add(self, kind, args, value=None):
        c = Constraint(type=kind, args=args, value=value)
        if c not in self.constraints:
            self.constraints.append(c)

    def _expand_figures(self):
        for f in self.schema.figures:
            p = f.points
            t = f.type.value
            expected = (
                3
                if "triangle" in t
                else 4
                if t
                in {"quadrilateral", "parallelogram", "rectangle", "square", "rhombus", "trapezoid"}
                else None
            )
            if expected and len(p) != expected:
                raise GeometryError(f"{f.name}: требуется {expected} различных вершин")
            if t in {"parallelogram", "rectangle", "square", "rhombus"}:
                self._add("parallel", [p[:2], p[2:]])
                self._add("parallel", [p[1:3], [p[3], p[0]]])
                self._add("equal_segments", [p[:2], p[2:]])
                self._add("equal_segments", [p[1:3], [p[3], p[0]]])
            if t in {"rectangle", "square"}:
                self._add("right_angle", [p[0], p[1], p[2]])
            if t in {"square", "rhombus"}:
                self._add("equal_segments", [p[:2], p[1:3]])
            if t == "trapezoid" and not any(c.type == "parallel" for c in self.constraints):
                self._add("parallel", [p[:2], p[2:]])
            if t == "equilateral_triangle":
                self._add("equal_segments", [p[:2], p[1:3]])
                self._add("equal_segments", [p[:2], [p[0], p[2]]])
            if t == "isosceles_triangle":
                self._add("equal_segments", [[p[0], p[2]], [p[1], p[2]]])
            if t == "right_triangle" and not any(
                c.type == "right_angle" and set(c.args) == set(p) for c in self.constraints
            ):
                # Documented convention: the last vertex is the right-angle vertex.
                self._add("right_angle", [p[0], p[2], p[1]])
        for circle in self.schema.circles:
            for point in circle.passing_through:
                self._add("point_on_circle", [point, circle.center])

    def _check_triangle_inequalities(self):
        lengths = {}
        for c in self.constraints:
            if c.type == "distance":
                key = frozenset(c.args)
                if key in lengths and not math.isclose(lengths[key], c.value):
                    raise GeometryError("Противоречивые длины одного отрезка")
                lengths[key] = c.value
        for f in self.schema.figures:
            if len(f.points) == 3:
                a, b, c = f.points
                sides = [lengths.get(frozenset(s)) for s in [(a, b), (b, c), (c, a)]]
                if all(v is not None for v in sides) and 2 * max(sides) >= sum(sides):
                    raise GeometryError(
                        "Фигура с заданными свойствами не существует: нарушено неравенство треугольника"
                    )

    @staticmethod
    def _cross(a, b):
        return float(a[0] * b[1] - a[1] * b[0])

    @staticmethod
    def _norm(v):
        return max(float(np.linalg.norm(v)), 1e-10)

    def _cos(self, p, args):
        a, v, b = (p[n] for n in args)
        u, w = a - v, b - v
        return float(np.dot(u, w) / (self._norm(u) * self._norm(w)))

    def _circle_radius(self, p, center):
        for c in self.constraints:
            if c.type == "circle_radius" and c.args == [center]:
                return float(c.value)
        for circ in self.schema.circles:
            if circ.center == center:
                if circ.radius is not None:
                    return circ.radius
                if circ.passing_through:
                    return self._norm(p[circ.passing_through[0]] - p[center])
        for c in self.constraints:
            if c.type == "circumscribed_circle" and c.args[0] == center:
                return self._norm(p[c.args[1]] - p[center])
            if c.type in ("inscribed_circle", "inscribed_polygon") and c.args[0] == center:
                a, b = p[c.args[1]], p[c.args[2]]
                return abs(self._cross(b - a, p[center] - a)) / self._norm(b - a)
        raise GeometryError(f"Для окружности {center} задайте радиус или точку на ней")

    def _residual(self, p, c):
        a, t, v, s = c.args, c.type.value, c.value, self.scale
        vec = lambda pair: p[pair[1]] - p[pair[0]]
        length = lambda pair: self._norm(vec(pair))
        if t == "distance":
            return [(length(a) - v) / s]
        if t == "equal_segments":
            return [(length(a[0]) - length(a[1])) / s]
        if t == "segment_sum":
            return [(length(a[0]) + length(a[1]) - v) / s]
        if t == "segment_difference":
            return [max(0, v - length(a[0]) + length(a[1])) / s]
        if t == "ratio":
            return [(length(a[0]) * v[1] - length(a[1]) * v[0]) / (s * max(v))]
        if t in {"angle", "right_angle", "sin", "cos", "tg"}:
            cosine = self._cos(p, a)
            if t == "right_angle":
                return [cosine]
            if t == "angle":
                return [cosine - math.cos(math.radians(v))]
            if t == "cos":
                return [cosine - v]
            sine = math.sqrt(max(0, 1 - cosine * cosine))
            return [sine - v] if t == "sin" else [sine - v * cosine]
        if t == "equal_angles":
            return [self._cos(p, a[0]) - self._cos(p, a[1])]
        if t in {"parallel", "perpendicular"}:
            u, w = vec(a[0]), vec(a[1])
            denom = self._norm(u) * self._norm(w)
            return [self._cross(u, w) / denom if t == "parallel" else float(np.dot(u, w)) / denom]
        if t == "midpoint":
            return list((p[a[0]] - (p[a[1]] + p[a[2]]) / 2) / s)
        if t in {"point_on_segment", "point_on_line", "point_between", "collinear"}:
            q, start, end = (p[n] for n in a)
            u = end - start
            result = [self._cross(u, q - start) / (self._norm(u) * s)]
            if t in {"point_on_segment", "point_between"}:
                fraction = float(np.dot(q - start, u)) / max(float(np.dot(u, u)), 1e-15)
                margin = 0.001 if t == "point_between" else 0
                result.extend([max(0, margin - fraction), max(0, fraction - 1 + margin)])
            return result
        if t == "projection":
            h, q, start, end = (p[n] for n in a)
            u = end - start
            return [
                self._cross(u, h - start) / (self._norm(u) * s),
                float(np.dot(q - h, u)) / (self._norm(u) * s),
            ]
        if t == "distinct":
            return [max(0, 0.02 - length(a) / s)]
        if t in ("product_equal", "ratio_equal"):
            # Four segments: ab*cd=ef*gh, or ab/cd=ef/gh.
            x, y, z, w = [length(pair) for pair in a]
            return (
                [(x * y - z * w) / (s * s)] if t == "product_equal" else [(x * w - z * y) / (s * s)]
            )
        if t == "inside_triangle":
            q, x, y, z = (p[n] for n in a)
            edge_cross = self._cross(y - x, z - x)
            sign = 1 if edge_cross >= 0 else -1
            return [
                max(0, 0.001 - sign * self._cross(p[v] - p[u], q - p[u]) / (s * s))
                for u, v in zip(a[1:], a[2:] + a[1:2])
            ]
        if t == "tangent":
            # [centre, contact, other point on the tangent line].
            o, h, q = (p[n] for n in a)
            return [
                (self._norm(h - o) - self._circle_radius(p, a[0])) / s,
                float(np.dot(h - o, q - h)) / (self._norm(h - o) * self._norm(q - h)),
            ]
        if t == "external_tangency":
            o, k, h = a
            r1, r2 = self._circle_radius(p, o), self._circle_radius(p, k)
            return [
                (self._norm(p[o] - p[k]) - r1 - r2) / s,
                (self._norm(p[h] - p[o]) - r1) / s,
                (self._norm(p[h] - p[k]) - r2) / s,
                self._cross(p[k] - p[o], p[h] - p[o]) / (self._norm(p[k] - p[o]) * s),
            ]
        if t == "acute_angle":
            return [max(0, 0.001 - self._cos(p, a))]
        if t == "obtuse_angle":
            return [max(0, self._cos(p, a) + 0.001)]
        if t == "external_bisector":
            vertex, foot, left, right = (p[n] for n in a)
            u, w, ray = left - vertex, right - vertex, foot - vertex
            direction = u / self._norm(u) - w / self._norm(w)
            return [self._cross(direction, ray) / (self._norm(direction) * s)]
        if t == "bisector":
            # Canonical convention shared with rule parser: [vertex, foot, sideA, sideB].
            vertex, foot, left, right = (p[n] for n in a)
            u, w, ray = left - vertex, right - vertex, foot - vertex
            direction = u / self._norm(u) + w / self._norm(w)
            return [
                self._cross(direction, ray) / (self._norm(direction) * s),
                max(0, -float(np.dot(direction, ray))) / s,
            ]
        if t == "circumscribed_circle":
            center, *vertices = a
            lengths = [self._norm(p[n] - p[center]) for n in vertices]
            return [(d - lengths[0]) / s for d in lengths[1:]]
        if t in ("inscribed_circle", "inscribed_polygon"):
            center, *vertices = a
            signed = [
                self._cross(p[b] - p[q], p[center] - p[q]) / self._norm(p[b] - p[q])
                for q, b in zip(vertices, vertices[1:] + vertices[:1])
            ]
            residuals = [(signed[i] - signed[0]) / s for i in range(1, len(signed))]
            # Tangency must occur on each side, not its extension. Equal signed
            # distances alone also admit concave/excentral configurations.
            for q, b in zip(vertices, vertices[1:] + vertices[:1]):
                edge = p[b] - p[q]
                fraction = float(np.dot(p[center] - p[q], edge)) / max(
                    float(np.dot(edge, edge)), 1e-15
                )
                residuals.extend([max(0, -fraction), max(0, fraction - 1)])
            return residuals
        if t == "point_on_circle":
            return [(self._norm(p[a[0]] - p[a[1]]) - self._circle_radius(p, a[1])) / s]
        if t == "perimeter":
            return [(sum(length([a[i], a[(i + 1) % len(a)]]) for i in range(len(a))) - v) / s]
        if t == "circle_radius":
            center = a[0]
            circles = [c for c in self.schema.circles if c.center == center]
            if not circles:
                raise GeometryError("Для circle_radius требуется окружность с этим центром")
            circle = circles[0]
            residuals = []
            if circle.radius is not None:
                residuals.append((circle.radius - v) / s)
            residuals.extend((self._norm(p[n] - p[center]) - v) / s for n in circle.passing_through)
            for c in self.constraints:
                if c.type in ("inscribed_circle", "inscribed_polygon") and c.args[0] == center:
                    x, y = c.args[1:3]
                    r = abs(self._cross(p[y] - p[x], p[center] - p[x])) / self._norm(p[y] - p[x])
                    residuals.append((r - v) / s)
                if c.type == "circumscribed_circle" and c.args[0] == center:
                    residuals.extend((self._norm(p[n] - p[center]) - v) / s for n in c.args[1:])
            if not residuals:
                raise GeometryError("Радиус не связан с геометрией окружности")
            return residuals
        raise GeometryError(f"Ограничение {t} пока не поддерживается. Уточните схему.")

    def _nondegenerate(self, p):
        out = []
        # Zero-length referenced segments cannot satisfy relations by collapse.
        segments = list(self.schema.lines)
        for c in self.constraints:
            if c.type in {
                "parallel",
                "perpendicular",
                "equal_segments",
                "ratio",
                "segment_sum",
                "segment_difference",
            }:
                segments.extend(c.args)
            if c.type in {"product_equal", "ratio_equal"}:
                segments.extend(c.args)
            if c.type == "distinct":
                segments.append(c.args)
            if c.type == "tangent":
                segments.extend([c.args[:2], c.args[1:]])
            if c.type in {"bisector", "external_bisector"}:
                vertex, foot, left, right = c.args
                segments.extend([[vertex, foot], [vertex, left], [vertex, right]])
            if c.type in {
                "angle",
                "right_angle",
                "sin",
                "cos",
                "tg",
                "acute_angle",
                "obtuse_angle",
            }:
                segments.extend([[c.args[0], c.args[1]], [c.args[1], c.args[2]]])
            if c.type in {"point_on_segment", "point_on_line", "point_between", "collinear"}:
                segments.append(c.args[1:3])
            if c.type == "projection":
                segments.append(c.args[2:4])
        for line in segments:
            out.append(max(0, 0.001 - self._norm(p[line[0]] - p[line[1]]) / self.scale))
        for f in self.schema.figures:
            if len(f.points) >= 3:
                vertices = [p[n] for n in f.points]
                for i in range(len(vertices)):
                    u = vertices[i - 1] - vertices[i]
                    w = vertices[(i + 1) % len(vertices)] - vertices[i]
                    sine = abs(self._cross(u, w)) / (self._norm(u) * self._norm(w))
                    out.append(max(0, 0.002 - sine))
            # Unknown-size circles still need a positive, drawable radius.
            # No explicit radius does not mean the geometry is contradictory.
        for circle in self.schema.circles:
            out.append(max(0, 0.01 - self._circle_radius(p, circle.center) / self.scale))
        return out

    def validate_points(self, points):
        if set(points) != set(self.names):
            raise GeometryError("Набор координат не совпадает с точками схемы")
        p = {}
        for name, value in points.items():
            arr = np.asarray(value, dtype=float)
            if arr.shape != (2,) or not np.isfinite(arr).all() or np.max(np.abs(arr)) > 1e6:
                raise GeometryError(
                    "Координаты должны быть конечными парами чисел в пределах ±1000000"
                )
            p[name] = arr
        residuals = [
            {
                "type": c.type.value,
                "args": c.args,
                "error": max(map(abs, self._residual(p, c)), default=0),
            }
            for c in self.constraints
        ]
        maximum = max([r["error"] for r in residuals] + self._nondegenerate(p) + [0])
        return maximum, residuals

    def _initial_positions(self):
        p = {
            n: np.array(
                [
                    self.scale * 0.7 * math.cos(i * 2 * math.pi / max(3, len(self.names))),
                    self.scale * 0.7 * math.sin(i * 2 * math.pi / max(3, len(self.names))),
                ]
            )
            for i, n in enumerate(self.names)
        }
        for f in self.schema.figures:
            if len(f.points) >= 3:
                for i, n in enumerate(f.points):
                    angle = i * 2 * math.pi / len(f.points)
                    p[n] = self.scale * np.array([math.cos(angle), math.sin(angle)]) * 0.6
        for c in self.constraints:
            if c.type == "midpoint":
                m, a, b = c.args
                exact = sp.Segment(sp.Point(*p[a]), sp.Point(*p[b])).midpoint
                p[m] = np.array([float(exact.x), float(exact.y)])
            if c.type == "point_on_segment":
                m, a, b = c.args
                p[m] = (p[a] + p[b]) / 2
        return p

    def solve(self, initial_points=None, fixed_points=None, timeout=12.0) -> dict[str, Any]:
        started = time.monotonic()
        base = (
            self._initial_positions()
            if initial_points is None
            else {n: np.array(initial_points[n], dtype=float) for n in self.names}
        )
        fixed = {n: np.array(v, dtype=float) for n, v in (fixed_points or {}).items()}
        if not set(fixed) <= set(self.names):
            raise GeometryError("Неизвестная редактируемая точка")
        # Fix translation/rotation only on a fresh drawing. Edits retain world coordinates.
        anchor = not fixed and initial_points is None

        def unpack(x):
            return {n: x[2 * i : 2 * i + 2] * self.scale for i, n in enumerate(self.names)}

        def fun(x):
            if time.monotonic() - started > timeout:
                raise TimeoutError("Истекло время геометрического расчёта")
            p = unpack(x)
            out = [r for c in self.constraints for r in self._residual(p, c)]
            out.extend(self._nondegenerate(p))
            for n, v in fixed.items():
                out.extend((p[n] - v) / self.scale)
            if anchor:
                out.extend(p[self.names[0]] / self.scale)
                if len(self.names) > 1:
                    out.append(p[self.names[1]][1] / self.scale)
            # Keep genuinely free drawings at a useful scale, not a collapsed zero solution.
            if (
                not any(
                    c.type in {"distance", "perimeter", "circle_radius"} for c in self.constraints
                )
                and not any(c.radius is not None for c in self.schema.circles)
                and len(self.names) > 1
            ):
                out.append(
                    (self._norm(p[self.names[1]] - p[self.names[0]]) - self.scale) / self.scale
                )
            return np.asarray(out or [0.0])

        best, best_error, iterations = None, float("inf"), 0
        seed = np.concatenate([base[n] / self.scale for n in self.names])
        # Fail early on unsupported constraints, rather than returning successful geometry.
        fun(seed)
        for attempt in range(6):
            start = (
                seed
                if attempt == 0
                else seed + np.random.default_rng(attempt).normal(0, 0.5, seed.shape)
            )
            try:
                result = least_squares(fun, start, max_nfev=600, ftol=1e-11, xtol=1e-11, gtol=1e-11)
            except TimeoutError:
                break
            coords = {n: list(map(float, v)) for n, v in unpack(result.x).items()}
            error, residuals = self.validate_points(coords)
            pin_error = max(
                [self._norm(np.array(coords[n]) - v) / self.scale for n, v in fixed.items()] + [0]
            )
            error = max(error, pin_error)
            if error < best_error:
                best, best_error, iterations = coords, error, result.nfev
            if error < self.TOLERANCE:
                break
        if best is None or best_error > self.TOLERANCE:
            raise GeometryError(
                "Не удалось построить невырожденную фигуру с заданными свойствами. Условия противоречивы или требуют уточнения."
            )
        _, residuals = self.validate_points(best)
        circles = []
        p = {n: np.array(v) for n, v in best.items()}
        for c in self.schema.circles:
            circles.append(
                {
                    **c.model_dump(),
                    "center_coords": best[c.center],
                    "radius": self._circle_radius(p, c.center),
                }
            )
        lines = list(self.schema.lines)
        for f in self.schema.figures:
            if len(f.points) >= 3:
                for i, a in enumerate(f.points):
                    pair = [a, f.points[(i + 1) % len(f.points)]]
                    if pair not in lines and pair[::-1] not in lines:
                        lines.append(pair)
        return {
            "points": best,
            "lines": lines,
            "circles": circles,
            "figures": [f.model_dump() for f in self.schema.figures],
            "diagnostics": {
                "status": "solved",
                "method": "numerical least_squares",
                "loss": best_error**2,
                "max_residual": best_error,
                "tolerance": self.TOLERANCE,
                "residuals": residuals,
                "iterations": iterations,
                "constraints_count": len(self.constraints),
                "seconds": round(time.monotonic() - started, 3),
            },
        }
