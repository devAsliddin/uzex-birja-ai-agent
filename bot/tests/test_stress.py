"""Stress tests: many concurrent updates through the real dispatcher with a mocked backend.

Run with `-s` to see the latency report.
"""

from __future__ import annotations

import asyncio
import random
import statistics
import time

from aiogram.methods import SendDocument, SendMessage

from conftest import BOT_USERNAME, GENERIC_ERR_TEXT, Harness, make_update

CHATS = [-1001000000000 - i for i in range(20)]
INPUTS = [
    "/summary 2025", "/summary", "/deal 1234567", "/deal 42", "/deal abc", "/broker BK001",
    "/broker BK404", "/broker xx", "/top_brokers", "/top_brokers 2024", "/help",
    f"@{BOT_USERNAME} eng katta bitim qaysi?", "/export 01.13.2025 01.01.2026",
    "/deal " + "9" * 5000, "/broker " + "\u0000" * 50, f"@{BOT_USERNAME} " + "x" * 10_000,
]


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


async def run_load(n: int, backend_delay: float) -> dict:
    hh = Harness(allowed=CHATS, rate=10_000, delay=backend_delay)
    rnd = random.Random(7)
    lat: list[float] = []
    errors = 0

    async def one(i: int) -> None:
        nonlocal errors
        upd = make_update(rnd.choice(INPUTS), chat_id=CHATS[i % len(CHATS)], user_id=10_000 + i)
        t0 = time.perf_counter()
        try:
            await hh.dp.feed_update(hh.bot, upd)
        except Exception:  # noqa: BLE001
            errors += 1
        lat.append((time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    await asyncio.gather(*(one(i) for i in range(n)))
    wall = time.perf_counter() - t0
    sent = hh.session.sent()
    generic = sum(1 for m in sent if isinstance(m, SendMessage) and m.text == GENERIC_ERR_TEXT)
    await hh.close()
    return {
        "updates": n, "replies": len(sent), "exceptions": errors, "generic_errors": generic,
        "p50_ms": round(statistics.median(lat), 1), "p95_ms": round(pct(lat, 95), 1),
        "max_ms": round(max(lat), 1), "wall_s": round(wall, 2), "rps": round(n / wall, 1),
        "backend_calls": len(hh.backend_calls),
    }


async def test_stress_200_concurrent():
    r = await run_load(200, backend_delay=0.02)  # 20 ms simulated backend latency
    print("\nSTRESS 200:", r)
    assert r["exceptions"] == 0
    assert r["generic_errors"] == 0
    assert r["replies"] == 200  # every update answered exactly once
    assert r["p95_ms"] < 1000


async def test_stress_2000_concurrent():
    r = await run_load(2000, backend_delay=0.02)
    print("\nSTRESS 2000:", r)
    assert r["exceptions"] == 0 and r["generic_errors"] == 0
    assert r["replies"] == 2000


async def test_flood_single_chat_rate_limited():
    hh = Harness(rate=20)
    try:
        await asyncio.gather(*(hh.dp.feed_update(hh.bot, make_update("/summary 2025")) for _ in range(300)))
        sent = hh.session.sent()
        answers = [m for m in sent if isinstance(m, SendMessage) and m.text.startswith("Jami aylanma")]
        warns = [m for m in sent if isinstance(m, SendMessage) and m.text.startswith("So'rovlar juda ko'p")]
        print(f"\nFLOOD 300 msgs/1 chat: answered={len(answers)} warned={len(warns)} "
              f"backend_calls={len(hh.backend_calls)}")
        assert len(answers) == 20 and len(warns) == 1
        assert len(hh.backend_calls) == 40  # 2 calls (UZS+USD) per allowed request only
    finally:
        await hh.close()


async def test_concurrent_exports_cooldown():
    hh = Harness()
    try:
        await asyncio.gather(
            *(hh.dp.feed_update(hh.bot, make_update("/export 01.01.2025 31.01.2025")) for _ in range(20))
        )
        docs = [m for m in hh.session.sent() if isinstance(m, SendDocument)]
        print(f"\nEXPORT x20 same chat: files_sent={len(docs)}")
        assert len(docs) <= 2  # cooldown prevents export storms
    finally:
        await hh.close()
