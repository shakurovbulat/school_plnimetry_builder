"""Server-side configuration. Cloud API keys are intentionally not used."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)


@dataclass(frozen=True)
class Settings:
    ollama_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "deepseek-coder-v2:16b")
    ollama_timeout: float = float(os.getenv("OLLAMA_TIMEOUT", "180"))
    ollama_context: int = int(os.getenv("OLLAMA_CONTEXT", "4096"))
    parser_mode: str = os.getenv("PARSER_MODE", "ollama")


settings = Settings()
