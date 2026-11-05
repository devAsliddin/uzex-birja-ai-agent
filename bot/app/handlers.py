"""Command handlers. Commands are answered straight from the backend REST API (no LLM).
Free-text questions go to /agent/ask as plain data; the reply shows the answer plus its source (basis, SQL, rows)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
from collections import OrderedDict, deque
from datetime import date, datetime
from functools import wraps
from typing import Any, Awaitable, Callable

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from . import formatting as fm
from .backend import AgentTimeout, BackendClient, BackendError, NotFound, TooLarge
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
TYPING_EVERY = 4.0  # Telegram shows "typing" for ~5 s per action


class State:
    """Mutable per-process state kept out of module globals (easier to test)."""

    HISTORY_TURNS = 6  # last 6 question/answer pairs are sent with each question
    MAX_CONVERSATIONS = 5000  # LRU bound on in-memory conversations

    def __init__(self, agent_concurrency: int = 20) -> None:
        self.export_last: dict[int, float] = {}
        # Global cap: at most N questions hit the agent at once; the rest wait (inside the timeout).
        self.agent_sem = asyncio.Semaphore(max(1, agent_concurrency))
        self._conv: OrderedDict[tuple[int, int], deque[dict[str, str]]] = OrderedDict()
        self.webapp_url: str | None = None  # Mini App URL (env / tunnel file), refreshed every 60 s
        self.menu_url: str | None = None  # URL the chat menu button currently points to

    def history(self, key: tuple[int, int]) -> list[dict[str, str]]:
        return list(self._conv.get(key, ()))

    def remember(self, key: tuple[int, int], question: str, answer: str) -> None:
        q = self._conv.get(key)
        if q is None:
            q = self._conv[key] = deque(maxlen=2 * self.HISTORY_TURNS)
            while len(self._conv) > self.MAX_CONVERSATIONS:
                self._conv.popitem(last=False)
        self._conv.move_to_end(key)
        q.append({"role": "user", "content": question})
        q.append({"role": "assistant", "content": answer[:2000]})

    def reset(self, key: tuple[int, int]) -> None:
        self._conv.pop(key, None)


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
async def cmd_start(message: Message, bot_state: State) -> None:
    rows = [[InlineKeyboardButton(text=q, callback_data=f"ex:{i}")] for i, q in enumerate(fm.EXAMPLES)]
    url = bot_state.webapp_url
    if url:
        # web_app buttons work only in private chats; groups get a plain link to the same app
        btn = (InlineKeyboardButton(text=fm.OPEN_APP, web_app=WebAppInfo(url=url))
               if message.chat.type == "private" else InlineKeyboardButton(text=fm.OPEN_APP, url=url))
        rows.insert(0, [btn])
    await message.answer(fm.START_TEXT, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


async def cmd_help(message: Message) -> None:
    await message.answer(fm.HELP)


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


async def _keep_typing(bot: Bot, chat_id: int) -> None:
    """Re-send "typing" while the agent works (the first one is sent before this task starts)."""
    with contextlib.suppress(Exception):
        while True:
            await asyncio.sleep(TYPING_EVERY)
            await bot.send_chat_action(chat_id, "typing")


def _conv_key(chat_id: int, user_id: int | None) -> tuple[int, int]:
    """History is kept per chat AND per user, so jury members in one group do not mix contexts."""
    return chat_id, user_id or 0


async def free_text(message: Message, bot: Bot, backend: BackendClient, bot_state: State, settings: Settings) -> None:
    me = await bot.me()
    text = message.text or ""
    if me.username:
        text = re.sub(rf"@{re.escape(me.username)}\b", " ", text, flags=re.IGNORECASE)
    user_id = message.from_user.id if message.from_user else None
    await ask_and_reply(bot, message.chat.id, user_id, text, backend, bot_state, settings,
                        reply_to=message.message_id if message.chat.type != "private" else None)


async def ask_and_reply(
    bot: Bot, chat_id: int, user_id: int | None, raw: str, backend: BackendClient, bot_state: State,
    settings: Settings, *, reply_to: int | None = None, echo: bool = False,
) -> None:
    """Send the question (+ short history) to the agent and post the answer with its source."""
    text = CTRL.sub(" ", raw).strip()[:AI_MAX_INPUT]
    if not text:
        await bot.send_message(chat_id, fm.agent_failure("empty", raw), parse_mode="HTML")
        return
    ref = chat_ref(chat_id)
    key = _conv_key(chat_id, user_id)
    history = bot_state.history(key)
    with contextlib.suppress(Exception):
        await bot.send_chat_action(chat_id, "typing")
    typing = asyncio.create_task(_keep_typing(bot, chat_id))
    t0 = time.monotonic()
    try:
        try:
            async with asyncio.timeout(settings.agent_timeout):
                async with bot_state.agent_sem:
                    resp = await backend.ask(text, history=history, timeout=settings.agent_timeout)
            reply = fm.agent_reply(resp, text)
            if resp.get("status") in ("ok", "no_data") and str(resp.get("answer") or "").strip():
                bot_state.remember(key, text, str(resp["answer"]).strip())
            log.info("ask chat=%s status=%s turns=%d ms=%d", ref, resp.get("status"), len(history) // 2,
                     (time.monotonic() - t0) * 1000)
        except (TimeoutError, AgentTimeout):
            log.warning("ask timeout chat=%s", ref)
            reply = fm.agent_failure("timeout", text)
        except BackendError as e:
            log.warning("ask backend error (%s) chat=%s", e, ref)
            reply = fm.agent_failure("down", text)
        except Exception:  # noqa: BLE001 - never leak internals to chat
            log.exception("ask failed chat=%s", ref)
            reply = fm.agent_failure("down", text)
    finally:
        typing.cancel()
    if echo:  # the question came from a button: show it above the answer
        reply = f"<i>{fm.esc(text)}</i>\n\n{reply}"
    try:
        await bot.send_message(chat_id, reply, parse_mode="HTML", disable_web_page_preview=True,
                               reply_to_message_id=reply_to, allow_sending_without_reply=True)
    except Exception:  # noqa: BLE001 - e.g. HTML rejected: resend as plain text without markup
        log.warning("html reply rejected chat=%s, resending plain", ref)
        plain = re.sub(r"<[^>]+>", "", reply).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
        await bot.send_message(chat_id, plain, parse_mode=None, reply_to_message_id=reply_to,
                               allow_sending_without_reply=True)


async def cmd_new(message: Message, bot_state: State) -> None:
    user_id = message.from_user.id if message.from_user else None
    bot_state.reset(_conv_key(message.chat.id, user_id))
    await message.answer(fm.agent_failure("new", message.text or ""))


async def on_example(query: CallbackQuery, bot: Bot, backend: BackendClient, bot_state: State,
                     settings: Settings) -> None:
    """Inline example button from /start: ask that question as if the user had typed it."""
    try:
        idx = int((query.data or "").split(":", 1)[1])
        question = fm.EXAMPLES[idx]
    except (IndexError, ValueError):
        await query.answer()
        return
    await query.answer()
    if query.message is None:
        return
    await ask_and_reply(bot, query.message.chat.id, query.from_user.id, question, backend, bot_state, settings,
                        echo=True)


def build_router() -> Router:
    """Fresh router per dispatcher (aiogram routers can be attached only once)."""
    r = Router(name="registry")
    r.message(CommandStart())(cmd_start)
    r.message(Command("new"))(cmd_new)
    r.callback_query(F.data.startswith("ex:"))(on_example)
    r.message(Command("help"))(cmd_help)
    r.message(Command("summary"))(cmd_summary)
    r.message(Command("deal"))(cmd_deal)
    r.message(Command("broker"))(cmd_broker)
    r.message(Command("top_brokers"))(cmd_top_brokers)
    r.message(Command("export"))(cmd_export)
    r.message(F.text, _addressed_text)(free_text)
    return r
