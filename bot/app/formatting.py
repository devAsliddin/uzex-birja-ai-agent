"""Pure formatting helpers: backend JSON -> short Uzbek plain-text answers.

Rule: first line = the direct answer, then short detail lines. No emoji, no greetings.
"""

from __future__ import annotations

import html
from datetime import date, datetime
from typing import Any

# Backend statuses are stored in Russian (as in the source registry).
STATUS_UZ = {
    "Новый": "Yangi",
    "Не подписан": "Imzolanmagan",
    "Заключен": "Tuzilgan",
    "Ждёт оплату": "To'lov kutilmoqda",
    "Оплачен": "To'langan",
    "Исполнен": "Bajarilgan",
    "Исполнен(Частично)": "Qisman bajarilgan",
    "Аннулирован(Не оплачен)": "Bekor qilingan (to'lanmagan)",
}

# Aliases accepted in /export (lower-case) -> backend status value.
STATUS_ALIASES = {
    "yangi": "Новый",
    "imzolanmagan": "Не подписан",
    "tuzilgan": "Заключен",
    "kutilmoqda": "Ждёт оплату",
    "tolov_kutilmoqda": "Ждёт оплату",
    "tolangan": "Оплачен",
    "to'langan": "Оплачен",
    "bajarilgan": "Исполнен",
    "qisman": "Исполнен(Частично)",
    "bekor": "Аннулирован(Не оплачен)",
    "bekor_qilingan": "Аннулирован(Не оплачен)",
}
for _ru in STATUS_UZ:
    STATUS_ALIASES[_ru.lower()] = _ru

CONTRACT_TYPE_UZ = {"Внутренний": "Ichki", "Экспортный": "Eksport"}
FORM_UZ = {"Спот": "Spot", "Форвард": "Forvard", "Фьючерс": "Fyuchers"}
TRADE_UZ = {
    "Английский аукцион": "Ingliz auksioni",
    "Обратный аукцион": "Teskari auksion",
    "Двусторонний аукцион": "Ikki tomonlama auksion",
}
USD_CURRENCY = "Доллар США"

MAX_MSG = 3900  # Telegram hard limit is 4096


def status_uz(s: str | None) -> str:
    if not s:
        return "—"
    return STATUS_UZ.get(s, s)


def fmt_int(n: Any) -> str:
    try:
        return f"{int(n):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


def fmt_dec(x: float, digits: int = 1) -> str:
    s = f"{x:,.{digits}f}"
    return s.replace(",", " ").replace(".", ",")


