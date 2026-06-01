from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.parser import parse_geometry_text
from backend.solver import build_geometry_schema


app = FastAPI(title="School Planimetry Builder API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TaskRequest(BaseModel):
    text: str = Field(min_length=1)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/parse")
async def parse_geometry_task(request: TaskRequest) -> dict:
    try:
        return {"status": "success", "parser_data": parse_geometry_text(request.text)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/solve")
async def solve_geometry_task(request: TaskRequest) -> dict:
    try:
        parsed_data = parse_geometry_text(request.text)
        schema_data = build_geometry_schema(parsed_data)
        return {
            "status": "success",
            "parser_data": parsed_data,
            "points": schema_data["points"],
            "lines": schema_data["lines"],
            "diagnostics": schema_data.get("diagnostics", {}),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
