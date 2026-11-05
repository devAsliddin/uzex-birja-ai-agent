"""Smoke tests: every command returns the right format with a mocked backend."""

from __future__ import annotations

import asyncio
import html
import json
import time

from aiogram.methods import AnswerCallbackQuery, SendChatAction, SendDocument, SendMessage

from app.formatting import EXAMPLES
from conftest import AGENT_ERROR, AGENT_NO_DATA, AGENT_OK, BOT_USERNAME, GROUP_ID, Harness, make_callback


def one_text(out) -> str:
    msgs = [m for m in out if isinstance(m, SendMessage)]
    assert len(msgs) == 1, out
    return msgs[0].text


async def test_help_and_start(h):
    for cmd in ("/help", f"/help@{BOT_USERNAME}"):
        t = one_text(await h.send(cmd))
        assert t.startswith("Birja reyestri boti — buyruqlar")
        for c in ("/summary", "/deal", "/broker", "/top_brokers", "/export", "/new"):
            assert c in t
    t = one_text(await h.send("/start", chat_id=555, chat_type="private"))
    assert "2022–2026" in t and "ma'lumotlar asosida" in t and "строго по данным" in t


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


def one_msg(out) -> SendMessage:
    msgs = [m for m in out if isinstance(m, SendMessage)]
    assert len(msgs) == 1, out
    return msgs[0]


def asks(hh) -> list[dict]:
    return [json.loads(c.content) for c in hh.backend_calls if c.url.path.endswith("agent/ask")]


async def test_agent_ok_private_with_source(h):
    out = await h.send("2025-yilda nechta bitim?", chat_id=555, chat_type="private")
    assert any(isinstance(m, SendChatAction) and m.action == "typing" for m in h.session.requests)
    m = one_msg(out)
    assert m.parse_mode == "HTML"
    t = m.text
    answer, src = t.split("\n\n", 1)
    assert answer == "2025-yilda 115 763 ta bitim tuzilgan."  # plain answer first, number untouched
    # short collapsed source: header with row count, basis line, then SQL; no result rows
    assert src == (
        "<blockquote expandable><b>Manba</b> · 1 ta qator\n"
        "deals jadvali, 2025-yil, barcha holatlar | q=2025-yilda nechta bitim?\n"
        "SQL: SELECT COUNT(*) AS deals FROM deals WHERE deal_date &gt;= '2025-01-01' AND deal_date &lt; '2026-01-01'"
        "</blockquote>"
    )
    assert "<pre>" not in t and "<code>" not in t  # not allowed inside a blockquote
    assert asks(h)[0] == {"question": "2025-yilda nechta bitim?", "language": "auto", "history": []}


async def test_agent_html_escaped_and_ru_labels():
    evil = {**AGENT_OK, "language": "ru", "answer": "<b>x</b> & <script>", "basis": "<i>b</i>",
            "sql": ["SELECT '<a href=x>' " + "x" * 3000], "columns": ["a<", "b"], "rows": [["<z>", 2]],
            "row_count": 21}
    hh = Harness(agent=evil)
    try:
        t = one_msg(await hh.send("Сколько сделок?", chat_id=1, chat_type="private")).text
        assert t.startswith(html.escape("<b>x</b> & <script>", quote=False))
        assert "<b>Источник</b> · 21 строка\n&lt;i&gt;b&lt;/i&gt;\nSQL: " in t
        assert "&lt;z&gt;" not in t  # result rows are not repeated in Telegram
        assert "<script>" not in t and "<a href" not in t and "<i>" not in t
        sql_part = t.split("SQL: ")[1].split("</blockquote>")[0]
        assert len(html.unescape(sql_part)) <= 1500
        assert len(t) <= 4096
    finally:
        await hh.close()


async def test_agent_long_answer_fits_telegram_limit():
    hh = Harness(agent={**AGENT_OK, "answer": "<&>" * 3000})
    try:
        t = one_msg(await hh.send("savol", chat_id=1, chat_type="private")).text
        assert len(t) <= 4096 and "<b>Manba</b>" in t and t.endswith("</blockquote>")
    finally:
        await hh.close()


async def test_agent_answer_readable_markdown():
    ans = ("## Natija\n**Jami:** 115 763 ta bitim, 205 678 901 234,56 so'm.\n\n\n\n"
           "- BK001 — 12,5%\n* BK017 — 9,1%\n2*3 = 6")
    hh = Harness(agent={**AGENT_OK, "answer": ans})
    try:
        body = one_msg(await hh.send("savol", chat_id=1, chat_type="private")).text.split("<blockquote")[0]
        assert body.rstrip() == (
            "Natija\n<b>Jami:</b> 115 763 ta bitim, 205 678 901 234,56 so'm.\n\n"
            "• BK001 — 12,5%\n• BK017 — 9,1%\n2*3 = 6"
        )
    finally:
        await hh.close()


async def test_agent_no_sql_no_rows_no_source_block():
    hh = Harness(agent={**AGENT_OK, "sql": [], "basis": "", "rows": [], "row_count": 0})
    try:
        t = one_msg(await hh.send("salom", chat_id=1, chat_type="private")).text
        assert t == "2025-yilda 115 763 ta bitim tuzilgan."  # e.g. smalltalk: just the answer
    finally:
        await hh.close()


async def test_agent_no_data_shown_as_is():
    hh = Harness(agent=AGENT_NO_DATA)
    try:
        t = one_msg(await hh.send("Banan narxi qancha?", chat_id=1, chat_type="private")).text
        assert t == "Bilmayman — ma'lumotlarda bu haqida ma'lumot yo'q."  # no source block, no decoration
    finally:
        await hh.close()


