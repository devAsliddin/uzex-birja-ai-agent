"""Settings loaded from bot/.env (never logged)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BOT_DIR = Path(__file__).resolve().parent.parent


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _ids(raw: str) -> frozenset[int]:
    out: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.add(int(part))
    return frozenset(out)


@dataclass(frozen=True)
class Settings:
    bot_token: str = field(repr=False)
    backend_url: str = "http://127.0.0.1:8000/api/v1"
    # PUBLIC_MODE=true: every chat is served (jury opens the bot without registration).
    # ALLOWED_CHAT_IDS is used only when PUBLIC_MODE=false.
    public_mode: bool = True
    allowed_chat_ids: frozenset[int] = frozenset()
    rate_limit_per_min: int = 10  # per user
    rate_limit_per_day: int = 200  # per user
    agent_concurrency: int = 20  # global cap on simultaneous /agent/ask calls
    agent_timeout: float = 80.0  # seconds, includes queueing (jury limit is 90 s)
    export_max_rows: int = 20_000
    export_max_bytes: int = 45 * 1024 * 1024  # Telegram bot upload limit is 50 MB
    http_timeout: float = 30.0


def load_settings() -> Settings:
    load_dotenv(BOT_DIR / ".env")
    return Settings(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        backend_url=(os.getenv("BACKEND_URL") or "http://127.0.0.1:8000/api/v1").rstrip("/"),
        public_mode=_bool("PUBLIC_MODE", True),
        allowed_chat_ids=_ids(os.getenv("ALLOWED_CHAT_IDS", "")),
        rate_limit_per_min=_int("RATE_LIMIT_PER_MIN", 10),
        rate_limit_per_day=_int("RATE_LIMIT_PER_DAY", 200),
        agent_concurrency=_int("AGENT_CONCURRENCY", 20),
        agent_timeout=_float("AGENT_TIMEOUT", 80.0),
        export_max_rows=_int("EXPORT_MAX_ROWS", 20_000),
    )
