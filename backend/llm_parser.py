"""External LLM recognition with structured response validation."""

import json
import logging
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from urllib3.exceptions import ReadTimeoutError

from backend.config import settings
from backend.models import GeometrySchema

logger = logging.getLogger(__name__)

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

    def __init__(self, message: str, *, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code


def get_llm_json_schema() -> dict:
    return GeometrySchema.model_json_schema()


def provider_status() -> dict:
    return {
        "provider": "external_llm",
        "model": settings.model,
        "configured": bool(settings.api_url and settings.api_key),
    }


def _sse_data(response: requests.Response) -> Iterator[str]:
    """Yield complete data events, ignoring SSE comments and other fields."""
    data = []
    pending = b""
    for chunk in response.iter_content(chunk_size=512):
        # A network chunk can split a UTF-8 character or the CRLF line ending.
        *lines, pending = (pending + chunk).split(b"\n")
        for raw_line in lines:
            line = raw_line.removesuffix(b"\r")
            if not line:
                if data:
                    yield b"\n".join(data).decode("utf-8")
                    data.clear()
            elif line.startswith(b"data:"):
                data.append(line[5:].removeprefix(b" "))


def _receive_stream(response: requests.Response) -> dict:
    content = []
    refusal = False
    try:
        for data in _sse_data(response):
            if data == "[DONE]":
                break
            event = json.loads(data)
            if not isinstance(event, dict) or "error" in event:
                raise ValueError
            # Role/usage-only chunks and separate reasoning deltas aren't JSON output.
            for choice in event.get("choices", []):
                if choice.get("index", 0) != 0:
                    continue
                delta = choice.get("delta") or {}
                piece = delta.get("content")
                if piece is not None:
                    if not isinstance(piece, str):
                        raise ValueError
                    content.append(piece)
                refusal = refusal or bool(delta.get("refusal"))
                if (reason := choice.get("finish_reason")) is not None:
                    return {
                        "finish_reason": reason,
                        "message": {"content": "".join(content), "refusal": refusal},
                    }
    except (ValueError, TypeError, AttributeError):
        raise ProviderError(
            "Внешний API вернул ошибку или некорректные данные в потоке.",
            status_code=502,
        ) from None
    raise ProviderError(
        "Поток внешнего API завершился до получения полного ответа модели.",
        status_code=502,
    )


def _check_status(status: int, started: float) -> None:
    if status == 200:
        return
    elapsed = time.monotonic() - started
    logger.warning("External LLM: HTTP %d after %.1fs", status, elapsed)
    if status == 504:
        raise ProviderError(
            f"Шлюз внешнего API вернул HTTP 504 через {elapsed:.1f} с: "
            "не дождался ответа от своего сервера. Попробуйте ещё раз. "
            "Если ошибка повторяется, укажите более быструю доступную модель в LLM_MODEL.",
            status_code=504,
        )
    messages = {
        400: "Внешний API отклонил запрос: проверьте ID модели и параметры API.",
        401: "API-ключ недействителен или отключён.",
        402: "Недостаточно средств или исчерпан лимит расходов на API.",
        403: "Внешний API запретил доступ. Проверьте права ключа и доступ к модели.",
        404: "Внешний API не нашёл ресурс. Проверьте адрес API и ID модели.",
        429: "Превышен лимит запросов или расходов. Попробуйте позже.",
        503: f"Внешний API временно недоступен (HTTP 503 через {elapsed:.1f} с). "
        "Попробуйте позже.",
    }
    raise ProviderError(messages.get(status, f"Внешний API недоступен (HTTP {status})."))


def _request_choice(payload: dict) -> dict:
    started = time.monotonic()
    try:
        with requests.post(
            f"{settings.api_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.api_key}"},
            json=payload,
            stream=True,  # Check HTTP status before consuming the body.
            timeout=(10, settings.timeout),
        ) as response:
            _check_status(response.status_code, started)
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0]
            if content_type.strip().lower() == "text/event-stream":
                return _receive_stream(response)
            # Some compatible providers return ordinary JSON even with stream=true.
            return response.json()["choices"][0]
    except (requests.Timeout, requests.ConnectionError) as exc:
        # requests wraps idle timeouts during body consumption in ConnectionError.
        elapsed = time.monotonic() - started
        logger.warning("External LLM: %s after %.1fs", type(exc).__name__, elapsed)
        if isinstance(exc, requests.ConnectTimeout):
            detail = f"Не удалось подключиться к внешнему API за {elapsed:.1f} с."
        elif isinstance(exc, requests.Timeout) or (
            exc.args and isinstance(exc.args[0], ReadTimeoutError)
        ):
            detail = f"Приложение не дождалось ответа внешнего API ({elapsed:.1f} с)."
        else:
            raise ProviderError("Не удалось связаться с внешним API.") from None
        raise ProviderError(f"{detail} Попробуйте ещё раз.", status_code=504) from None
    except requests.exceptions.ChunkedEncodingError:
        logger.warning(
            "External LLM: body interrupted after %.1fs", time.monotonic() - started
        )
        raise ProviderError(
            "Соединение с внешним API оборвалось во время ответа.", status_code=502
        ) from None
    except requests.exceptions.JSONDecodeError:
        # Keep the same validation error for malformed non-streaming responses.
        raise ValueError("Модель вернула некорректный JSON или геометрическую схему.") from None
    except requests.RequestException as exc:
        logger.warning(
            "External LLM: %s after %.1fs", type(exc).__name__, time.monotonic() - started
        )
        raise ProviderError("Не удалось связаться с внешним API.") from None


def parse_task(
    text: str, model: str | None = None
) -> tuple[GeometrySchema, str, list[str]]:
    if not settings.api_url:
        raise ProviderError("Не задан адрес внешнего API (LLM_BASE_URL).")
    if not settings.api_key:
        raise ProviderError(
            "Задайте LLM_API_KEY или укажите LLM_KEY_FILE с одним ключом."
        )
    selected = model or settings.model
    # Supply the schema in the prompt without relying on strict JSON Schema mode.
    payload = {
        "model": selected,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
                + "\n\nJSON Schema ответа:\n"
                + json.dumps(
                    Recognition.model_json_schema(), ensure_ascii=False, separators=(",", ":")
                ),
            },
            {"role": "user", "content": text},
        ],
        "stream": settings.stream,
        "max_tokens": settings.max_tokens,
    }
    try:
        choice = _request_choice(payload)
        finish_reason = choice.get("finish_reason")
        if finish_reason == "length":
            raise ProviderError(
                "Ответ модели оборвался на лимите токенов. "
                "Сократите условие или увеличьте LLM_MAX_TOKENS, если API это позволяет.",
                status_code=502,
            )
        if finish_reason not in ("stop", None):
            raise ProviderError(
                "Ответ модели прерван или отклонён. Полная схема не получена.",
                status_code=502,
            )
        message = choice["message"]
        if message.get("refusal"):
            raise ValueError("Модель отказалась распознавать условие.")
        result = Recognition.model_validate_json(message["content"])
    except (KeyError, IndexError, TypeError, AttributeError, ValidationError, json.JSONDecodeError):
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
        f"Внешняя LLM ({selected}) — прямое распознавание",
        result.warnings,
    )
