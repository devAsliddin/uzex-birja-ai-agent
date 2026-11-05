"""Text-to-SQL agent: question -> SQL (Gemini) -> read-only execution -> grounded answer."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import hashlib
import sqlite3
import threading
from pathlib import Path
import uuid
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from typing import Any

from app.agent import db as agent_db
from app.agent.grounding import check_grounding, format_rows
from app.agent.prompts import ANSWER_SYSTEM, SQL_RETRY, SQL_SYSTEM
from app.ai.providers.base import BaseProvider
from app.core.config import settings

log = logging.getLogger("app.agent")

NO_DATA = {
    "uz": "Bilmayman — ma'lumotlarda bu haqida ma'lumot yo'q.",
    "ru": "Не знаю — в данных нет такой информации.",
}
NO_DATA_BASIS = {
    "uz": "Ma'lumotlar: birja bitimlari 03.01.2022–30.10.2026 (bitimlar, shartnomalar, ishtirokchilar, brokerlar, USD kursi).",
    "ru": "Данные: сделки биржи 03.01.2022–30.10.2026 (сделки, контракты, участники, брокеры, курс USD).",
}
ERROR_TEXT = {
    "uz": "Javob berib bo'lmadi: texnik xato. Savolni qayta yuboring.",
    "ru": "Не удалось ответить: техническая ошибка. Повторите вопрос.",
}
HELP_TEXT = {
    "uz": ("Men birja bitimlari reyestri (03.01.2022–30.10.2026) bo'yicha savollarga faqat ma'lumotlar asosida javob "
           "beraman: bitimlar soni va aylanmasi (so'm/USD), tovarlar, hududlar, kompaniyalar, brokerlar, holatlar, "
           "muddatlar va dollar kursi.\n"
           "Masalan: «2025-yilda nechta bitim tuzilgan?», «2025-yilda eng ko'p bitim tuzgan broker kim?», "
           "«2025-yilda Farg'ona viloyatida aylanma qancha?»"),
    "ru": ("Я отвечаю на вопросы о реестре биржевых сделок (03.01.2022–30.10.2026) строго по данным: количество и "
           "оборот сделок (сум/USD), товары, регионы, компании, брокеры, состояния, сроки и курс доллара.\n"
           "Например: «Сколько сделок было в 2025 году?», «Какой брокер заключил больше всего сделок в 2025 году?», "
           "«Какой оборот по медному катоду в 2025 году?»"),
}
EXAMPLES = {
    "uz": "Men javob bera oladigan savollar: «2025-yilda nechta bitim tuzilgan?», «2025-yilda eng ko'p bitim tuzgan broker kim?»",
    "ru": "Я могу ответить, например: «Сколько сделок было в 2025 году?», «Какой брокер лидер по сделкам в 2025 году?»",
}
FALLBACK_HEAD ={"uz": "So'rov natijasi:", "ru": "Результат запроса:"}

# provider chain "provider:model,..." (gemini | ollama); first available wins (429/503 -> next)
DEFAULT_CHAIN = (
    "gemini:gemini-3-flash-preview,gemini:gemini-3.5-flash,gemini:gemini-flash-latest,gemini:gemini-3.8-flash,"
    "gemini:gemini-3.1-flash-lite,gemini:gemini-flash-lite-latest,gemini:gemini-3.5-flash-lite"
)


def _env(name: str) -> str | None:
    """Process env first, then backend/.env (pydantic-settings does not export unknown keys to os.environ)."""
    if os.environ.get(name) is not None:
        return os.environ[name]
    try:
        for line in (Path(__file__).resolve().parents[2] / ".env").read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return None


def model_chain() -> list[str]:
    """AI_MODEL_CHAIN: "rules" (default, zero LLM calls), or "rules,gemini:<model>,..." (rules first, LLM for
    questions the rules cannot parse), or "gemini:<model>,ollama:<model>" (LLM only)."""
    raw = (_env("AI_MODEL_CHAIN") or "rules").strip() or "rules"
    if raw == "default":
        raw = DEFAULT_CHAIN
    return [m.strip() if (":" in m or m.strip() == "rules") else f"gemini:{m.strip()}"
            for m in raw.split(",") if m.strip()]


CACHE_PATH = os.environ.get("AGENT_CACHE_PATH", str(Path(__file__).resolve().parents[2] / "agent_cache.sqlite"))
PROMPT_VERSION = hashlib.sha256((SQL_SYSTEM + ANSWER_SYSTEM).encode()).hexdigest()[:12]
MAX_ROWS_UI = 20
MAX_ROWS_LLM = 30


# ---------------------------------------------------------------------------
# language detection
# ---------------------------------------------------------------------------
_UZ_CYR_LETTERS = set("ўқғҳЎҚҒҲ")
_UZ_CYR_WORDS = re.compile(
    r"\b(қанча|канча|нечта|қайси|кайси|ва|бўйича|буйича|йил|йилда|битим\w*|сотувчи|харидор|энг|кўп|жами|ҳажм\w*|"
    r"нима|ким|қаерда|учун|бўлган|бор|йўқ|тонна|сўм)\b",
    re.I,
)
_UZ_LAT_HINT = re.compile(
    r"(o‘|o'|g‘|g'|oʻ|gʻ|sh|ch|\b(qancha|nechta|qaysi|bitim\w*|yil\w*|eng|jami|savdo|sotuvchi|xaridor|bo'yicha|bo‘yicha|"
    r"hajm\w*|necha|kim|nima|uchun|qilgan|bo'lgan|bo‘lgan|tovar|viloyat\w*|summa\w*)\b)",
    re.I,
)


def detect_language(text: str, requested: str = "auto") -> str:
    if requested in ("ru", "uz"):
        return requested
    cyr = sum(1 for ch in text if "Ѐ" <= ch <= "ӿ")
    lat = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    if cyr >= lat:
        if any(ch in _UZ_CYR_LETTERS for ch in text) or len(_UZ_CYR_WORDS.findall(text)) >= 2:
            return "uz"
        return "ru"
    return "uz"


_SMALLTALK = re.compile(
    r"^\W*(salom|assalomu?\s*alaykum|assalom|привет|здравствуй\w*|добрый (день|вечер)|доброе утро|hello|hi|"
    r"rahmat|raxmat|спасибо|благодарю|thanks|xayr|пока|до свидания|"
    r"sen kimsan|siz kimsiz|ты кто|кто ты|вы кто|nima qila olasan|nima qila olasiz|что (ты )?умеешь|"
    r"что ты можешь|помощь|help|yordam)[\s\W]*"
    r"(sen kimsan|siz kimsiz|ты кто|кто ты|nima qila olasan|что умеешь|что ты умеешь)?[\s\W]*$",
    re.I,
)
_GREET = {"uz": "Salom! ", "ru": "Здравствуйте! "}


def is_smalltalk(q: str) -> bool:
    return len(q) < 80 and bool(_SMALLTALK.match(q.strip()))


# obvious out-of-scope questions (answered as no_data without SQL)
_OUT_OF_SCOPE = re.compile(
    r"(погод|ob-?havo|биткоин|bitcoin|криптовалют|kripto|прогноз|prognoz|bashorat|weather|"
    r"лондонск|london metal|lme\b|чикагск|cbot|nyse|nasdaq|акци[ия] компани|anekdot|анекдот)",
    re.I,
)
_YEAR = re.compile(r"\b(19\d\d|20\d\d)\s*(?:-?\s*(?:год\w*|г\.|yil\w*))", re.I)


def obviously_out_of_scope(q: str) -> bool:
    if _OUT_OF_SCOPE.search(q):
        return True
    years = [int(y) for y in _YEAR.findall(q)]
    return bool(years) and all(y < 2022 or y > 2026 for y in years)


# ---------------------------------------------------------------------------
@dataclass
class AgentAnswer:
    answer: str
    language: str
    status: str
    sql: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    row_count: int = 0
    basis: str = ""
    model: str = ""
    latency_ms: int = 0
    tokens: dict[str, Any] = field(default_factory=dict)
    conversation_id: str = ""
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return {}
    return {}


def _jsonable(v: Any) -> Any:
    if isinstance(v, (int, float, str)) or v is None:
        return v
    return str(v)


def _thinking(model: str, role: str) -> dict[str, Any] | None:
    env = os.environ.get(f"AGENT_{role.upper()}_THINKING")
    if env:
        if env == "default":
            return None
        return {"thinkingBudget": int(env)} if env.lstrip("-").isdigit() else {"thinkingLevel": env}
    if model.startswith("gemini-3") or "latest" in model:
        return {"thinkingLevel": "low"} if role == "sql" else {"thinkingLevel": "minimal"}
    return {"thinkingBudget": 1024} if role == "sql" else {"thinkingBudget": 0}


class AgentEngine:
    def __init__(self, provider_factory=None, sql_models: list[str] | None = None,
                 answer_models: list[str] | None = None, cache_path: str | None = None):
        chain = model_chain()
        self.use_rules = sql_models is None and "rules" in chain
        llm_chain = [m for m in chain if m != "rules"]
        self.sql_models = [m.strip() for m in (sql_models or llm_chain) if m.strip()]
        self.answer_models = [m.strip() for m in (answer_models or llm_chain) if m.strip()]
        self.sql_model = self.sql_models[0] if self.sql_models else "rules"
        self._slots: OrderedDict[str, Any] = OrderedDict()
        self._factory = provider_factory or self._make_provider
        self._cache_path = CACHE_PATH if cache_path is None else cache_path
        self._cache_lock = threading.Lock()
        if self._cache_path:
            with sqlite3.connect(self._cache_path) as c:
                c.execute("CREATE TABLE IF NOT EXISTS answers (k TEXT PRIMARY KEY, v TEXT NOT NULL, ts REAL)")
        self._providers: dict[str, BaseProvider] = {}
        self._conversations: OrderedDict[str, list[dict[str, str]]] = OrderedDict()

    @staticmethod
    def _make_provider(entry: str) -> BaseProvider:
        kind, _, model = entry.partition(":")
        if kind == "ollama":
            from app.ai.providers.ollama import OllamaProvider

            return OllamaProvider(model=model, base_url=settings.ollama_base_url)
        from app.ai.providers.gemini import GeminiProvider

        return GeminiProvider(model=model, api_key=settings.gemini_api_key, base_url=settings.gemini_base_url)

    # persistent answer cache (repeated questions cost 0 LLM calls)
    def _cache_get(self, key: str) -> dict[str, Any] | None:
        if not self._cache_path:
            return None
        try:
            with self._cache_lock, sqlite3.connect(self._cache_path, timeout=5) as c:
                row = c.execute("SELECT v FROM answers WHERE k = ?", (key,)).fetchone()
            return json.loads(row[0]) if row else None
        except Exception:
            return None

    def _cache_put(self, key: str, value: dict[str, Any]) -> None:
        if not self._cache_path:
            return
        try:
            with self._cache_lock, sqlite3.connect(self._cache_path, timeout=5) as c:
                c.execute("INSERT OR REPLACE INTO answers (k, v, ts) VALUES (?, ?, ?)",
                          (key, json.dumps(value, ensure_ascii=False), time.time()))
        except Exception:
            log.warning("agent cache write failed")

    def _provider(self, model: str) -> BaseProvider:
        if model not in self._providers:
            self._providers[model] = self._factory(model)
        return self._providers[model]

    async def _llm(self, models, system: str, user: str, tokens: dict[str, int], *, role: str, max_tokens: int):
        """Call the first available model of the chain (free-tier 429/503 -> next model)."""
        if isinstance(models, str):
            models = [models]
        last_exc: Exception | None = None
        resp = None
        for rnd in range(2):
            for model in models:
                prov = self._provider(model)
                kind, _, mname = model.partition(":")
                thinking = _thinking(mname or model, role)
                for _ in range(2):
                    if kind == "ollama":
                        kwargs: dict[str, Any] = {"format": "json"}
                    elif kind == "gemini":
                        kwargs = {"response_mime_type": "application/json", "thinking_config": thinking}
                    else:  # test doubles
                        kwargs = {}
                    try:
                        resp = await prov.chat_completion(
                            [{"role": "system", "content": system}, {"role": "user", "content": user}],
                            temperature=0.0, max_tokens=max_tokens, timeout=45, **kwargs,
                        )
                        break
                    except Exception as exc:
                        last_exc = exc
                        if "HTTP 400" in str(exc) and thinking is not None:
                            thinking = None  # model does not accept this thinking config
                            continue
                        break
                if resp is not None:
                    tokens.setdefault("models", [])  # type: ignore[arg-type]
                    tokens["models"].append(model)  # type: ignore[union-attr]
                    break
            if resp is not None:
                break
            await asyncio.sleep(2.0)
        if resp is None:
            raise RuntimeError(str(last_exc))
        u = resp.usage or {}
        raw_u = (resp.raw or {}).get("usageMetadata", {}) if isinstance(resp.raw, dict) else {}
        tokens["prompt"] = tokens.get("prompt", 0) + int(u.get("prompt_tokens", 0) or 0)
        tokens["completion"] = tokens.get("completion", 0) + int(u.get("completion_tokens", 0) or 0)
        tokens["thinking"] = tokens.get("thinking", 0) + int(raw_u.get("thoughtsTokenCount", 0) or 0)
        tokens["cached"] = tokens.get("cached", 0) + int(raw_u.get("cachedContentTokenCount", 0) or 0)
        tokens["total"] = tokens.get("total", 0) + int(u.get("total_tokens", 0) or 0) + int(
            u.get("prompt_eval_count", 0) or 0) + int(u.get("eval_count", 0) or 0)
        tokens["calls"] = tokens.get("calls", 0) + 1
        return _parse_json(resp.content)

    def _rules_answer(self, question: str, lang: str, t0: float, tokens, turns: str) -> AgentAnswer | None:
        """Zero-LLM path. Returns None only when the question is not understood and an LLM chain exists."""
        from app.agent import rules, rules_sql

        prev = tokens.pop("_prev", None)
        slots, reason = rules.parse(question, prev)
        if slots is None:
            if reason in ("no_metric", "unused_slot") and self.sql_models:
                return None
            res = self._no_data(lang, t0, tokens, hint=reason in ("no_metric", "unused_slot"))
            if reason == "future" and re.search(r"(?i)курс|kurs", question):
                res.answer = NO_DATA[lang] + "\n" + rules_sql.last_rate_line(lang)
            return res
        tokens["engine"] = "rules"
        try:
            sql, basis, fn = rules_sql.build(slots, lang, rules.norm(question))
            result = agent_db.run_query(sql, max_rows=200, timeout_s=20.0)
        except rules_sql.NotFound as nf:
            msg = nf.msg.get(lang) or ""
            res = self._no_data(lang, t0, tokens)
            if msg:
                res.answer = msg
            return res
        text = fn(result.columns, result.rows) if result.rows else None
        text = rules_sql.cap(text) if text else text
        if not text:
            return self._no_data(lang, t0, tokens, [result.sql], basis)
        tokens["_slots"] = slots
        rows_fmt = format_rows(result.columns, result.rows)
        return AgentAnswer(
            answer=text, language=lang, status="ok", sql=[result.sql], columns=result.columns,
            rows=[[_jsonable(v) for v in r] for r in rows_fmt[:MAX_ROWS_UI]], row_count=len(result.rows),
            basis=basis, model="rules (no LLM)", latency_ms=int((time.monotonic() - t0) * 1000), tokens=tokens,
            suggestions=rules_sql.suggestions(slots, lang),
        )

    def _no_data(self, lang: str, t0: float, tokens, sql=None, basis: str | None = None, hint: bool = False) -> AgentAnswer:
        return AgentAnswer(
            answer=NO_DATA[lang] + ("\n" + EXAMPLES[lang] if hint else ""),
            language=lang,
            status="no_data",
            sql=sql or [],
            basis=basis or NO_DATA_BASIS[lang],
            model=self.sql_model,
            latency_ms=int((time.monotonic() - t0) * 1000),
            tokens=tokens,
        )

    async def ask(self, question: str, language: str = "auto", history: list[dict[str, str]] | None = None,
                  conversation_id: str | None = None) -> AgentAnswer:
        t0 = time.monotonic()
        question = (question or "").strip()[:1000]
        lang = detect_language(question, language)
        conv_id = (conversation_id or "")[:64] or uuid.uuid4().hex
        turns = self._history_block(history, conversation_id)
        key = hashlib.sha256(
            "|".join([PROMPT_VERSION, lang, " ".join(question.casefold().split()), turns]).encode()
        ).hexdigest()
        cached = self._cache_get(key)
        if cached:
            res = AgentAnswer(**{**cached, "latency_ms": int((time.monotonic() - t0) * 1000)})
            res.tokens = {**res.tokens, "cache_hit": 1}
        else:
            tokens: dict[str, Any] = {}
            tokens["_prev"] = self._prev_slots(conversation_id, history)
            try:
                res = await self._ask(question, lang, t0, tokens, turns)
            except Exception as exc:
                log.warning("agent error: %s", type(exc).__name__)
                # LLM unavailable (quota/overload) or unusable output -> honest "don't know", never a guess
                res = AgentAnswer(
                    answer=NO_DATA[lang], language=lang, status="no_data", model=self.sql_model,
                    basis=NO_DATA_BASIS[lang],
                    latency_ms=int((time.monotonic() - t0) * 1000), tokens=tokens,
                )
            res.tokens.pop("_prev", None)
            new_slots = res.tokens.pop("_slots", None)
            # rule answers are deterministic and cheap -> not cached (cache would go stale when rules change)
            if res.status in ("ok", "no_data") and res.tokens.get("engine") != "rules" and res.tokens.get("calls"):
                await asyncio.to_thread(self._cache_put, key, res.to_dict())
        res.conversation_id = conv_id
        if cached:
            new_slots = None
        if new_slots is not None:
            self._slots[conv_id] = new_slots
            while len(self._slots) > 2000:
                self._slots.popitem(last=False)
        conv = self._conversations.setdefault(conv_id, [])
        conv.append({"q": question, "sql": res.sql[-1] if res.sql else "", "a": res.answer[:400]})
        del conv[:-6]
        self._conversations.move_to_end(conv_id)
        while len(self._conversations) > 2000:
            self._conversations.popitem(last=False)
        return res

    def _prev_slots(self, conversation_id: str | None, history: list[dict[str, str]] | None):
        if conversation_id and conversation_id in self._slots:
            return self._slots[conversation_id]
        if history:
            from app.agent import rules

            for h in reversed(history):
                if h.get("role") == "user":
                    sl, _ = rules.parse(str(h.get("content", ""))[:1000])
                    if sl is not None:
                        return sl
        return None

    def _history_block(self, history: list[dict[str, str]] | None, conversation_id: str | None) -> str:
        """Prior turns (passed as DATA) for follow-up resolution: stored turns (with SQL) or client history."""
        lines: list[str] = []
        stored = self._conversations.get(conversation_id or "", [])
        if stored:
            for t in stored[-3:]:
                lines.append(f"user: {t['q'][:500]}")
                if t["sql"]:
                    lines.append(f"sql: {t['sql'][:1200]}")
                lines.append(f"assistant: {t['a'][:300]}")
        elif history:
            for h in history[-6:]:
                role = "assistant" if h.get("role") == "assistant" else "user"
                lines.append(f"{role}: {str(h.get('content', ''))[:500]}")
        return "\n".join(lines)

    async def _ask(self, question: str, lang: str, t0: float, tokens: dict[str, Any], turns: str = "") -> AgentAnswer:
        if question and is_smalltalk(question):
            thanks = re.search(r"(?i)rahmat|raxmat|спасибо|благодар|thanks", question)
            greet = ("Arzimaydi! " if lang == "uz" else "Пожалуйста! ") if thanks else _GREET[lang]
            return AgentAnswer(answer=greet + HELP_TEXT[lang], language=lang, status="ok", model="static",
                               latency_ms=int((time.monotonic() - t0) * 1000), tokens=tokens)
        if not question or (not turns and obviously_out_of_scope(question)):
            return self._no_data(lang, t0, tokens)
        if self.use_rules:
            res = await asyncio.to_thread(self._rules_answer, question, lang, t0, tokens, turns)
            if res is not None or not self.sql_models:
                return res or self._no_data(lang, t0, tokens)

        user = f"<history>\n{turns}\n</history>\n" if turns else ""
        user += f"Question ({'Uzbek' if lang == 'uz' else 'Russian'}):\n<question>\n{question}\n</question>"
        plan = await self._llm(self.sql_models, SQL_SYSTEM, user, tokens, role="sql", max_tokens=8192)
        intent = str(plan.get("intent", "data") or "data")
        if intent in ("smalltalk", "help"):
            text = HELP_TEXT[lang]  # static bilingual text: never carries data facts
            return AgentAnswer(answer=text, language=lang, status="ok", model=self.sql_model,
                               latency_ms=int((time.monotonic() - t0) * 1000), tokens=tokens)
        if intent == "out_of_scope" or not plan.get("answerable", True) or not (plan.get("sql") or "").strip():
            return self._no_data(lang, t0, tokens)

        sql_history: list[str] = []
        sql = str(plan.get("sql", ""))
        basis = str(plan.get("basis", "") or "")
        result = None
        for attempt in range(3):
            sql_history.append(sql)
            try:
                result = await asyncio.to_thread(agent_db.run_query, sql, max_rows=200, timeout_s=15.0)
                break
            except Exception as exc:  # validation / sqlite / timeout -> let the model fix it
                err = f"{type(exc).__name__}: {str(exc)[:300]}"
                if attempt == 2:
                    raise RuntimeError("SQL failed") from None
                retry_user = user + "\n\n" + SQL_RETRY.format(error=err, sql=sql)
                plan = await self._llm(self.sql_models, SQL_SYSTEM, retry_user, tokens, role="sql", max_tokens=8192)
                if not plan.get("answerable", True) or not (plan.get("sql") or "").strip():
                    return self._no_data(lang, t0, tokens, sql_history)
                sql = str(plan.get("sql", ""))
                basis = str(plan.get("basis", "") or basis)

        assert result is not None
        cols = result.columns
        raw_rows = result.rows
        if not raw_rows or all(all(v is None for v in r) for r in raw_rows):
            return self._no_data(lang, t0, tokens, sql_history, basis or None)

        rows_fmt = format_rows(cols, raw_rows)
        ui_rows = [[_jsonable(v) for v in r] for r in rows_fmt[:MAX_ROWS_UI]]
        llm_rows = [[_jsonable(v) for v in r] for r in rows_fmt[:MAX_ROWS_LLM]]
        data_blob = json.dumps({"columns": cols, "rows": llm_rows, "total_rows": len(raw_rows),
                                "truncated": result.truncated or len(raw_rows) > MAX_ROWS_LLM}, ensure_ascii=False)
        lang_name = "Uzbek (Latin script)" if lang == "uz" else "Russian"
        ans_user = (
            (f"<history>\n{turns}\n</history>\n" if turns else "")
            + f"<question>\n{question}\n</question>\n<basis>\n{basis}\n</basis>\n"
            f"<result_rows>\n{data_blob}\n</result_rows>"
        )
        system = ANSWER_SYSTEM.format(lang_name=lang_name)
        answer_text = ""
        status = "ok"
        tmpl = render_template(str(plan.get("answer_template", "") or ""), cols, _readable_rows(cols, raw_rows, lang))
        if tmpl and not check_grounding(tmpl, cols, rows_fmt[:MAX_ROWS_LLM] + raw_rows[:MAX_ROWS_LLM], question,
                                        [basis, sql_history[-1]]):
            answer_text = tmpl  # one LLM call total; every value comes straight from the rows
        for attempt in range(0 if answer_text else 2):
            out = await self._llm(self.answer_models, system, ans_user, tokens, role="answer", max_tokens=1024)
            if out.get("no_data") is True:
                return self._no_data(lang, t0, tokens, sql_history, basis or None)
            cand = str(out.get("answer", "") or "").strip()
            if not cand:
                continue
            bad = check_grounding(cand, cols, rows_fmt[:MAX_ROWS_LLM] + raw_rows[:MAX_ROWS_LLM], question,
                                  [basis, sql_history[-1]])
            if not bad:
                answer_text = cand
                break
            log.info("grounding rejected tokens: %s", bad[:5])
            ans_user += (
                "\n\nYour previous answer contained values not present in the rows: "
                + ", ".join(bad[:10])
                + ". Rewrite using only values copied from the rows."
            )
        if not answer_text:
            answer_text = self._deterministic(lang, cols, rows_fmt)
        return AgentAnswer(
            answer=answer_text,
            language=lang,
            status=status,
            sql=sql_history,
            columns=cols,
            rows=ui_rows,
            row_count=len(raw_rows),
            basis=basis,
            model=" + ".join(dict.fromkeys(tokens.get("models", []))) or self.sql_model,  # type: ignore[arg-type]
            latency_ms=int((time.monotonic() - t0) * 1000),
            tokens=tokens,
        )

    @staticmethod
    def _deterministic(lang: str, cols: list[str], rows_fmt: list[list[Any]]) -> str:
        lines = [FALLBACK_HEAD[lang]]
        for r in rows_fmt[:5]:
            lines.append("; ".join(f"{c}: {v}" for c, v in zip(cols, r) if v is not None))
        if len(rows_fmt) > 5:
            lines.append(("Jami qatorlar: " if lang == "uz" else "Всего строк: ") + str(len(rows_fmt)))
        return "\n".join(lines)


_PH = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


_MONEY_COL = re.compile(r"(?i)uzs|usd|amount|total|sum|turnover|price|summa|aylanma|oborot")


def _readable_rows(cols: list[str], rows: list[list[Any]], lang: str) -> list[list[Any]]:
    """Template values: money as '8,69 trln so'm (aniq: ...)', other numbers exact with decimal comma."""
    from app.agent.rules_sql import money1, n

    out = []
    for r in rows:
        row = []
        for i, v in enumerate(r):
            col = cols[i] if i < len(cols) else ""
            if isinstance(v, (int, float)) and not isinstance(v, bool) and _MONEY_COL.search(col):
                row.append(money1(v, lang, usd="usd" in col.lower()))
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                row.append(n(v, col))
            else:
                row.append(v)
        out.append(row)
    return out


