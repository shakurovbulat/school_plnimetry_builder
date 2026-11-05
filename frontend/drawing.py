"""Shared Matplotlib export (never runs a Streamlit application on import)."""

import io

import numpy as np
from matplotlib.figure import Figure
from matplotlib.patches import Arc, Circle


def render_drawing(solution):
    fig = Figure(figsize=(8, 7), dpi=150)
    ax = fig.subplots()
    points = {n: np.array(v) for n, v in solution["points"].items()}
    for a, b in solution["lines"]:
        ax.plot(*zip(points[a], points[b]), color="#1e40af", linewidth=1.8)
    for c in solution.get("circles", []):
        ax.add_patch(
            Circle(c["center_coords"], c["radius"], fill=False, color="#0284c7", linewidth=1.5)
        )
    span = max(np.ptp(np.array(list(points.values())), axis=0).max(), 1)
    for n, p in points.items():
        ax.plot(*p, "o", color="#2563eb", markersize=4)
        ax.annotate(n, p, xytext=(7, 7), textcoords="offset points", weight="bold")
    for c in solution.get("schema", {}).get("constraints", []):
        if c["type"] not in ("right_angle", "angle"):
            continue
        a, v, b = (points[n] for n in c["args"])
        u, w = a - v, b - v
        u, w = u / max(np.linalg.norm(u), 1e-12), w / max(np.linalg.norm(w), 1e-12)
        r = span * 0.04
        if c["type"] == "right_angle":
            q = np.array([v + u * r, v + (u + w) * r, v + w * r])
            ax.plot(q[:, 0], q[:, 1], color="#059669", linewidth=1)
        else:
            start, end = np.degrees(np.arctan2(u[1], u[0])), np.degrees(np.arctan2(w[1], w[0]))
            if (end - start) % 360 > 180:
                start, end = end, start
            ax.add_patch(Arc(v, r * 3, r * 3, theta1=start, theta2=end, color="#059669"))
    ax.relim()
    ax.autoscale_view()
    ax.margins(0.2)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.tight_layout()
    return fig


def export_drawing(solution, fmt):
    if fmt not in ("png", "svg"):
        raise ValueError("Неизвестный формат")
    fig = render_drawing(solution)
    buffer = io.BytesIO()
    fig.savefig(buffer, format=fmt, dpi=300, bbox_inches="tight")
    return buffer.getvalue()
