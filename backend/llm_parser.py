"""Apilsin recognition with structured response validation."""

import json
from pathlib import Path
from typing import Literal

import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.config import settings
from backend.models import GeometrySchema

SYSTEM_PROMPT = (
    Path(__file__).with_name("recognition_prompt.md").read_text(encoding="utf-8")
)


class Recognition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok", "needs_clarification", "unsupported"]
    message: str
    warnings: list[str] = Field(default_factory=list)
    geometry: GeometrySchema | None


class ProviderError(RuntimeError):
    """Safe provider error without credentials, response bodies or request headers."""


def get_llm_json_schema() -> dict:
    return GeometrySchema.model_json_schema()


def provider_status() -> dict:
    return {
        "provider": "apilsin",
        "model": settings.model,
        "configured": bool(settings.api_key),
    }


def parse_task(
    text: str, model: str | None = None
) -> tuple[GeometrySchema, str, list[str]]:
    if not settings.api_key:
        raise ProviderError(
            "Не настроен APILSIN_API_KEY или файл APILSIN_KEY_FILE с одним ключом."
        )
    selected = model or settings.model
    # The documented gateway guarantees chat completions, not strict json_schema mode.
    # Supply the schema in the prompt and validate the returned JSON locally.
    payload = {
        "model": selected,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
                + "\n\nJSON Schema ответа:\n"
                + json.dumps(Recognition.model_json_schema(), ensure_ascii=False),
            },
            {"role": "user", "content": text},
        ],
        "stream": False,
        "max_tokens": settings.max_tokens,
    }
    try:
        response = requests.post(
            f"{settings.api_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.api_key}"},
            json=payload,
            timeout=(10, settings.timeout),
        )
    except requests.Timeout:
        raise ProviderError("Apilsin не ответил вовремя. Попробуйте позже.") from None
    except requests.RequestException:
        raise ProviderError("Не удалось связаться с Apilsin.") from None
    if response.status_code != 200:
        messages = {
            400: "Apilsin отклонил запрос: проверьте ID модели и параметры API.",
            401: "Apilsin: API-ключ недействителен или отключён.",
            402: "Apilsin: недостаточно средств или исчерпан лимит расходов.",
            429: "Apilsin: превышен лимит запросов или расходов. Попробуйте позже.",
        }
        raise ProviderError(
            messages.get(
                response.status_code,
                f"Apilsin недоступен (HTTP {response.status_code}).",
            )
        )
    try:
        choice = response.json()["choices"][0]
        if choice.get("finish_reason") not in ("stop", None):
            raise ProviderError(
                "Ответ модели прерван или отклонён. Полная схема не получена."
            )
        message = choice["message"]
        if message.get("refusal"):
            raise ValueError("Модель отказалась распознавать условие.")
        result = Recognition.model_validate_json(message["content"])
    except (KeyError, IndexError, TypeError, ValidationError, json.JSONDecodeError):
        raise ValueError(
            "Модель вернула некорректный JSON или геометрическую схему."
        ) from None
    if result.status != "ok":
        raise ValueError(
            result.message or "Нужно уточнить условие или оно не поддерживается."
        )
    if result.geometry is None or not result.geometry.points:
        raise ValueError("Модель не распознала геометрические объекты.")
    if any(
        c.type.value in {"circle_center", "segment_difference"}
        for c in result.geometry.constraints
    ):
        raise ValueError(
            "Модель использовала ограничение, не поддерживаемое точно решателем."
        )
    return (
        result.geometry,
        f"Apilsin ({selected}) — прямое распознавание",
        result.warnings,
    )
