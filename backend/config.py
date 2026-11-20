"""Server-side configuration for the external LLM API."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)


def load_api_key() -> str:
    key = os.getenv("LLM_API_KEY", "").strip()
    if key:
        return key
    key_file = os.getenv("LLM_KEY_FILE", "").strip()
    if not key_file:
        return ""
    try:
        key = Path(key_file).expanduser().read_text(encoding="utf-8-sig").strip()
    except (OSError, UnicodeError):
        return ""
    return key if not any(ch.isspace() for ch in key) else ""


@dataclass(frozen=True)
class Settings:
    api_url: str = os.getenv("LLM_BASE_URL", "").strip().rstrip("/")
    api_key: str = field(default_factory=load_api_key, repr=False)
    model: str = os.getenv("LLM_MODEL", "").strip() or "gpt-6.2-sol"
    timeout: float = float(os.getenv("LLM_TIMEOUT", "180"))
    max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "8192"))
    stream: bool = os.getenv("LLM_STREAM", "true").strip().lower() not in {
        "0", "false", "no", "off"
    }


settings = Settings()
