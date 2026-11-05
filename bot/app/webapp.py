"""Telegram Mini App wiring: the web app URL (env or tunnel file) and the chat menu button.

The tunnel watchdog writes the current public HTTPS URL into run/webapp_url.txt and it may change, so the
bot re-reads it every 60 s and re-registers the default menu button when it changes.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from urllib.parse import urlparse

from aiogram import Bot
from aiogram.types import MenuButtonWebApp, WebAppInfo

log = logging.getLogger("bot.webapp")

MENU_TEXT = "AI chat"
CHECK_EVERY = 60.0


def clean_url(raw: str | None) -> str | None:
    """Only absolute https URLs without whitespace (Telegram rejects anything else for web_app)."""
    if not raw:
        return None
    url = raw.strip().splitlines()[0].strip() if raw.strip() else ""
    if not url or len(url) > 512 or any(c.isspace() for c in url):
        return None
    p = urlparse(url)
    if p.scheme != "https" or not p.netloc:
        return None
    return url.rstrip("/") + "/"


def read_url(env_url: str, path: Path) -> str | None:
    """The tunnel file wins (it is the freshest); the env value is the fallback."""
    try:
        from_file = clean_url(path.read_text(encoding="utf-8-sig"))
    except OSError:
        from_file = None
    return from_file or clean_url(env_url)


async def apply_menu(bot: Bot, url: str) -> bool:
    try:
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text=MENU_TEXT, web_app=WebAppInfo(url=url)))
        return True
    except Exception as e:  # noqa: BLE001 - never crash polling over a cosmetic button
        log.warning("set_chat_menu_button failed: %s", type(e).__name__)
        return False


async def refresh(bot: Bot, state, env_url: str, path: Path) -> None:
    url = read_url(env_url, path)
    if not url:
        return  # no URL yet: skip silently
    state.webapp_url = url  # /start buttons use it right away
    if url != state.menu_url and await apply_menu(bot, url):
        state.menu_url = url  # a failed call is retried on the next check
        log.info("web app menu button set host=%s", urlparse(url).netloc)


async def watch(bot: Bot, state, env_url: str, path: Path, every: float = CHECK_EVERY) -> None:
    while True:
        await refresh(bot, state, env_url, path)
        await asyncio.sleep(every)
