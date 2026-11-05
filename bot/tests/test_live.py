"""Live smoke test: real dispatcher + REAL backend (read-only calls), fake Telegram.

Run: set LIVE_BACKEND=http://127.0.0.1:8000/api/v1 ; pytest tests/test_live.py -s
"""

from __future__ import annotations

import os
import time

import pytest
from aiogram import Bot
from aiogram.methods import SendDocument, SendMessage

from app.backend import BackendClient
from app.config import Settings
from app.main import build_dispatcher
from conftest import FAKE_TOKEN, GROUP_ID, FakeSession, make_update

LIVE = os.getenv("LIVE_BACKEND")
pytestmark = pytest.mark.skipif(not LIVE, reason="set LIVE_BACKEND to run against the real backend")

CASES = [
    ("/summary 2025", "Jami aylanma (2025):"),
    ("/summary", "Jami aylanma ("),
    ("/top_brokers", "Top-10 broker"),
    ("/broker BK001", "BK001 — "),
    ("/broker BK999", "Broker BK999 topilmadi."),
    ("/deal 1", None),  # exists or "topilmadi" — both fine
    ("/export 01.01.2025 02.01.2025 bajarilgan", "FILE"),
]


async def test_live_smoke():
    settings = Settings(bot_token=FAKE_TOKEN, backend_url=LIVE, allowed_chat_ids=frozenset({GROUP_ID}),
                        rate_limit_per_min=1000)
    backend = BackendClient(LIVE, timeout=60)
    session = FakeSession()
    bot = Bot(FAKE_TOKEN, session=session)
    dp = build_dispatcher(settings, backend)
    # pick a real deal number for the card check
    first = (await backend._get("deals", {"limit": 1, "start_date": "2025-03-01", "end_date": "2025-03-15"}))
    deal_no = first["items"][0]["deal_no"]
    cases = CASES + [(f"/deal {deal_no}", f"Bitim №{deal_no}:")]
    try:
        for text, expect in cases:
            before = len(session.sent())
            t0 = time.perf_counter()
            await dp.feed_update(bot, make_update(text))
            ms = (time.perf_counter() - t0) * 1000
            out = session.sent()[before:]
            assert len(out) == 1, (text, out)
            m = out[0]
            body = m.caption if isinstance(m, SendDocument) else m.text
            print(f"\n=== {text}  ({ms:.0f} ms)\n{body}")
            if expect == "FILE":
                assert isinstance(m, SendDocument), body
                print(f"[file {m.document.filename}, {len(m.document.data)} bytes]")
            elif expect:
                assert isinstance(m, SendMessage) and m.text.startswith(expect), body
            assert "Ma'lumot manbasi hozir javob bermayapti" not in body
    finally:
        await backend.close()
