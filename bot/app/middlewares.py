"""Per-user rate limit (outer middleware on messages). The bot is public: no access control by design."""

from __future__ import annotations

import hashlib
import logging
import time
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Message

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


LIMIT_DAY = "Kunlik so'rovlar limiti tugadi. / Дневной лимит вопросов исчерпан."
LIMIT_MIN = ("So'rovlar juda ko'p. 1 daqiqadan keyin qayta urinib ko'ring. / "
             "Слишком много запросов, повторите через минуту.")


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
    def _key(event: Message | CallbackQuery) -> int:
        if event.from_user:
            return event.from_user.id
        return event.message.chat.id if isinstance(event, CallbackQuery) and event.message else event.chat.id

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and not await is_addressed(event, data["bot"]):
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
            warn = now - self._warned.get(key, -1e9) >= self.window
            if isinstance(event, CallbackQuery):  # always answer the button so it stops spinning
                if warn:
                    self._warned[key] = now
                await event.answer(LIMIT_DAY if daily else LIMIT_MIN, show_alert=False)
                return None
            if warn:
                self._warned[key] = now
                await event.answer(LIMIT_DAY if daily else LIMIT_MIN)
            return None
        q.append(now)
        qd.append(now)
        return await handler(event, data)