def render_template(tmpl: str, cols: list[str], rows_fmt: list[list[Any]]) -> str:
    """Fill {column} placeholders from row 0 and {rows} with a numbered list; '' if unusable."""
    tmpl = tmpl.strip()
    if not tmpl or not rows_fmt:
        return ""
    idx = {c: i for i, c in enumerate(cols)}
    names = _PH.findall(tmpl)

    def cell(name: str) -> Any:
        m = re.fullmatch(r"r(\d+)_c(\d+)", name)
        if m:  # {rN_cM}: row N, column M (0-based)
            ri, ci = int(m.group(1)), int(m.group(2))
            return rows_fmt[ri][ci] if ri < len(rows_fmt) and ci < len(rows_fmt[ri]) else None
        return rows_fmt[0][idx[name]] if name in idx else None

    if not names or any(n != "rows" and cell(n) is None for n in names):
        return ""

    def _list() -> str:
        lines = []
        for i, r in enumerate(rows_fmt[:MAX_ROWS_UI], 1):
            lines.append(f"{i}. " + " — ".join(str(v) for v in r if v is not None))
        return "\n" + "\n".join(lines) + "\n"

    out = _PH.sub(lambda m: _list() if m.group(1) == "rows" else str(cell(m.group(1))), tmpl)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


_engine: AgentEngine | None = None


def get_agent() -> AgentEngine:
    global _engine
    if _engine is None:
        _engine = AgentEngine()
    return _engine
