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
    hh = Harness(rate=10_000, delay=backend_delay)
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


QUESTIONS = [
    "2025-yilda jami nechta bitim tuzilgan?", "Какой брокер имел наибольший оборот в 2024 году?",
    "2023-yil mart oyida qaysi tovar eng ko'p sotilgan?", "Сколько сделок аннулировано в 2022?",
    "Banan narxi qancha?", "x" * 5000, "<script>alert(1)</script>", "  ",
]


async def run_agent_load(n: int, latency: float, concurrency: int) -> dict:
    """n users ask at once (private chats); every /agent/ask call takes `latency` seconds."""
    hh = Harness(rate=10, per_day=200, concurrency=concurrency, agent_delay=latency)
    lat: list[float] = []
    exceptions = 0

    async def one(i: int) -> None:
        nonlocal exceptions
        upd = make_update(QUESTIONS[i % len(QUESTIONS)], chat_id=50_000 + i, chat_type="private",
                          user_id=50_000 + i)
        t0 = time.perf_counter()
        try:
            await hh.dp.feed_update(hh.bot, upd)
        except Exception:  # noqa: BLE001
            exceptions += 1
        lat.append(time.perf_counter() - t0)

    t0 = time.perf_counter()
    await asyncio.gather(*(one(i) for i in range(n)))
    wall = time.perf_counter() - t0
    sent = [m for m in hh.session.sent() if isinstance(m, SendMessage)]
    with_source = sum(1 for m in sent if "<b>Manba</b>" in m.text or "<b>Источник</b>" in m.text)
    failures = sum(1 for m in sent if m.text.startswith(("Kechirasiz", "Извините")))
    await hh.close()
    asks = len([c for c in hh.backend_calls if c.url.path.endswith("agent/ask")])
    return {
        "questions": n, "replies": len(sent), "with_source": with_source, "failure_replies": failures,
        "exceptions": exceptions, "agent_calls": asks, "concurrency_cap": concurrency,
        "backend_latency_s": latency, "p50_s": round(statistics.median(lat), 2), "p95_s": round(pct(lat, 95), 2),
        "max_s": round(max(lat), 2), "wall_s": round(wall, 2),
    }


async def test_stress_100_concurrent_questions_2s_backend():
    r = await run_agent_load(100, latency=2.0, concurrency=20)
    print("\nAGENT STRESS 100 x 2 s:", r)
    assert r["exceptions"] == 0
    assert r["replies"] == 100  # every question answered exactly once
    assert r["failure_replies"] == 0
    # 100 questions, cap 20, 2 s each -> 5 waves -> ~10 s worst case, far below the 80 s timeout
    assert r["max_s"] < 15 and r["p95_s"] < 15
