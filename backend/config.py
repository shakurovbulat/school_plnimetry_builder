"""Server-side Apilsin configuration. Secrets never belong in the frontend."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)


def load_api_key() -> str:
    key = os.getenv("APILSIN_API_KEY", "").strip()
    if key:
        return key
    # The operator's local credential file is not necessarily valid JSON.
    path = Path(
        os.getenv("APILSIN_KEY_FILE", str(Path.home() / "Desktop" / "apikey.json"))
    )
    try:
        tokens = set(
            re.findall(
                r"sk-apilsin-[A-Za-z0-9_-]+", path.read_text(encoding="utf-8-sig")
            )
        )
    except OSError:
        return ""
    return tokens.pop() if len(tokens) == 1 else ""


@dataclass(frozen=True)
class Settings:
    api_url: str = os.getenv("APILSIN_BASE_URL", "https://api.apilsin.run/v1").rstrip(
        "/"
    )
    api_key: str = field(default_factory=load_api_key, repr=False)
    model: str = os.getenv("APILSIN_MODEL", "gpt-6.1-sol")
    timeout: float = float(os.getenv("APILSIN_TIMEOUT", "180"))
    max_tokens: int = int(os.getenv("APILSIN_MAX_TOKENS", "8192"))


settings = Settings()
