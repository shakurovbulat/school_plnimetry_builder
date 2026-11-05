from __future__ import annotations

import logging
import time
from functools import lru_cache

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from backend.llm_parser import get_llm_json_schema, parse_hybrid
from backend.models import GeometrySchema
from backend.sympy_solver import SympyGeometrySolver

logger = logging.getLogger(__name__)

app = FastAPI(
    title="School Planimetry Builder API",
    version="1.0.0",
    description="LLM -> JSON Schema -> Pydantic -> SymPy pipeline for school geometry problem drawings",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8501", "http://localhost:8501"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TaskRequest(BaseModel):
    text: str = Field(min_length=1, max_length=6000, description="Planimetry problem formulation")
    custom_schema: GeometrySchema | None = Field(
        default=None, description="Optional pre-modified or direct GeometrySchema"
    )
    parser_mode: str | None = Field(default=None, pattern="^(ollama|rules)$")
    model: str | None = Field(default=None, description="Custom LLM Model Name")

    @field_validator("text")
    @classmethod
    def validate_text(cls, text):
        text = text.strip()
        if not text:
            raise ValueError("Поле ввода не может быть пустым")
        if any(ord(c) < 32 and c not in "\n\r\t" for c in text):
            raise ValueError("Недопустимые управляющие символы")
        return text


class DrawingRequest(BaseModel):
    schema_data: GeometrySchema
    points: dict[str, list[float]]


class PointUpdateRequest(DrawingRequest):
    point_name: str
    new_coords: list[float] = Field(min_length=2, max_length=2)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "engine": "SymPy + Pydantic + LLM/Heuristic"}


@app.get("/ollama")
def local_model_status():
    from backend.llm_parser import ollama_status

    return ollama_status()


@app.get("/schema")
def schema_spec() -> dict:
    """Returns the JSON Schema of GeometrySchema for LLM and external clients."""
    return get_llm_json_schema()


@app.post("/parse")
def parse_geometry_task(request: TaskRequest) -> dict:
    try:
        schema, parser_engine = parse_hybrid(
            request.text,
            mode=request.parser_mode,
            model=request.model,
        )
        return {
            "status": "success",
            "schema": schema.model_dump(),
            "parser_engine": parser_engine,
        }
    except Exception as exc:
        logger.exception("Parse error")
        raise HTTPException(
            status_code=503 if isinstance(exc, RuntimeError) else 422, detail=str(exc)
        ) from exc


@app.post("/solve")
def solve_geometry_task(request: TaskRequest) -> dict:
    parser_engine = "Custom Schema"
    started = time.perf_counter()
    try:
        if request.custom_schema is not None:
            schema = request.custom_schema
        else:
            schema, parser_engine = parse_hybrid(
                request.text,
                mode=request.parser_mode,
                model=request.model,
            )

        parsed_at = time.perf_counter()
        solver = SympyGeometrySolver(schema)
        solution = solver.solve()
        solution["diagnostics"]["parse_seconds"] = round(parsed_at - started, 3)
        solution["diagnostics"]["total_seconds"] = round(time.perf_counter() - started, 3)

        result = {
            "status": "success",
            "parser_engine": parser_engine,
            "schema": schema.model_dump(),
            "points": solution["points"],
            "lines": solution["lines"],
            "circles": solution["circles"],
            "figures": solution["figures"],
            "diagnostics": solution["diagnostics"],
        }
        if any(
            c.type
            in (
                "distinct",
                "product_equal",
                "ratio_equal",
                "acute_angle",
                "inside_triangle",
                "external_tangency",
                "tangent",
            )
            for c in schema.constraints
        ):
            result["warnings"] = [
                "Построен один допустимый экземпляр исходных данных, не доказательство утверждения. "
                "При свободных параметрах другие экземпляры могут выглядеть иначе. "
                "Если прямая имеет два пересечения с окружностью, выбор ветви не считается единственным; "
                "дополнительная ветвь при наличии обозначена индексом 1."
            ]
        try:
            result["history_id"] = history_store().save(request.text, result)
        except Exception:
            logger.exception("History write failed")
            result.setdefault("warnings", []).append(
                "Не удалось сохранить историю; чертёж доступен для экспорта."
            )
        return result
    except Exception as exc:
        logger.exception("Solve error: %s", exc)
        raise HTTPException(
            status_code=503 if isinstance(exc, RuntimeError) else 422, detail=str(exc)
        ) from exc


@app.post("/update-point")
def update_point(request: PointUpdateRequest):
    try:
        solver = SympyGeometrySolver(request.schema_data)
        error, _ = solver.validate_points(request.points)
        if error > solver.TOLERANCE:
            raise ValueError("Исходный чертёж нарушает ограничения")
        if request.point_name not in request.points:
            raise ValueError("Неизвестная точка")
        import math

        if not all(math.isfinite(v) and abs(v) <= 1e6 for v in request.new_coords):
            raise ValueError("Некорректные координаты")
        # Only the dragged vertex is pinned; dependent geometry is recomputed.
        result = solver.solve(
            initial_points=request.points, fixed_points={request.point_name: request.new_coords}
        )
        return {"status": "success", "schema": request.schema_data.model_dump(), **result}
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc


@lru_cache(maxsize=1)
def history_store():
    from backend.history import History

    return History()


@app.get("/history")
def list_history():
    return history_store().list()


@app.get("/history/{item_id}")
def get_history(item_id: int):
    item = history_store().get(item_id)
    if item is None:
        raise HTTPException(404, detail="Чертёж не найден")
    return item


@app.post("/export/{fmt}")
def export_points(fmt: str, request: DrawingRequest):
    if fmt not in ("png", "svg"):
        raise HTTPException(422, detail="Формат должен быть png или svg")
    try:
        solver = SympyGeometrySolver(request.schema_data)
        error, _ = solver.validate_points(request.points)
        if error > solver.TOLERANCE:
            raise ValueError("Нельзя экспортировать чертёж с нарушенными ограничениями")
        import numpy as np

        from frontend.drawing import export_drawing

        coords = {n: np.array(v) for n, v in request.points.items()}
        solution = {
            "points": request.points,
            "lines": request.schema_data.lines,
            "circles": [
                {
                    **c.model_dump(),
                    "center_coords": request.points[c.center],
                    "radius": solver._circle_radius(coords, c.center),
                }
                for c in request.schema_data.circles
            ],
            "schema": request.schema_data.model_dump(),
        }
        data = export_drawing(solution, fmt)
        return Response(data, media_type="image/png" if fmt == "png" else "image/svg+xml")
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000)
