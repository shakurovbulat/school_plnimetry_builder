"""Local structured extraction through Ollama's native API."""

import requests

from backend.config import settings
from backend.models import GeometrySchema
from backend.parser import parse_geometry_text
from backend.semantic_validation import (
    check_supported_text,
    preserve_explicit_facts,
    verify_coverage,
)
from backend.text_normalization import given_text

SYSTEM_PROMPT = """Ты формализуешь школьные задачи по планиметрии. Верни только JSON по заданной схеме.
points: уникальные имена A, B, A1, O1 (индексы допустимы). lines: пары имён точек.
figures: type, name, points по порядку обхода. Не выдумывай числовые данные.
constraints: distance [A,B] value=длина; angle [A,B,C] value=градусы (вершина B);
right_angle [A,B,C]; midpoint [M,A,B]; projection [H,P,A,B] (H проекция P на AB);
point_on_segment [M,A,B]; point_on_line [M,A,B];
parallel/perpendicular/equal_segments [[A,B],[C,D]];
ratio [[A,M],[M,B]] value=[3,4]; bisector [B,M,A,C] (BM биссектриса ABC).
sin/cos/tg [A,B,C] value=значение функции, не угол в градусах.
circumscribed_circle [O,A,B,C] (либо [O,A,B,C,D]); inscribed_circle [I,A,B,C].
Пример ограничения: {"type":"distance","args":["A","B"],"value":5}.
Прямой угол указывай явно в right_angle; тип right_triangle не определяет вершину.
Для прямоугольного треугольника лучше используй type triangle + right_angle.
circles: name, center (имя точки), radius либо null, passing_through.
Включай все используемые точки в points. Не добавляй условие из того, что требуется доказать.
Не вычисляй новые числовые длины или углы: сохраняй только явно заданные числа.
Угол C в ABC кодируется [A,C,B], угол A кодируется [B,A,C].
sin угла A = 0.6 кодируется {"type":"sin","args":["B","A","C"],"value":0.6}.
Квадрат ABCD имеет прямые углы ABC, BCD, CDA, DAB, но НЕ ACD.
tangent [O,T,P]: T на окружности с центром O, TP касательная.
external_tangency [O1,O2,T]: внешнее касание окружностей в T.
distinct [A,B]: различные точки; acute_angle [A,B,C]: острый угол B.
inside_triangle [P,A,B,C]: P строго внутри ABC.
product_equal [[A,B],[C,D],[A,D],[B,C]] означает AB*CD=AD*BC.
ratio_equal [[A,M],[M,B],[A,N],[N,C]] означает AM/MB=AN/NC.
Неизвестный угол α НЕ равен нулю: цепочку ∠PAB=∠PBC=∠PCA запиши двумя equal_angles,
без value: [[P,A,B],[P,B,C]] и [[P,B,C],[P,C,A]]. Никогда не заменяй неизвестное число нулём.
Для окружности проверь наличие её центра и всех passing_through в points.
Если объектов нет, верни пустые списки. Для чисел используй JSON numbers, а не строки.
"""


def get_llm_json_schema() -> dict:
    return GeometrySchema.model_json_schema()


def parse_with_llm(text: str, model: str | None = None) -> GeometrySchema:
    check_supported_text(text)
    draft = parse_geometry_text(text)
    raw_draft = draft
    import json

    draft = {k: draft.get(k, []) for k in GeometrySchema.model_fields}
    user_content = (
        given_text(text)
        + "\n\nПредварительная схема детерминированного парсера (проверь её по условию, "
        "сохрани верные ограничения, исправь только ошибки):\n"
        + json.dumps(draft, ensure_ascii=False)
    )
    try:
        response = requests.post(
            f"{settings.ollama_url}/api/chat",
            json={
                "model": model or settings.ollama_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                "format": get_llm_json_schema(),
                "stream": False,
                "think": False,
                "keep_alive": "5m",
                "options": {
                    "temperature": 0,
                    "num_ctx": settings.ollama_context,
                    "num_predict": 2048,
                },
            },
            timeout=(5, settings.ollama_timeout),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(
            "Ollama недоступна или модель не загружена. Проверьте ollama serve и ollama list."
        ) from exc
    try:
        schema = GeometrySchema.model_validate_json(response.json()["message"]["content"])
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(
            f"Ollama вернула некорректную геометрическую схему: {str(exc)[:1600]}"
        ) from exc
    if not schema.points:
        raise ValueError("Не удалось распознать геометрические фигуры на чертеже")
    return preserve_explicit_facts(schema, raw_draft)


def parse_hybrid(text: str, model: str | None = None, mode: str | None = None):
    """Explicit engine selection: service failures never trigger a hidden fallback."""
    selected = mode or settings.parser_mode
    if selected == "ollama":
        return parse_with_llm(
            text, model
        ), f"Ollama ({model or settings.ollama_model}) + проверенные конструкции правил"
    if selected != "rules":
        raise ValueError("Неизвестный режим парсера")
    check_supported_text(text)
    raw = parse_geometry_text(text)
    schema = GeometrySchema.model_validate({k: raw.get(k, []) for k in GeometrySchema.model_fields})
    verify_coverage(raw["clean_text"], schema)
    if not schema.points:
        raise ValueError("Не удалось распознать геометрические фигуры на чертеже")
    return schema, "Правила (без LLM)"


def ollama_status() -> dict:
    try:
        response = requests.get(f"{settings.ollama_url}/api/tags", timeout=5)
        response.raise_for_status()
        models = [m["name"] for m in response.json().get("models", [])]
        running = requests.get(f"{settings.ollama_url}/api/ps", timeout=5)
        running.raise_for_status()
        return {
            "available": True,
            "model": settings.ollama_model,
            "model_installed": settings.ollama_model in models,
            "models": models,
            "running": running.json().get("models", []),
        }
    except (requests.RequestException, ValueError, KeyError):
        return {
            "available": False,
            "model": settings.ollama_model,
            "model_installed": False,
            "models": [],
            "running": [],
        }
