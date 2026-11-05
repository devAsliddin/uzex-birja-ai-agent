"""Smoke tests: every command returns the right format with a mocked backend."""

from __future__ import annotations

from aiogram.methods import SendDocument, SendMessage

from conftest import BOT_USERNAME, GROUP_ID, Harness


def one_text(out) -> str:
    msgs = [m for m in out if isinstance(m, SendMessage)]
    assert len(msgs) == 1, out
    return msgs[0].text


async def test_help_and_start(h):
    for cmd in ("/start", "/help", f"/help@{BOT_USERNAME}"):
        t = one_text(await h.send(cmd))
        assert t.startswith("Birja reyestri boti — buyruqlar:")
        for c in ("/summary", "/deal", "/broker", "/top_brokers", "/export"):
            assert c in t


async def test_summary_year(h):
    t = one_text(await h.send("/summary 2025"))
    first = t.splitlines()[0]
    assert first == "Jami aylanma (2025): 146,2 trln so'm ($11,6 mlrd). Bitimlar: 115 763."
    assert "USD kursi: 12 650,50 so'm (30.10.2026)." in t
    assert "1. г. Ташкент — 23,8%, 34,8 trln so'm, 27 000 bitim" in t
    assert "Top kategoriyalar:" in t and "3. Зерно" in t
    assert "Other" not in t  # only top-3 regions
    paths = {(c.url.path, c.url.params.get("currency"), c.url.params.get("year")) for c in h.backend_calls}
    assert ("/api/v1/analytics/summary", "UZS", "2025") in paths
    assert ("/api/v1/analytics/summary", "USD", "2025") in paths


async def test_summary_all_years_and_bad_year(h):
    assert one_text(await h.send("/summary")).startswith("Jami aylanma (2025–2025)")
    assert one_text(await h.send("/summary abc")).startswith("Yil noto'g'ri")


async def test_deal_card(h):
    t = one_text(await h.send(f"/deal@{BOT_USERNAME} 1234567"))
    lines = t.splitlines()
    assert lines[0].startswith("Bitim №1234567: 1,2 mlrd so'm ($96 899), holati — Bajarilgan.")
    assert "Tovar: Цемент Марка М400" in t
    assert "Hajm: 10 lot × 20 тонна = 200 тонна" in t
    assert "Sana: 14.03.2025 10:15; Spot, Ichki, Ingliz auksioni" in t
    assert "Sotuvchi: OOO Sement Savdo, STIR 301234567" in t
    assert "Xaridor: OOO Qurilish Plus" in t
    assert "BK001 — Broker One" in t and "BK017 — Broker Seventeen" in t
    assert "To'lov: 16.03.2025; yetkazish: 25.03.2025 (10/10 lot yetkazilgan)" in t


async def test_deal_validation_and_404(h):
    assert one_text(await h.send("/deal abc")).startswith("Bitim raqami faqat raqamlardan")
    assert one_text(await h.send("/deal 1; DROP TABLE")).startswith("Bitim raqami faqat raqamlardan")
    assert one_text(await h.send("/deal 999")) == "Bitim №999 topilmadi."


async def test_broker(h):
    t = one_text(await h.send("/broker bk001"))
    assert t.splitlines()[0] == "BK001 — Broker One: reyting 3/120, 8 123 bitim, aylanma 9,4 trln so'm."
    assert "Sotuvchi tomonida: 5 000, xaridor tomonida: 3 123 bitim." in t
    assert one_text(await h.send("/broker BK1")).startswith("Broker kodi BK")
    assert one_text(await h.send("/broker ../admin")).startswith("Broker kodi BK")
    assert one_text(await h.send("/broker BK999")) == "Broker BK999 topilmadi."


async def test_top_brokers(h):
    t = one_text(await h.send("/top_brokers"))
    lines = t.splitlines()
    assert lines[0].startswith("Top-10 broker (barcha yillar). 1-o'rin: BK001 — Broker 1")
    assert len(lines) == 11
    t2 = one_text(await h.send("/top_brokers 2025"))
    assert "Eslatma: backend yil bo'yicha filtrni qo'llamadi" in t2


