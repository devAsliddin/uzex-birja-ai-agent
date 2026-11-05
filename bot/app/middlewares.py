"""Access control + per-user rate limit (outer middlewares on messages)."""

from __future__ import annotations

import hashlib
import logging
import time
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.types import Message

log = logging.getLogger("bot.access")


def chat_ref(chat_id: int) -> str:
    """Non-reversible short reference for logs (no raw ids / names / text)."""
    return hashlib.sha256(str(chat_id).encode()).hexdigest()[:10]


async def is_addressed(message: Message, bot: Bot) -> bool:
    """True if the message is meant for the bot (command, mention, reply, or private chat)."""
    if message.chat.type == "private":
        return True
    text = message.text or message.caption or ""
    if text.startswith("/"):
        return True
    me = await bot.me()
    r = message.reply_to_message
    if r and r.from_user and r.from_user.id == me.id:
        return True
    return bool(me.username) and f"@{me.username.lower()}" in text.lower()


class AccessMiddleware(BaseMiddleware):
    """PUBLIC_MODE=true: everyone is served. Otherwise only `allowed` chat ids."""

    def __init__(self, allowed: frozenset[int], refusal_cooldown: float = 60.0, public: bool = False) -> None:
        self.allowed = allowed
        self.public = public
        self.cooldown = refusal_cooldown
        self._last_refusal: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        chat_id = event.chat.id
        if self.public or chat_id in self.allowed:
            return await handler(event, data)
        bot: Bot = data["bot"]
        text = (event.text or "").strip()
        if text.split("@")[0].split(" ")[0] == "/chatid":
            return await handler(event, data)  # setup helper works everywhere
        if not await is_addressed(event, bot):
            return None
        log.warning("denied chat=%s type=%s", chat_ref(chat_id), event.chat.type)
        now = time.monotonic()
        if now - self._last_refusal.get(chat_id, -1e9) >= self.cooldown:
            self._last_refusal[chat_id] = now
            await event.answer(f"Bu chat uchun ruxsat yo'q. Chat ID: {chat_id}. Administratorga yuboring.")
        return None


class RateLimitMiddleware(BaseMiddleware):
    """Per-user sliding windows: at most `per_minute` addressed messages per 60 s and `per_day` per 24 h.

    Keyed by the sender's user id (falls back to the chat id for anonymous/channel posts), so one noisy
    user in a group does not block the other jury members.
    """

    def __init__(self, per_minute: int, per_day: int = 200, window: float = 60.0, day: float = 86_400.0) -> None:
        self.per_minute = max(1, per_minute)
        self.per_day = max(1, per_day)
        self.window = window
        self.day = day
        self._hits: dict[int, deque[float]] = defaultdict(deque)
        self._day_hits: dict[int, deque[float]] = defaultdict(deque)
        self._warned: dict[int, float] = {}

    @staticmethod
    def _key(event: Message) -> int:
        return event.from_user.id if event.from_user else event.chat.id

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        if not await is_addressed(event, data["bot"]):
            return await handler(event, data)
        key = self._key(event)
        now = time.monotonic()
        q, qd = self._hits[key], self._day_hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        while qd and now - qd[0] > self.day:
            qd.popleft()
        if len(q) >= self.per_minute or len(qd) >= self.per_day:
            daily = len(qd) >= self.per_day
            log.info("rate-limited user=%s daily=%s", chat_ref(key), daily)
            if now - self._warned.get(key, -1e9) >= self.window:
                self._warned[key] = now
                if daily:
                    await event.answer("Kunlik so'rovlar limiti tugadi. / Дневной лимит вопросов исчерпан.")
                else:
                    await event.answer(
                        "So'rovlar juda ko'p. 1 daqiqadan keyin qayta urinib ko'ring. / "
                        "Слишком много запросов, повторите через минуту."
                    )
            return None
        q.append(now)
        qd.append(now)
        return await handler(event, data)
