"""UZEX AI Engine.

Orchestrates:
- system prompt (versioned, from DB with file fallback)
- conversation context
- deterministic read-only tool selection + execution (grounding)
- LLM provider for answer composition

The engine never lets the LLM invent deal facts: every factual claim must come
from a tool result backed by PostgreSQL.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from app.ai.context import ConversationContext
from app.ai.providers.base import LLMMessage, LLMResponse
from app.ai.providers.registry import create_provider
from app.ai.tools.registry import ToolRegistry
from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_read_session


def _load_system_prompt() -> str:
    """Load system prompt from the bundled file (single source of truth)."""
    path = Path(__file__).resolve().parent.parent / "prompts" / "system_prompt.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "Ты — UZEX AI. Отвечай только на основе проверенных данных из базы."


class AIEngine:
    def __init__(self) -> None:
        self.provider = create_provider()
        self.registry = ToolRegistry()
        self.system_prompt = _load_system_prompt()
        self._router = _IntentRouter()

    async def close(self) -> None:
        await self.provider.close()

    async def process_message(
        self,
        message: str,
        *,
        language: str = "ru",
        conversation_id: int | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        """Process a user message and return a grounded answer."""
        ctx = ConversationContext(
            conversation_id=conversation_id,
            user_id=user_id,
            language=language,
            system_prompt=self.system_prompt,
        )
        ctx.add_user_message(message)

        tool_calls: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []

        plan = self._router.route(message)
        async for db in get_read_session():
            for tool_name, params in plan:
                tool = self.registry.get(tool_name)
                if tool is None:
                    logger.warning("Unknown tool requested: %s", tool_name)
                    continue
                result = await tool.execute(db, params)
                tool_calls.append({"tool": tool_name, "params": params})
                if result.ok:
                    tool_results.append(
                        {"tool": tool_name, "data": result.data, "latency_ms": result.latency_ms}
                    )
                else:
                    tool_results.append(
                        {"tool": tool_name, "error": result.error, "latency_ms": result.latency_ms}
                    )
            break

        answer = await self._compose(message, language, tool_results)

        ctx.add_assistant_message(answer)
        return {
            "response": answer,
            "language": language,
            "conversation_id": conversation_id,
            "tool_calls": tool_calls,
            "tool_results": tool_results,
        }

    async def _compose(
        self,
        user_message: str,
        language: str,
        tool_results: list[dict[str, Any]],
    ) -> str:
        if not tool_results:
            return self._unknown_answer(language)

        facts = self._summarize_results(tool_results, language)

        compose_prompt = (
            "Ты — UZEX AI. Составь ответ на вопрос пользователя ТОЛЬКО на основе приведённых ниже "
            "проверенных фактов из базы данных. Не выдумывай ничего. Если фактов недостаточно, "
            "скажи честно, что информации нет. Отвечай на языке пользователя.\n\n"
            f"Язык пользователя: {language}\n"
            f"Вопрос пользователя: {user_message}\n\n"
            f"Проверенные факты:\n{facts}\n"
        )

        messages: list[LLMMessage] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": compose_prompt},
        ]
        try:
            resp: LLMResponse = await self.provider.chat_completion(
                messages,
                temperature=settings.ai_temperature,
                max_tokens=settings.ai_max_tokens,
                timeout=settings.ai_timeout_seconds,
            )
            content = (resp.content or "").strip()
            if not content:
                return self._unknown_answer(language)
            return content
        except Exception as exc:
            logger.error("LLM composition failed: %s", exc)
            return self._fallback_summary(tool_results, language)

    def _summarize_results(self, tool_results: list[dict[str, Any]], language: str) -> str:
        lines: list[str] = []
        for tr in tool_results:
            tool = tr["tool"]
            if "error" in tr:
                lines.append(f"- {tool}: ошибка — {tr['error']}")
                continue
            data = tr.get("data") or {}
            lines.append(f"- {tool}: {self._format_data(data, language)}")
        return "\n".join(lines)

    @staticmethod
    def _format_data(data: dict[str, Any], language: str) -> str:
        parts: list[str] = []
        for key, value in data.items():
            if value is None:
                continue
            if isinstance(value, list):
                parts.append(f"{key}: {len(value)} записей")
            else:
                parts.append(f"{key}={value}")
        return "; ".join(parts) if parts else "пусто"

    def _unknown_answer(self, language: str) -> str:
        if language == "uz":
            return (
                "Bu savolga javobni bilmayman. "
                "Mavjud ma'lumotlarda ishonchli javob berish uchun yetarli axborot yo'q."
            )
        return (
            "Я не знаю ответа на этот вопрос. "
            "В доступных данных нет достаточной информации, чтобы достоверно ответить."
        )

    def _fallback_summary(self, tool_results: list[dict[str, Any]], language: str) -> str:
        if not tool_results:
            return self._unknown_answer(language)
        lines = [
            self._format_data(tr.get("data") or {}, language)
            for tr in tool_results
            if "error" not in tr
        ]
        if language == "uz":
            return "Mavjud ma'lumotlar bo'yicha: " + " | ".join(lines)
        return "По доступным данным: " + " | ".join(lines)


class _IntentRouter:
    """Deterministic, keyword-based tool selection.

    Keeps the AI grounded: tools are chosen by explicit user intent, not by
    asking the LLM to guess. Provider-agnostic.
    """

    def route(self, message: str) -> list[tuple[str, dict[str, Any]]]:
        text = message
        low = text.lower()
        plans: list[tuple[str, dict[str, Any]]] = []

        m = re.search(r"(?:сделк[ае]\s*(?:№|N|#)?\s*(\d+)|deal\s*(?:№|#)?\s*(\d+))", low)
        if m:
            num = int(m.group(1) or m.group(2))
            plans.append(("get_deal_details", {"deal_number": num}))

        m = re.search(r"(?:контракт[ае]?\s*(?:№|N|#)?\s*(\d+)|contract\s*(?:№|#)?\s*(\d+))", low)
        if m:
            plans.append(("get_contract_details", {"contract_number": m.group(1) or m.group(2)}))

        m = re.search(r"\b(BK\d{3})\b", text.upper())
        if m:
            plans.append(("get_broker_details", {"broker_code": m.group(1)}))

        m = re.search(r"\b(\d{9})\b", text)
        if m:
            plans.append(("get_participant_details", {"inn": m.group(1)}))

        if any(w in low for w in ["брокер", "broker"]) and not plans:
            plans.append(("search_brokers", {"query": text, "limit": 10}))
        if any(w in low for w in ["участник", "компани", "participant", "инн"]) and not plans:
            plans.append(("search_participants", {"query": text, "limit": 10}))
        if any(w in low for w in ["контракт", "contract"]) and not plans:
            plans.append(("search_contracts", {"query": text, "limit": 10}))
        if any(w in low for w in ["сделк", "deal", "bitim"]) and not plans:
            plans.append(("search_deals", {"query": text, "limit": 10}))

        if any(w in low for w in ["курс", "доллар", "usd", "сум за", "exchange"]):
            m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
            if m:
                plans.append(("get_exchange_rate", {"date": f"{m.group(1)}-{m.group(2)}-{m.group(3)}"}))
            else:
                plans.append(("get_dataset_information", {}))

        if any(w in low for w in ["объём", "объем", "volume", "количество × лот", "х"]):
            m = re.search(r"(\d+)\s*[хx×]\s*(\d+)", text)
            if m:
                plans.append(("calculate_deal_volume", {"quantity": int(m.group(1)), "lot_size": int(m.group(2))}))
        if any(w in low for w in ["цена за единицу", "unit price"]):
            plans.append(("calculate_unit_price", {"amount": 0, "quantity": 1, "lot_size": 1}))
        if any(w in low for w in ["сумма в сумах", "amount uzs", "uzs"]):
            m = re.search(r"(\d+(?:\.\d+)?)\s*(?:USD|usd|\$)", text)
            if m:
                plans.append(("calculate_amount_uzs", {"amount_usd": float(m.group(1)), "date": date.today().isoformat()}))

        if any(w in low for w in ["топ брокер", "top broker"]):
            plans.append(("get_top_brokers", {"limit": 10}))
        if any(w in low for w in ["топ товар", "top product"]):
            plans.append(("get_top_products", {"limit": 10}))
        if any(w in low for w in ["статистика сделок", "deal statistics"]):
            plans.append(("get_deal_statistics", {}))
        if any(w in low for w in ["информация о наборе", "dataset information", "сколько записей"]):
            plans.append(("get_dataset_information", {}))

        m = re.search(r"(\d{4})-(\d{2})-(\d{2})\s*[-–]\s*(\d{4})-(\d{2})-(\d{2})", text)
        if m:
            plans.append((
                "compare_periods",
                {
                    "period_from": f"{m.group(1)}-{m.group(2)}-{m.group(3)}",
                    "period_to": f"{m.group(4)}-{m.group(5)}-{m.group(6)}",
                },
            ))

        seen: set[str] = set()
        unique: list[tuple[str, dict[str, Any]]] = []
        for name, params in plans:
            if name in seen:
                continue
            seen.add(name)
            unique.append((name, params))
        return unique
