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


@dataclass(frozen=True)
class Settings:
    bot_token: str = field(repr=False)
    backend_url: str = "http://127.0.0.1:8000/api/v1"
    # The bot is public: every user and chat is served equally (no admins, no allow-list).
    # Abuse protection = per-user rate limits + a global concurrency cap.
    rate_limit_per_min: int = 10  # per user
    rate_limit_per_day: int = 200  # per user
    agent_concurrency: int = 20  # global cap on simultaneous /agent/ask calls
    agent_timeout: float = 80.0  # seconds, includes queueing (jury limit is 90 s)
    # Telegram Mini App: WEBAPP_URL from env; run/webapp_url.txt (written by the tunnel watchdog) wins.
    webapp_url: str = ""
    webapp_url_file: Path = BOT_DIR.parent / "run" / "webapp_url.txt"
    export_max_rows: int = 20_000
    export_max_bytes: int = 45 * 1024 * 1024  # Telegram bot upload limit is 50 MB
    http_timeout: float = 30.0


def load_settings() -> Settings:
    load_dotenv(BOT_DIR / ".env")
    return Settings(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        backend_url=(os.getenv("BACKEND_URL") or "http://127.0.0.1:8000/api/v1").rstrip("/"),
        rate_limit_per_min=_int("RATE_LIMIT_PER_MIN", 10),
        rate_limit_per_day=_int("RATE_LIMIT_PER_DAY", 200),
        agent_concurrency=_int("AGENT_CONCURRENCY", 20),
        agent_timeout=_float("AGENT_TIMEOUT", 80.0),
        webapp_url=(os.getenv("WEBAPP_URL") or "").strip(),
        webapp_url_file=Path(os.getenv("WEBAPP_URL_FILE") or (BOT_DIR.parent / "run" / "webapp_url.txt")),
        export_max_rows=_int("EXPORT_MAX_ROWS", 20_000),
    )
