"""Test harness: fake Telegram session (records outgoing calls) + mocked backend (httpx.MockTransport)."""

from __future__ import annotations

import asyncio
import itertools
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import GetMe, SendDocument, SendMessage, TelegramMethod
from aiogram.types import Chat, Message, Update, User

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.backend import BackendClient  # noqa: E402
from app.config import Settings  # noqa: E402
from app.handlers import GENERIC_ERR as GENERIC_ERR_TEXT  # noqa: E402,F401
from app.main import build_dispatcher  # noqa: E402

BOT_ID = 777
BOT_USERNAME = "birja_reyestr_bot"
GROUP_ID = -1001234567890
FAKE_TOKEN = "123456:" + "A" * 35

# --------------------------------------------------------------------------- fixtures data
SUMMARY_UZS = {
    "year": 2025, "currency": "UZS", "total_turnover": 146_200_000_000_000.0, "deals_count": 115_763,
    "broker_count": 120, "usd_rate": {"date": "2026-10-30", "rate": 12650.5},
    "yearly": [{"year": 2025, "deals_count": 115_763, "turnover": 146_200_000_000_000.0}],
    "monthly": [],
    "regions": [
        {"region": "г. Ташкент", "deals_count": 27000, "turnover": 34_800_000_000_000.0, "share_pct": 23.8},
        {"region": "Навоийская обл.", "deals_count": 9000, "turnover": 15_100_000_000_000.0, "share_pct": 10.3},
        {"region": "Ферганская обл.", "deals_count": 8000, "turnover": 11_000_000_000_000.0, "share_pct": 7.5},
        {"region": "Other", "deals_count": 1, "turnover": 1.0, "share_pct": 0.0},
    ],
    "top_categories": [
        {"category": "Нефтепродукты", "deals_count": 30000, "turnover": 40_000_000_000_000.0},
        {"category": "Металлы", "deals_count": 20000, "turnover": 25_000_000_000_000.0},
        {"category": "Зерно", "deals_count": 15000, "turnover": 10_000_000_000_000.0},
    ],
}
SUMMARY_USD = {**SUMMARY_UZS, "currency": "USD", "total_turnover": 11_560_000_000.0}

DEAL = {
    "deal_no": 1234567, "deal_date": "2025-03-14", "deal_time": "10:15:00", "trade_type": "Английский аукцион",
    "quantity": 10, "amount": 1_250_000_000.0, "currency": "Узбекский сум", "amount_uzs": 1_250_000_000.0,
    "start_price": 6_000_000.0, "lot_size": 20.0, "unit": "тонна", "volume": 200.0,
    "product_name": "Цемент Марка М400", "region": "Ташкентская обл.", "contract_no": "C-001",
    "contract_type": "Внутренний", "contract_form": "Спот", "status": "Исполнен",
    "payment_date": "2025-03-16", "delivery_date": "2025-03-25", "delivered_lots": 10,
    "usd_rate": {"requested_date": "2025-03-14", "rate_date": "2025-03-14", "rate": 12900.0, "exact": True},
    "contract": {"product_category": "Стройматериалы"},
    "seller": {"inn": "301234567", "name": "OOO Sement Savdo", "region": "Ташкентская обл."},
    "buyer": {"inn": "309876543", "name": "OOO Qurilish Plus", "region": "г. Ташкент"},
    "seller_broker": {"code": "BK001", "name": "Broker One", "inn": "1", "region": "x"},
    "buyer_broker": {"code": "BK017", "name": "Broker Seventeen", "inn": "2", "region": "y"},
}

BROKER = {
    "broker_code": "BK001", "name": "Broker One", "inn": "200000001", "region": "г. Ташкент",
    "rating": {"rank": 3, "of": 120},
    "stats": {
        "deals_count": 8123, "deals_as_seller_broker": 5000, "deals_as_buyer_broker": 3123,
        "turnover_uzs": 9_400_000_000_000.0, "avg_deal_uzs": 1_157_000_000.0,
        "by_status": [{"status": "Исполнен", "deals_count": 6000, "turnover_uzs": 1.0},
                      {"status": "Аннулирован(Не оплачен)", "deals_count": 500, "turnover_uzs": 1.0}],
    },
}

BROKERS = {
    "items": [
        {"broker_code": f"BK{i:03d}", "name": f"Broker {i}", "inn": "1", "region": "г. Ташкент",
         "deals_count": 1000 - i, "turnover_uzs": 10_000_000_000_000.0 - i * 1e11, "rating": i}
        for i in range(1, 11)
    ],
    "total": 120, "page": 1, "limit": 10, "pages": 12,
}