async def test_export_ok(h):
    out = await h.send("/export 01.01.2025 31.01.2025 bajarilgan")
    docs = [m for m in out if isinstance(m, SendDocument)]
    assert len(docs) == 1
    assert docs[0].caption == "Bitimlar: 2. Davr: 01.01.2025–31.01.2025. Holat: Bajarilgan. Format: CSV."
    assert docs[0].document.filename == "bitimlar_20250101_20250131_bajarilgan.csv"
    exp = [c for c in h.backend_calls if c.url.path.endswith("export/deals")][0]
    assert exp.url.params["status"] == "Исполнен" and exp.url.params["start_date"] == "2025-01-01"
    # cooldown
    assert one_text(await h.send("/export 01.01.2025 31.01.2025")).startswith("Eksport har 30 soniyada")


async def test_export_validation():
    hh = Harness(deal_total=999_999)
    try:
        assert one_text(await hh.send("/export")).startswith("Format: /export")
        assert one_text(await hh.send("/export 32.01.2025 01.02.2025")).startswith("Sana noto'g'ri")
        assert one_text(await hh.send("/export 02.02.2025 01.02.2025")).startswith("Boshlanish sanasi")
        assert one_text(await hh.send("/export 01.01.2025 02.01.2025 foo")).startswith("Noma'lum parametr")
        t = one_text(await hh.send("/export 01.01.2022 30.10.2026 xlsx"))
        assert "999 999 bitim — chegaradan ko'p (20 000)" in t
        assert not [c for c in hh.backend_calls if c.url.path.endswith("export/deals")]
    finally:
        await hh.close()


async def test_free_text_group_rules(h):
    # plain group chatter is ignored
    assert await h.send("salom hammaga") == []
    # mention -> AI, mention stripped, text passed as data
    t = one_text(await h.send(f"@{BOT_USERNAME} 2025 da eng katta region?"))
    assert t == "AI javob: 2025 da eng katta region?"
    # reply to bot -> AI
    assert one_text(await h.send("yana?", reply_to_bot=True)) == "AI javob: yana?"


async def test_free_text_ai_down():
    hh = Harness(ai_status=404)
    try:
        t = one_text(await hh.send(f"@{BOT_USERNAME} savol"))
        assert t.startswith("Birja reyestri boti") and "Erkin savollar hozircha mavjud emas" in t
        ai_calls = len([c for c in hh.backend_calls if c.url.path.endswith("ai/chat")])
        await hh.send(f"@{BOT_USERNAME} yana savol")  # circuit open: no second backend call
        assert len([c for c in hh.backend_calls if c.url.path.endswith("ai/chat")]) == ai_calls
    finally:
        await hh.close()


async def test_unauthorized_chat():
    hh = Harness(allowed=())
    try:
        t = one_text(await hh.send("/summary"))
        assert t.startswith("Bu chat uchun ruxsat yo'q. Chat ID: -1001234567890")
        assert not hh.backend_calls  # no data leaves
        assert await hh.send("/summary") == []  # refusal cooldown, no spam
        assert one_text(await hh.send("/chatid")).startswith(f"Chat ID: {GROUP_ID}")
        assert await hh.send("oddiy gap") == []
    finally:
        await hh.close()


async def test_rate_limit():
    hh = Harness(rate=3)
    try:
        for _ in range(3):
            assert one_text(await hh.send("/help")).startswith("Birja")
        assert one_text(await hh.send("/help")).startswith("So'rovlar juda ko'p")
        assert await hh.send("/help") == []  # warned once per window
        # other chats are unaffected
    finally:
        await hh.close()


async def test_backend_down_generic_error():
    import httpx

    hh = Harness()

    def boom(request):
        raise httpx.ConnectError("refused")

    hh.backend._client._transport = httpx.MockTransport(boom)
    try:
        t = one_text(await hh.send("/summary 2025"))
        assert t == "Ma'lumot manbasi hozir javob bermayapti. Birozdan keyin qayta urinib ko'ring."
    finally:
        await hh.close()


async def test_free_text_without_api_key_no_ai_call():
    hh = Harness(ai_key="")
    try:
        t = one_text(await hh.send(f"@{BOT_USERNAME} savol"))
        assert "Erkin savollar hozircha mavjud emas" in t
        assert not [c for c in hh.backend_calls if c.url.path.endswith("ai/chat")]
        # key is never sent on public data endpoints
        await hh.send("/summary 2025")
        assert all("x-api-key" not in c.headers for c in hh.backend_calls)
    finally:
        await hh.close()
