from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Импортируем наши изолированные модули
from backend.parser import parse_geometry_text
from backend.solver import build_geometry_schema

app = FastAPI(title="Geometry Solver API")


class TaskRequest(BaseModel):
    text: str


@app.post("/solve")
async def solve_geometry_task(request: TaskRequest):
    print(f"📥 [FastAPI] Получен запрос на схему: {request.text}")
    try:
        # 1. Шаг парсера: вытаскиваем гео-объекты из текста
        parsed_data = parse_geometry_text(request.text)

        # 2. Шаг солвера: строим на основе этих объектов схему координат
        schema_data = build_geometry_schema(parsed_data)

        # Возвращаем всё собранное на фронтенд
        return {
            "status": "success",
            "parser_data": parsed_data,
            "points": schema_data["points"],
            "lines": schema_data["lines"]
        }
    except Exception as e:
        print(f"❌ Ошибка пайплайна: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)