CSV_BYTES = "deal_no,deal_date\n1,2025-01-01\n".encode()


def make_backend_handler(*, deal_total: int = 2, ai_status: int = 200, delay: float = 0.0):
    calls: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if delay:
            await asyncio.sleep(delay)
        p = request.url.path.removeprefix("/api/v1/")
        q = request.url.params
        if p == "analytics/summary":
            return httpx.Response(200, json=SUMMARY_USD if q.get("currency") == "USD" else SUMMARY_UZS)
        if p == "deals/1234567":
            return httpx.Response(200, json=DEAL)
        if p.startswith("deals/"):
            return httpx.Response(404, json={"detail": "not found"})
        if p == "deals":
            return httpx.Response(200, json={"items": [], "total": deal_total, "page": 1, "limit": 1, "pages": 1})
        if p == "brokers/BK001":
            return httpx.Response(200, json=BROKER)
        if p.startswith("brokers/"):
            return httpx.Response(404, json={"detail": "not found"})
        if p == "brokers":
            return httpx.Response(200, json=BROKERS)
        if p == "export/deals":
            return httpx.Response(200, content=CSV_BYTES, headers={"content-type": "text/csv"})
        if p == "ai/chat":
            if request.headers.get("X-API-Key") != "test-key":
                return httpx.Response(401, json={"error": "unauthorized"})
            if ai_status != 200:
                return httpx.Response(ai_status, json={"detail": "x"})
            body = json.loads(request.content)
            return httpx.Response(200, json={"response": f"AI javob: {body['message']}", "language": "uz",
                                             "conversation_id": 1})
        return httpx.Response(500)

    return handler, calls


# --------------------------------------------------------------------------- fake telegram
class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod] = []
        self._ids = itertools.count(1000)

    async def make_request(self, bot: Bot, method: TelegramMethod, timeout: int | None = None) -> Any:
        self.requests.append(method)
        if isinstance(method, GetMe):
            return User(id=BOT_ID, is_bot=True, first_name="Birja", username=BOT_USERNAME)
        if isinstance(method, (SendMessage, SendDocument)):
            return Message(
                message_id=next(self._ids), date=datetime.now(),
                chat=Chat(id=method.chat_id, type="group"),
                text=getattr(method, "text", None),
            )
        return True

    async def close(self) -> None:  # pragma: no cover
        pass

    async def stream_content(self, *a: Any, **kw: Any):  # pragma: no cover
        yield b""

    def sent(self, chat_id: int | None = None) -> list[TelegramMethod]:
        return [r for r in self.requests if isinstance(r, (SendMessage, SendDocument))
                and (chat_id is None or r.chat_id == chat_id)]


_upd = itertools.count(1)


def make_update(text: str, chat_id: int = GROUP_ID, chat_type: str = "supergroup",
                reply_to_bot: bool = False, user_id: int = 4242) -> Update:
    reply = None
    if reply_to_bot:
        reply = Message(message_id=1, date=datetime.now(), chat=Chat(id=chat_id, type=chat_type),
                        from_user=User(id=BOT_ID, is_bot=True, first_name="Birja"), text="prev")
    n = next(_upd)
    return Update(
        update_id=n,
        message=Message(
            message_id=n, date=datetime.now(), chat=Chat(id=chat_id, type=chat_type, title="Test"),
            from_user=User(id=user_id, is_bot=False, first_name="U"), text=text, reply_to_message=reply,
        ),
    )


class Harness:
    def __init__(self, *, allowed=(GROUP_ID,), rate=1000, ai_key: str = "test-key", **backend_kw: Any) -> None:
        handler, self.backend_calls = make_backend_handler(**backend_kw)
        self.settings = Settings(bot_token=FAKE_TOKEN, backend_url="http://backend.test/api/v1",
                                 allowed_chat_ids=frozenset(allowed), rate_limit_per_min=rate)
        self.backend = BackendClient(self.settings.backend_url, ai_api_key=ai_key,
                                     transport=httpx.MockTransport(handler))
        self.session = FakeSession()
        self.bot = Bot(FAKE_TOKEN, session=self.session)
        self.dp = build_dispatcher(self.settings, self.backend)

    async def send(self, text: str, **kw: Any) -> list[TelegramMethod]:
        before = len(self.session.sent())
        await self.dp.feed_update(self.bot, make_update(text, **kw))
        return self.session.sent()[before:]

    async def close(self) -> None:
        await self.backend.close()


@pytest.fixture
async def h():
    harness = Harness()
    yield harness
    await harness.close()