def fmt_big(x: Any) -> str:
    """146 200 000 000 000 -> '146,2 trln'."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "—"
    a = abs(v)
    for scale, word in ((1e12, "trln"), (1e9, "mlrd"), (1e6, "mln")):
        if a >= scale:
            return f"{fmt_dec(v / scale, 1)} {word}"
    if a >= 1000 or v.is_integer():
        return fmt_int(round(v))
    return fmt_dec(v, 2)


def uzs(x: Any) -> str:
    return f"{fmt_big(x)} so'm"


def usd(x: Any) -> str:
    return f"${fmt_big(x)}"


def fmt_date(v: Any) -> str:
    if not v:
        return "—"
    if isinstance(v, (date, datetime)):
        return v.strftime("%d.%m.%Y")
    s = str(v)[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return str(v)


def clip(text: str, limit: int = MAX_MSG) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ---------------------------------------------------------------------------
HELP = """Birja reyestri boti — buyruqlar / команды:
/summary [yil] — jami aylanma (so'm, USD), bitimlar soni, USD kursi, top-3 region va kategoriya
/deal <raqam> — bitim kartochkasi
/broker <BK001> — broker profili: reyting, bitimlar, aylanma
/top_brokers [yil] — aylanma bo'yicha top-10 broker
/export <DD.MM.YYYY> <DD.MM.YYYY> [holat] [xlsx] — bitimlar fayli (CSV yoki Excel)
Holatlar: yangi, imzolanmagan, tuzilgan, kutilmoqda, tolangan, bajarilgan, qisman, bekor
/new — yangi suhbat / новый диалог
Erkin savol / Свободный вопрос: shaxsiy chatda shunchaki yozing; guruhda botni @eslang yoki xabariga javob qiling."""

EXAMPLES = (
    "2025-yilda jami nechta bitim tuzilgan?",
    "Какой брокер имел наибольший оборот в 2024 году?",
    "2023-yil mart oyida qaysi tovar eng ko'p sotilgan?",
)

OPEN_APP = "Ilovani ochish / Открыть приложение"

START_TEXT = (
    "Men UZEX birja bitimlari (2022–2026) bo'yicha AI yordamchiman. Savolingizni o'zbek "
    "yoki rus tilida oddiy so'z bilan yozing — javobni faqat bitimlar bazasidan olaman, manbasini (SQL va "
    "natija) javob ostida ko'rsataman. Ma'lumot bo'lmasa, ochiq aytaman.\n\n"
    "Я AI-помощник по биржевым сделкам UZEX (2022–2026). Пишите вопрос обычными словами "
    "на русском или узбекском — отвечаю только по данным реестра и показываю источник. Можно уточнять: "
    "«а в 2025?».\n\n"
    "Misol savollar / Примеры — bosing / нажмите:"
)


def summary_text(year: int | None, uzs_d: dict, usd_d: dict) -> str:
    years = [y.get("year") for y in uzs_d.get("yearly") or [] if y.get("year")]
    if year:
        label = str(year)
    elif years:
        label = f"{min(years)}–{max(years)}"
    else:
        label = "barcha yillar"
    count = uzs_d.get("deals_count") or 0
    if not count:
        return f"{label}: bitimlar topilmadi."
    lines = [
        f"Jami aylanma ({label}): {uzs(uzs_d.get('total_turnover'))} ({usd(usd_d.get('total_turnover'))}). "
        f"Bitimlar: {fmt_int(count)}."
    ]
    annulled = int((uzs_d.get("status_counts") or {}).get("Аннулирован(Не оплачен)") or 0)
    valid = max(count - annulled, 1)
    avg = (uzs_d.get("total_turnover") or 0) / valid
    detail = f"O'rtacha bitim: {uzs(avg)}. Brokerlar: {fmt_int(uzs_d.get('broker_count'))}."
    if annulled:
        detail += f" Bekor qilingan {fmt_int(annulled)} bitim aylanmaga kirmaydi."
    lines.append(detail)
    rate = uzs_d.get("usd_rate") or {}
    if rate.get("rate"):
        lines.append(f"USD kursi: {fmt_dec(float(rate['rate']), 2)} so'm ({fmt_date(rate.get('date'))}).")
    regions = (uzs_d.get("regions") or [])[:3]
    if regions:
        lines.append("Top regionlar:")
        for i, r in enumerate(regions, 1):
            lines.append(
                f"{i}. {r.get('region')} — {fmt_dec(float(r.get('share_pct') or 0), 1)}%, "
                f"{uzs(r.get('turnover'))}, {fmt_int(r.get('deals_count'))} bitim"
            )
    cats = (uzs_d.get("top_categories") or [])[:3]
    if cats:
        total = float(uzs_d.get("total_turnover") or 0) or 1.0
        lines.append("Top kategoriyalar:")
        for i, c in enumerate(cats, 1):
            share = float(c.get("turnover") or 0) / total * 100
            lines.append(
                f"{i}. {c.get('category')} — {uzs(c.get('turnover'))} ({fmt_dec(share, 1)}%), "
                f"{fmt_int(c.get('deals_count'))} bitim"
            )
    return clip("\n".join(lines))


def _party(p: dict | None) -> str:
    if not p:
        return "—"
    parts = [str(p.get("name") or "—")]
    if p.get("inn"):
        parts.append(f"STIR {p['inn']}")
    if p.get("region"):
        parts.append(str(p["region"]))
    return ", ".join(parts)


def _broker_short(b: dict | None) -> str:
    if not b:
        return "—"
    return f"{b.get('code')} — {b.get('name')}"


def deal_text(d: dict) -> str:
    currency = d.get("currency")
    amount = d.get("amount")
    amount_uzs = d.get("amount_uzs")
    rate = (d.get("usd_rate") or {}).get("rate")
    if currency == USD_CURRENCY:
        usd_amount = amount
    elif amount_uzs and rate:
        usd_amount = float(amount_uzs) / float(rate)
    else:
        usd_amount = None
    head = f"Bitim №{d.get('deal_no')}: {uzs(amount_uzs)}"
    if usd_amount is not None:
        head += f" ({usd(usd_amount)})"
    head += f", holati — {status_uz(d.get('status'))}."
    lines = [head]
    lines.append(f"Tovar: {d.get('product_name') or '—'}")
    unit = d.get("unit") or ""
    qty = d.get("quantity")
    lot = d.get("lot_size")
    vol = d.get("volume")
    if qty is not None:
        vol_s = f" = {fmt_big(vol)} {unit}".rstrip() if vol is not None else ""
        lot_s = f" × {fmt_big(lot)} {unit}".rstrip() if lot is not None else ""
        lines.append(f"Hajm: {fmt_int(qty)} lot{lot_s}{vol_s}")
    when = fmt_date(d.get("deal_date"))
    if d.get("deal_time"):
        when += f" {str(d['deal_time'])[:5]}"
    kind = ", ".join(
        x
        for x in (
            FORM_UZ.get(d.get("contract_form"), d.get("contract_form")),
            CONTRACT_TYPE_UZ.get(d.get("contract_type"), d.get("contract_type")),
            TRADE_UZ.get(d.get("trade_type"), d.get("trade_type")),
        )
        if x
    )
    lines.append(f"Sana: {when}" + (f"; {kind}" if kind else ""))
    if currency == USD_CURRENCY and amount is not None:
        lines.append(f"Shartnoma summasi: {usd(amount)} (kurs bo'yicha so'mga o'girilgan)")
    lines.append(f"Sotuvchi: {_party(d.get('seller'))}")
    lines.append(f"Xaridor: {_party(d.get('buyer'))}")
    lines.append(
        f"Brokerlar: sotuvchi {_broker_short(d.get('seller_broker'))}; "
        f"xaridor {_broker_short(d.get('buyer_broker'))}"
    )
    c = d.get("contract") or {}
    contract = f"Shartnoma: {d.get('contract_no') or '—'}"
    if c.get("product_category"):
        contract += f", {c['product_category']}"
    if d.get("region"):
        contract += f", ombor: {d['region']}"
    lines.append(contract)
    pay = f"To'lov: {fmt_date(d.get('payment_date'))}; yetkazish: {fmt_date(d.get('delivery_date'))}"
    if d.get("delivered_lots") is not None and qty:
        pay += f" ({fmt_int(d.get('delivered_lots'))}/{fmt_int(qty)} lot yetkazilgan)"
    lines.append(pay)
    if rate:
        lines.append(
            f"USD kursi: {fmt_dec(float(rate), 2)} so'm ({fmt_date((d.get('usd_rate') or {}).get('rate_date'))})"
        )
    return clip("\n".join(lines))


def broker_text(b: dict) -> str:
    st = b.get("stats") or {}
    rk = b.get("rating") or {}
    lines = [
        f"{b.get('broker_code')} — {b.get('name')}: reyting {rk.get('rank', '—')}/{rk.get('of', '—')}, "
        f"{fmt_int(st.get('deals_count'))} bitim, aylanma {uzs(st.get('turnover_uzs'))}."
    ]
    lines.append(f"Region: {b.get('region') or '—'}. STIR: {b.get('inn') or '—'}.")
    lines.append(
        f"Sotuvchi tomonida: {fmt_int(st.get('deals_as_seller_broker'))}, "
        f"xaridor tomonida: {fmt_int(st.get('deals_as_buyer_broker'))} bitim."
    )
    if st.get("avg_deal_uzs"):
        lines.append(f"O'rtacha bitim: {uzs(st['avg_deal_uzs'])}.")
    by_status = sorted(st.get("by_status") or [], key=lambda s: -(s.get("deals_count") or 0))[:4]
    if by_status:
        lines.append(
            "Holatlar: "
            + "; ".join(f"{status_uz(s.get('status'))} — {fmt_int(s.get('deals_count'))}" for s in by_status)
        )
    return clip("\n".join(lines))


def top_brokers_text(data: dict, year: int | None) -> str:
    items = data.get("items") or []
    if not items:
        return "Brokerlar topilmadi."
    year_applied = year is not None and data.get("year") == year
    label = f" ({year})" if year_applied else " (barcha yillar)"
    first = items[0]
    lines = [
        f"Top-{len(items)} broker{label}. 1-o'rin: {first.get('broker_code')} — {first.get('name')}, "
        f"{uzs(first.get('turnover_uzs'))}."
    ]
    for i, b in enumerate(items, 1):
        lines.append(
            f"{i}. {b.get('broker_code')} {b.get('name')} — {uzs(b.get('turnover_uzs'))}, "
            f"{fmt_int(b.get('deals_count'))} bitim, {b.get('region') or '—'}"
        )
    if year is not None and not year_applied:
        lines.append(f"Eslatma: backend yil bo'yicha filtrni qo'llamadi, {year} o'rniga barcha yillar.")
    return clip("\n".join(lines))


# --------------------------------------------------------------------------- agent answers (HTML)
UZ_CYR = set("ўқғҳЎҚҒҲ")
SQL_MAX = 1500
TABLE_MAX_ROWS = 5
CELL_MAX = 28


def detect_lang(text: str) -> str:
    """'ru' for Cyrillic text without Uzbek-specific letters, else 'uz'."""
    if any(c in UZ_CYR for c in text):
        return "uz"
    cyr = sum(1 for c in text if "Ѐ" <= c <= "ӿ")
    lat = sum(1 for c in text if c.isascii() and c.isalpha())
    return "ru" if cyr > lat else "uz"


def ru_rows(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        w = "строка"
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        w = "строки"
    else:
        w = "строк"
    return f"{fmt_int(n)} {w}"


LABELS = {
    "uz": {
        "source": "Manba", "basis": "Asos", "result": "Natija", "rows": lambda n: f"{fmt_int(n)} ta qator",
        "no_data": "Bilmayman — ma'lumotlarda bu haqida ma'lumot yo'q.",
        "error": "Kechirasiz, savolni qayta ishlab bo'lmadi. Savolni boshqacha ifodalab ko'ring.",
        "timeout": "Kechirasiz, javob 80 soniyada tayyor bo'lmadi. Savolni soddaroq qilib qayta yuboring.",
        "down": "Kechirasiz, agent hozir javob bermayapti. Birozdan keyin qayta urinib ko'ring.",
        "empty": "Savol bo'sh. Misol: " + EXAMPLES[0],
        "new": "Yangi suhbat boshlandi. Savolingizni yozing.",
    },
    "ru": {
        "source": "Источник", "basis": "Основание", "result": "Результат", "rows": ru_rows,
        "no_data": "Не знаю — в данных нет такой информации.",
        "error": "Извините, не удалось обработать вопрос. Попробуйте переформулировать.",
        "timeout": "Извините, ответ не был готов за 80 секунд. Попробуйте задать вопрос проще.",
        "down": "Извините, агент сейчас не отвечает. Повторите попытку чуть позже.",
        "empty": "Вопрос пустой. Пример: " + EXAMPLES[1],
        "new": "Начат новый диалог. Задайте вопрос.",
    },
}


def esc(x: Any) -> str:
    return html.escape("" if x is None else str(x), quote=False)


def _cell(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return fmt_int(v)
    if isinstance(v, float):
        if v.is_integer() and abs(v) < 1e15:
            return fmt_int(int(v))
        return f"{v:,.2f}".replace(",", " ")
    s = str(v).replace("\n", " ")
    return s if len(s) <= CELL_MAX else s[: CELL_MAX - 1] + "…"


def _rows_text(columns: list[Any], rows: list[list[Any]]) -> str:
    """Up to 5 result rows as 'column: value; column: value' lines (no monospace inside a quote)."""
    n = max([len(columns)] + [len(r) for r in rows])
    cols = [_cell(c) for c in columns] + [f"#{i + 1}" for i in range(len(columns), n)]
    out = []
    for r in rows:
        vals = [_cell(v) for v in r] + [""] * (n - len(r))
        out.append(vals[0] if n == 1 else "; ".join(f"{cols[i]}: {vals[i]}" for i in range(n)))
    if n == 1:
        out.insert(0, f"{cols[0]}:")
    return "\n".join(out)


def _lang(resp: dict, question: str) -> str:
    lang = resp.get("language")
    return lang if lang in LABELS else detect_lang(question)


def agent_reply(resp: dict, question: str) -> str:
    """Backend /agent/ask JSON -> Telegram HTML message. Every dynamic value is html-escaped."""
    lang = _lang(resp, question)
    L = LABELS[lang]
    status = resp.get("status")
    if status not in ("ok", "no_data"):
        return esc(L["error"])
    answer = str(resp.get("answer") or "").strip()
    if status == "no_data":
        # Shown exactly as the agent said it ("Bilmayman — ..."), no source block, no decoration.
        return esc(answer or L["no_data"])
    if not answer:
        return esc(L["error"])
    sql_list = [str(q).strip() for q in (resp.get("sql") or []) if str(q).strip()]
    basis = str(resp.get("basis") or "").strip()
    rows = resp.get("rows") or []
    columns = resp.get("columns") or []
    try:
        row_count = int(resp.get("row_count") if resp.get("row_count") is not None else len(rows))
    except (TypeError, ValueError):
        row_count = len(rows)

    # Source goes into a collapsed (expandable) quote under the answer. Telegram does not allow
    # pre/code entities inside a blockquote, so its content is plain escaped text (+ bold labels).
    src: list[str] = []
    if basis:
        src.append(f"<b>{esc(L['basis'])}:</b> {esc(basis[:400])}")
    if sql_list:
        sql = ";\n\n".join(sql_list)
        if len(sql) > SQL_MAX:
            sql = sql[: SQL_MAX - 1] + "…"
        src.append(f"<b>SQL:</b>\n{esc(sql)}")
    if rows and len(rows) <= TABLE_MAX_ROWS and all(isinstance(r, (list, tuple)) for r in rows):
        src.append(f"<b>{esc(L['result'])}:</b>\n{esc(_rows_text(list(columns), [list(r) for r in rows]))}")

    tail = ""
    if src or row_count:
        head = f"<b>{esc(L['source'])}</b> · {esc(L['rows'](row_count))}"
        tail = "<blockquote expandable>" + "\n".join([head] + src) + "</blockquote>"
    budget = MAX_MSG - len(tail) - 2
    body = esc(answer)
    cut = len(answer)
    while len(body) > budget and cut > 100:
        cut = int(cut * 0.9)
        body = esc(answer[:cut]) + "…"
    return body + ("\n\n" + tail if tail else "")


def agent_failure(kind: str, question: str) -> str:
    """kind: 'timeout' | 'down' | 'empty' -> localized plain text (safe for HTML too)."""
    return esc(LABELS[detect_lang(question)][kind])