async def test_agent_error_status_generic_ru():
    hh = Harness(agent=AGENT_ERROR)
    try:
        t = one_msg(await hh.send("Сколько сделок?", chat_id=1, chat_type="private")).text
        assert t.startswith("Извините, не удалось обработать вопрос")
        assert "Traceback" not in t
        await hh.send("а в 2025?", chat_id=1, chat_type="private")
        assert asks(hh)[1]["history"] == []  # failed turns are not remembered
    finally:
        await hh.close()


async def test_agent_http_500_and_timeout():
    hh = Harness(agent_status=500)
    try:
        t = one_msg(await hh.send("savol", chat_id=1, chat_type="private")).text
        assert t.startswith("Kechirasiz, agent hozir javob bermayapti")
    finally:
        await hh.close()
    hh = Harness(agent_delay=1.0, agent_timeout=0.2)
    try:
        t = one_msg(await hh.send("Сколько сделок в 2024?", chat_id=1, chat_type="private")).text
        assert t.startswith("Извините, ответ не был готов за 80 секунд")
    finally:
        await hh.close()


async def test_history_followups_and_new(h):
    for q in ("Сколько сделок в 2024?", "а в 2025?"):
        await h.send(q, chat_id=7, chat_type="private", user_id=7)
    a = asks(h)
    assert a[1]["history"] == [
        {"role": "user", "content": "Сколько сделок в 2024?"},
        {"role": "assistant", "content": AGENT_OK["answer"]},
    ]
    # another user in the same group has a separate context
    await h.send(f"@{BOT_USERNAME} salom", user_id=8)
    assert asks(h)[2]["history"] == []
    # only the last 6 turns are kept
    for i in range(8):
        await h.send(f"q{i}", chat_id=7, chat_type="private", user_id=7)
    assert len(asks(h)[-1]["history"]) == 12
    t = one_text(await h.send("/new", chat_id=7, chat_type="private", user_id=7))
    assert t == "Yangi suhbat boshlandi. Savolingizni yozing."
    await h.send("yana", chat_id=7, chat_type="private", user_id=7)
    assert asks(h)[-1]["history"] == []


async def test_greeting_goes_to_agent(h):
    out = await h.send("salom", chat_id=9, chat_type="private")
    assert asks(h)[-1]["question"] == "salom"  # no static command list for smalltalk
    assert "buyruqlar" not in one_msg(out).text


async def test_start_only_app_button(h):
    m = one_msg(await h.send("/start", chat_id=555, chat_type="private"))
    t = m.text
    assert "/summary" not in t and "/new" in t and "Bilmayman" in t and "Не знаю" in t and "SQL" in t
    assert t.index("AI agent") < t.index("AI-агент")  # Uzbek first, then Russian
    assert m.reply_markup is None  # no example-question buttons; no app URL yet -> no keyboard


async def test_old_example_button_still_answers(h):
    # buttons sent by an older /start keep working after the update
    before = len(h.session.sent())
    await h.dp.feed_update(h.bot, make_callback("ex:1", chat_id=555, user_id=4242))
    t = one_msg(h.session.sent()[before:]).text
    assert t.startswith(f"<i>{html.escape(EXAMPLES[1], quote=False)}</i>\n\n")
    assert any(isinstance(r, AnswerCallbackQuery) for r in h.session.requests)
    before = len(h.session.sent())
    await h.dp.feed_update(h.bot, make_callback("ex:99", chat_id=555))
    assert h.session.sent()[before:] == []


async def test_free_text_group_rules(h):
    # plain group chatter is ignored
    assert await h.send("salom hammaga") == []
    # mention -> agent, mention stripped, text passed as data; reply is threaded to the question
    m = one_msg(await h.send(f"@{BOT_USERNAME} 2025 da eng katta region?"))
    assert "q=2025 da eng katta region?" in m.text and m.reply_to_message_id
    # reply to bot -> agent
    assert "q=yana?" in one_text(await h.send("yana?", reply_to_bot=True))


async def test_any_chat_is_served_no_allow_list(h):
    for cid, typ in ((-1009999, "supergroup"), (123, "private")):
        assert one_text(await h.send("/summary 2025", chat_id=cid, chat_type=typ)).startswith("Jami aylanma")
    assert await h.send("/chatid") == []  # no admin/setup commands any more


async def test_rate_limit_per_user():
    hh = Harness(rate=3)
    try:
        for _ in range(3):
            assert one_text(await hh.send("/help")).startswith("Birja")
        assert one_text(await hh.send("/help")).startswith("So'rovlar juda ko'p")
        assert await hh.send("/help") == []  # warned once per window
        # another user in the same group is unaffected
        assert one_text(await hh.send("/help", user_id=9999)).startswith("Birja")
        # example buttons share the budget and are always answered (no spinner)
        n = len(hh.session.requests)
        await hh.dp.feed_update(hh.bot, make_callback("ex:0", chat_id=GROUP_ID, user_id=4242))
        new = hh.session.requests[n:]
        assert any(isinstance(r, AnswerCallbackQuery) for r in new)
        assert not [c for c in hh.backend_calls if c.url.path.endswith("agent/ask")]
    finally:
        await hh.close()


async def test_rate_limit_per_day():
    hh = Harness(rate=100, per_day=2)
    try:
        for _ in range(2):
            one_text(await hh.send("/help"))
        assert one_text(await hh.send("/help")).startswith("Kunlik so'rovlar limiti tugadi")
    finally:
        await hh.close()


async def test_concurrency_cap():
    hh = Harness(concurrency=2, agent_delay=0.2)
    try:
        t0 = time.perf_counter()
        await asyncio.gather(*(hh.send("savol", chat_id=100 + i, chat_type="private", user_id=100 + i)
                               for i in range(6)))
        assert time.perf_counter() - t0 >= 0.55  # 6 questions / cap 2 x 0.2 s = 3 waves
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
