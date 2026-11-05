"""Command handlers. All answers come straight from the backend API (no LLM),
except free-text questions, which are forwarded to /ai/chat as plain data."""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime
from functools import wraps
from typing import Any, Awaitable, Callable

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import BufferedInputFile, Message

from . import formatting as fm
from .backend import BackendClient, BackendError, NotFound, TooLarge
from .config import Settings
from .middlewares import chat_ref, is_addressed

log = logging.getLogger("bot.handlers")

RE_DEAL = re.compile(r"^\d{1,12}$")
RE_BROKER = re.compile(r"^BK\d{3}$", re.IGNORECASE)
RE_YEAR = re.compile(r"^(20\d{2})$")
RE_DATE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

GENERIC_ERR = "Ma'lumot manbasi hozir javob bermayapti. Birozdan keyin qayta urinib ko'ring."
AI_MAX_INPUT = 500
EXPORT_COOLDOWN = 30.0
AI_RETRY_AFTER = 300.0


class State:
    """Mutable per-process state kept out of module globals (easier to test)."""

    def __init__(self) -> None:
        self.ai_disabled_until = 0.0
        self.export_last: dict[int, float] = {}


def safe(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    @wraps(fn)
    async def wrapper(message: Message, *args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(message, *args, **kwargs)
        except BackendError as e:
            log.warning("%s backend error: %s chat=%s", fn.__name__, e, chat_ref(message.chat.id))
            await message.answer(GENERIC_ERR)
        except Exception:  # noqa: BLE001 - last resort, never leak internals to chat
            log.exception("%s failed chat=%s", fn.__name__, chat_ref(message.chat.id))
            await message.answer(GENERIC_ERR)

    return wrapper


def parse_year(arg: str | None) -> tuple[bool, int | None]:
    if not arg:
        return True, None
    m = RE_YEAR.match(arg.strip())
    if not m:
        return False, None
    return True, int(m.group(1))


def parse_date(s: str) -> date | None:
    if not RE_DATE.match(s):
        return None
    try:
        return datetime.strptime(s, "%d.%m.%Y").date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
async def cmd_help(message: Message, bot_state: State, backend: BackendClient) -> None:
    ai_on = backend.ai_enabled and time.monotonic() >= bot_state.ai_disabled_until
    await message.answer(fm.HELP if ai_on else fm.HELP_NO_AI)


async def cmd_chatid(message: Message) -> None:
    await message.answer(f"Chat ID: {message.chat.id} ({message.chat.type}).")


@safe
async def cmd_summary(message: Message, command: CommandObject, backend: BackendClient) -> None:
    ok, year = parse_year(command.args)
    if not ok:
        await message.answer("Yil noto'g'ri. Misol: /summary 2025")
        return
    uzs_d, usd_d = await backend.summary(year)
    await message.answer(fm.summary_text(year, uzs_d, usd_d))


@safe
async def cmd_deal(message: Message, command: CommandObject, backend: BackendClient) -> None:
    arg = (command.args or "").strip().lstrip("№#")
    if not RE_DEAL.match(arg):
        await message.answer("Bitim raqami faqat raqamlardan iborat bo'lishi kerak. Misol: /deal 1234567")
        return
    try:
        d = await backend.deal(int(arg))
    except NotFound:
        await message.answer(f"Bitim №{arg} topilmadi.")
        return
    await message.answer(fm.deal_text(d))


@safe
async def cmd_broker(message: Message, command: CommandObject, backend: BackendClient) -> None:
    arg = (command.args or "").strip()
    if not RE_BROKER.match(arg):
        await message.answer("Broker kodi BK va 3 raqamdan iborat. Misol: /broker BK001")
        return
    code = arg.upper()
    try:
        b = await backend.broker(code)
    except NotFound:
        await message.answer(f"Broker {code} topilmadi.")
        return
    await message.answer(fm.broker_text(b))


@safe
async def cmd_top_brokers(message: Message, command: CommandObject, backend: BackendClient) -> None:
    ok, year = parse_year(command.args)
    if not ok:
        await message.answer("Yil noto'g'ri. Misol: /top_brokers 2025")
        return
    data = await backend.top_brokers(year, limit=10)
    await message.answer(fm.top_brokers_text(data, year))


EXPORT_USAGE = (
    "Format: /export <boshlanish> <tugash> [holat] [xlsx]\n"
    "Misol: /export 01.01.2025 31.01.2025 bajarilgan xlsx\n"
    "Holatlar: yangi, imzolanmagan, tuzilgan, kutilmoqda, tolangan, bajarilgan, qisman, bekor"
)


@safe
async def cmd_export(
    message: Message, command: CommandObject, backend: BackendClient, settings: Settings, bot_state: State, bot: Bot
) -> None:
    args = (command.args or "").split()
    if len(args) < 2 or len(args) > 4:
        await message.answer(EXPORT_USAGE)
        return
    start, end = parse_date(args[0]), parse_date(args[1])
    if not start or not end:
        await message.answer("Sana noto'g'ri. Format: DD.MM.YYYY\n" + EXPORT_USAGE)
        return
    if start > end:
        await message.answer("Boshlanish sanasi tugash sanasidan keyin bo'lmasligi kerak.")
        return
    fmt, status = "csv", None
    for extra in args[2:]:
        low = extra.lower()
        if low in ("csv", "xlsx", "excel"):
            fmt = "xlsx" if low != "csv" else "csv"
        elif low in fm.STATUS_ALIASES:
            status = fm.STATUS_ALIASES[low]
        else:
            await message.answer(f"Noma'lum parametr: {extra[:30]}\n" + EXPORT_USAGE)
            return
    now = time.monotonic()
    last = bot_state.export_last.get(message.chat.id, -1e9)
    if now - last < EXPORT_COOLDOWN:
        await message.answer(f"Eksport har {int(EXPORT_COOLDOWN)} soniyada bir marta. Biroz kuting.")
        return
    bot_state.export_last[message.chat.id] = now  # reserve the slot before any await (no races)
    period = f"{start:%d.%m.%Y}–{end:%d.%m.%Y}"
    status_lbl = fm.status_uz(status) if status else "barcha holatlar"
    try:
        total = await backend.count_deals(start, end, status)
    except BackendError:
        bot_state.export_last.pop(message.chat.id, None)
        raise
    if total == 0 or total > settings.export_max_rows:
        bot_state.export_last.pop(message.chat.id, None)  # nothing exported: allow a retry right away
        if total == 0:
            await message.answer(f"{period}, {status_lbl}: bitimlar topilmadi. Fayl yuborilmadi.")
        else:
            await message.answer(
                f"{period}, {status_lbl}: {fm.fmt_int(total)} bitim — chegaradan ko'p "
                f"({fm.fmt_int(settings.export_max_rows)}). Davrni qisqartiring yoki holat qo'shing."
            )
        return
    await bot.send_chat_action(message.chat.id, "upload_document")
    try:
        content = await backend.export(start, end, status, fmt, settings.export_max_bytes)
    except TooLarge:
        await message.answer("Fayl 45 MB dan katta. Davrni qisqartiring yoki holat qo'shing.")
        return
    name = f"bitimlar_{start:%Y%m%d}_{end:%Y%m%d}" + (f"_{fmt_slug(status)}" if status else "") + f".{fmt}"
    caption = f"Bitimlar: {fm.fmt_int(total)}. Davr: {period}. Holat: {status_lbl}. Format: {fmt.upper()}."
    await message.answer_document(BufferedInputFile(content, filename=name), caption=caption)


def fmt_slug(status: str) -> str:
    for alias, ru in fm.STATUS_ALIASES.items():
        if ru == status and alias.isascii():
            return alias
    return "holat"


# ---------------------------------------------------------------------------
async def _addressed_text(message: Message, bot: Bot) -> bool:
    return bool(message.text) and not message.text.startswith("/") and await is_addressed(message, bot)


@safe
async def free_text(message: Message, bot: Bot, backend: BackendClient, bot_state: State) -> None:
    me = await bot.me()
    text = message.text or ""
    if me.username:
        text = re.sub(rf"@{re.escape(me.username)}\b", " ", text, flags=re.IGNORECASE)
    text = CTRL.sub(" ", text).strip()[:AI_MAX_INPUT]
    if not text:
        await message.answer(fm.HELP)
        return
    if not backend.ai_enabled or time.monotonic() < bot_state.ai_disabled_until:
        await message.answer(fm.HELP_NO_AI)
        return
    await bot.send_chat_action(message.chat.id, "typing")
    try:
        answer = await backend.ai_chat(text)  # user text is sent as data in the `message` field
    except BackendError as e:
        log.info("ai unavailable (%s) chat=%s", e, chat_ref(message.chat.id))
        bot_state.ai_disabled_until = time.monotonic() + AI_RETRY_AFTER
        await message.answer(fm.HELP_NO_AI)
        return
    await message.answer(fm.clip(answer.strip()))


def build_router() -> Router:
    """Fresh router per dispatcher (aiogram routers can be attached only once)."""
    r = Router(name="registry")
    r.message(CommandStart())(cmd_help)
    r.message(Command("help"))(cmd_help)
    r.message(Command("chatid"))(cmd_chatid)
    r.message(Command("summary"))(cmd_summary)
    r.message(Command("deal"))(cmd_deal)
    r.message(Command("broker"))(cmd_broker)
    r.message(Command("top_brokers"))(cmd_top_brokers)
    r.message(Command("export"))(cmd_export)
    r.message(F.text, _addressed_text)(free_text)
    return r
