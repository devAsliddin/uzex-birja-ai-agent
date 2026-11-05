"""Entry point: python -m app.main"""

from __future__ import annotations

import asyncio
import logging
import re
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand

from . import webapp
from .backend import BackendClient
from .config import Settings, load_settings
from .handlers import State, build_router
from .middlewares import RateLimitMiddleware

TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")

COMMANDS = [
    BotCommand(command="start", description="Savol berish / Задать вопрос"),
    BotCommand(command="new", description="Yangi suhbat / Новый диалог"),
    BotCommand(command="summary", description="Jami aylanma: /summary [yil]"),
    BotCommand(command="deal", description="Bitim kartochkasi: /deal <raqam>"),
    BotCommand(command="broker", description="Broker profili: /broker BK001"),
    BotCommand(command="top_brokers", description="Top-10 broker: /top_brokers [yil]"),
    BotCommand(command="export", description="Fayl: /export DD.MM.YYYY DD.MM.YYYY [holat] [xlsx]"),
    BotCommand(command="help", description="Buyruqlar ro'yxati"),
]


def build_dispatcher(settings: Settings, backend: BackendClient, state: State | None = None) -> Dispatcher:
    dp = Dispatcher(backend=backend, settings=settings, bot_state=state or State(settings.agent_concurrency))
    limiter = RateLimitMiddleware(settings.rate_limit_per_min, settings.rate_limit_per_day)
    dp.message.outer_middleware(limiter)
    dp.callback_query.outer_middleware(limiter)  # example buttons share the same per-user budget
    dp.include_router(build_router())
    return dp


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout
    )
    # httpx logs full URLs at INFO; keep it quiet. Telegram calls go via aiohttp (token never logged).
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


async def run(settings: Settings) -> None:
    backend = BackendClient(settings.backend_url, timeout=settings.http_timeout)
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=None))
    state = State(settings.agent_concurrency)
    dp = build_dispatcher(settings, backend, state)
    log = logging.getLogger("bot")
    watcher: asyncio.Task | None = None
    try:
        me = await bot.get_me()
        log.info("started as @%s; backend=%s; public; agent cap=%d; limits %d/min %d/day per user",
                 me.username, settings.backend_url, settings.agent_concurrency,
                 settings.rate_limit_per_min, settings.rate_limit_per_day)
        try:
            await bot.set_my_commands(COMMANDS)
        except Exception:  # noqa: BLE001 - cosmetic, not fatal
            log.warning("set_my_commands failed")
        watcher = asyncio.create_task(webapp.watch(bot, state, settings.webapp_url, settings.webapp_url_file))
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"], handle_signals=True)
    finally:
        if watcher:
            watcher.cancel()
        await backend.close()
        await bot.session.close()


def main() -> int:
    _setup_logging()
    settings = load_settings()
    if not settings.bot_token or settings.bot_token.startswith("123456789:AAFake"):
        print(
            "BOT_TOKEN topilmadi. bot/.env faylini yarating (.env.example dan nusxa) va @BotFather "
            "bergan tokenni BOT_TOKEN= ga yozing.\n"
            "BOT_TOKEN is missing: copy bot/.env.example to bot/.env and set BOT_TOKEN.",
            file=sys.stderr,
        )
        return 2
    if not TOKEN_RE.match(settings.bot_token):
        print("BOT_TOKEN formati noto'g'ri (kutilgan: 123456:ABC...). / BOT_TOKEN format is invalid.",
              file=sys.stderr)
        return 2
    try:
        asyncio.run(run(settings))
    except KeyboardInterrupt:
        pass
    except Exception as e:  # noqa: BLE001
        # Do not print the exception repr: aiohttp errors may contain request URLs with the token.
        print(f"Bot to'xtadi: {type(e).__name__}. Tokenni va internetni tekshiring.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
