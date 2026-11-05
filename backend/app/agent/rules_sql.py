"""SQL templates + deterministic answer texts for the rule-based engine."""

from __future__ import annotations

import re
from typing import Any

from app.agent import db as agent_db
from app.agent.grounding import fmt_number
from dataclasses import replace

from app.agent.rules import ANN, MONTH_NAMES, PRODUCTS, Slots, esc

PROD = {p[0]: p for p in PRODUCTS}
ALL_PERIOD = {"ru": "за весь период (03.01.2022–30.10.2026)", "uz": "butun davr mobaynida (03.01.2022–30.10.2026)"}


class NotFound(Exception):
    """An explicitly named entity does not exist in the data."""

    def __init__(self, msg: dict[str, str]):
        super().__init__(msg["ru"])
        self.msg = msg


def n(v: Any, col: str = "") -> str:
    """Exact number: space thousands, decimal comma."""
    if v is None:
        return "—"
    if isinstance(v, (int, float)):
        return fmt_number(v, col).replace(".", ",")
    return str(v)


_SCALES = {"uz": [(1e12, "trln"), (1e9, "mlrd"), (1e6, "mln")], "ru": [(1e12, "трлн"), (1e9, "млрд"), (1e6, "млн")]}


def human(v: Any, lang: str) -> str | None:
    """'8,69 trln' style short form for |v| >= 1 mln, else None."""
    if not isinstance(v, (int, float)) or abs(v) < 1e6:
        return None
    for sc, word in _SCALES["uz" if lang == "uz" else "ru"]:
        if abs(v) >= sc:
            x = v / sc
            return f"{x:.2f}".replace(".", ",") + f" {word}" if abs(x) < 10 else f"{x:.1f}".replace(".", ",") + f" {word}"
    return None


def money1(v: Any, lang: str, usd: bool = False, exact: bool = True) -> str:
    """Money: human form + exact value in parentheses (exact only below 1 mln)."""
    cur = "$" if usd else ("so‘m" if lang == "uz" else "сум")
    h = human(v, lang)
    if h is None:
        return f"{n(v)} {cur}"
    if not exact:
        return f"{h} {cur}"
    return f"{h} {cur} ({'aniq' if lang == 'uz' else 'точно'}: {n(v)} {cur})"


def money(uzs: Any, usd: Any, lang: str, usd_first: bool = False) -> str:
    if usd is None:
        return money1(uzs, lang)
    if usd_first:
        return f"{money1(usd, lang, usd=True)} ≈ {money1(uzs, lang, exact=False)}"
    return f"{money1(uzs, lang)} ≈ {money1(usd, lang, usd=True, exact=False)}"


def fmt_pct(v: Any) -> str:
    if not isinstance(v, (int, float)):
        return n(v)
    short = f"{v:.1f}".replace(".", ",")
    exact = n(v)
    return f"{short}%" if short == exact else f"{short}% ({exact}%)"


def ddmmyyyy(iso: Any) -> str:
    if not isinstance(iso, str) or not re.match(r"\d{4}-\d{2}-\d{2}", iso):
        return n(iso)
    return f"{iso[8:10]}.{iso[5:7]}.{iso[:4]}"


def _one(sql: str) -> list[list[Any]]:
    return agent_db.run_query(sql, max_rows=50).rows


# ---------------------------------------------------------------------------
# filters
# ---------------------------------------------------------------------------
def period_text(s: Slots, lang: str) -> str:
    if s.quarter:
        y = f" {s.years[0]}" if s.years else ""
        if lang == "uz":
            return f"{s.years[0]}-yil {s.quarter}-choragida" if s.years else f"barcha yillarning {s.quarter}-choragida"
        return f"в {s.quarter}-м квартале{y} года" if s.years else f"в {s.quarter}-м квартале (все годы)"
    if s.day:
        return f"{ddmmyyyy(s.day)} kuni" if lang == "uz" else f"{ddmmyyyy(s.day)}"
    if s.years and s.month:
        y = s.years[0]
        return (f"{y}-yil {MONTH_NAMES['uz'][s.month]} oyida" if lang == "uz"
                else f"в {MONTH_NAMES['ru'][s.month]}е {y} года".replace("йе", "е").replace("ье", "е")
                .replace("те ", "те ").replace("в мае", "в мае"))
    if s.month:
        return (f"barcha yillarning {MONTH_NAMES['uz'][s.month]} oylarida" if lang == "uz"
                else f"в месяце «{MONTH_NAMES['ru'][s.month]}» всех лет")
    if len(s.years) == 1:
        return f"{s.years[0]}-yilda" if lang == "uz" else f"в {s.years[0]} году"
    if len(s.years) > 1:
        return (f"{s.years[0]}–{s.years[-1]}-yillarda" if lang == "uz" else f"в {s.years[0]}–{s.years[-1]} годах")
    return ALL_PERIOD[lang]


def _ru_month_prep(m: int) -> str:
    return ["", "январе", "феврале", "марте", "апреле", "мае", "июне", "июле", "августе", "сентябре", "октябре",
            "ноябре", "декабре"][m]


def period(s: Slots, lang: str) -> str:
    if lang == "ru" and s.years and s.month and not s.day:
        return f"в {_ru_month_prep(s.month)} {s.years[0]} года"
    return period_text(s, lang)


UNIT_LBL = {"тонна": ("тонн", "tonna"), "литр": ("литров", "litr"), "килограмм": ("кг", "kg"), "метр": ("м", "metr"),
            "штука": ("шт.", "dona"), "куб.метр": ("м³", "m³"), "кв.метр": ("м²", "m²")}


def unit_lbl(u: Any, lang: str) -> str:
    return UNIT_LBL.get(u, (u, u))[1 if lang == "uz" else 0] if isinstance(u, str) else n(u)


def subject(s: Slots, lang: str) -> str:
    parts = []
    if s.exact_name:
        parts.append(f"«{s.exact_name}»")
    elif s.product:
        parts.append(f"«{PROD[s.product][4 if lang == 'uz' else 3]}" + (f" {s.grade.upper()}" if s.grade else "") + "»")
    if s.contract_type:
        parts.append(("eksport" if s.contract_type == "Экспортный" else "ichki") if lang == "uz"
                     else ("экспортные" if s.contract_type == "Экспортный" else "внутренние"))
    if s.region:
        parts.append(s.region)
    if s.form:
        parts.append(s.form.lower())
    if s.category:
        parts.append(f"«{s.category}»")
    if s.trade_type:
        parts.append(s.trade_type.lower())
    if s.statuses and len(s.statuses) == 1:
        parts.append(s.statuses[0])
    if s.broker:
        parts.append(s.broker)
    if s.inn:
        parts.append(("STIR " if lang == "uz" else "ИНН ") + s.inn)
    if not parts:
        return ""
    return (" (" + ", ".join(parts) + ")")


def deal_where(s: Slots, default_exclude: bool) -> tuple[list[str], list[str], list[str]]:
    """Return (sql conditions, basis ru, basis uz)."""
    w: list[str] = []
    br: list[str] = []
    bu: list[str] = []
    if s.day:
        w.append(f"deal_date = '{s.day}'")
    elif s.quarter:
        w.append(f"month BETWEEN {3 * s.quarter - 2} AND {3 * s.quarter}")
        if s.years:
            w.append(f"deal_date >= '{s.years[0]}-01-01' AND deal_date < '{s.years[-1] + 1}-01-01'")
    elif s.years:
        y0, y1 = s.years[0], s.years[-1]
        if s.month:
            w.append(f"deal_date >= '{y0}-{s.month:02d}-01' AND deal_date < "
                     f"'{y0 + (s.month == 12)}-{(s.month % 12) + 1:02d}-01'")
        else:
            w.append(f"deal_date >= '{y0}-01-01' AND deal_date < '{y1 + 1}-01-01'")
    elif s.month:
        w.append(f"month = {s.month}")
    if s.region:
        w.append(f"region = '{esc(s.region)}'")
        br.append(f"регион склада продавца: {s.region}")
        bu.append(f"sotuvchi ombori hududi: {s.region}")
    if s.statuses:
        w.append("status IN (" + ", ".join(f"'{esc(x)}'" for x in s.statuses) + ")")
        br.append("состояние: " + ", ".join(s.statuses))
        bu.append("holat: " + ", ".join(s.statuses))
    elif s.exclude_ann or default_exclude:
        w.append(f"status <> '{ANN}'")
        br.append("аннулированные (Аннулирован(Не оплачен)) не учтены")
        bu.append("bekor qilingan bitimlar (Аннулирован(Не оплачен)) hisobga olinmadi")
    if s.exact_name:
        x = esc(s.exact_name.lower())
        w.append(f"(ulower(product_name) = '{x}' OR contract_no IN (SELECT contract_no FROM contracts "
                 f"WHERE ulower(product_name) = '{x}'))")
        br.append(f"товар: ровно «{s.exact_name}»")
        bu.append(f"tovar: aynan «{s.exact_name}»")
    elif s.product:
        pats = PROD[s.product][2]
        cond = " OR ".join(f"ulower(product_name) LIKE '{p}'" for p in pats)
        w.append(f"contract_no IN (SELECT contract_no FROM contracts WHERE {cond})")
        names = [r[0] for r in _one(f"SELECT DISTINCT product_name FROM contracts WHERE {cond} ORDER BY 1 LIMIT 12")]
        if not names:
            raise NotFound({"ru": "В данных нет такого товара.", "uz": "Ma'lumotlarda bunday tovar yo'q."})
        br.append(f"товар: {PROD[s.product][3]} (все варианты написания: {', '.join(names)})")
        bu.append(f"tovar: {PROD[s.product][4]} (barcha yozilish variantlari: {', '.join(names)})")
    if s.grade:
        w.append(f"ulower(product_name) LIKE '%{s.grade}%'")
        br.append(f"марка {s.grade.upper()}")
        bu.append(f"marka {s.grade.upper()}")
    if s.contract_type:
        w.append(f"contract_type = '{s.contract_type}'")
        br.append(f"тип контракта: {s.contract_type}")
        bu.append(f"shartnoma turi: {s.contract_type}")
    if s.currency:
        cur = "Узбекский сум" if s.currency == "UZS" else "Доллар США"
        w.append(f"currency = '{cur}'")
        br.append(f"валюта контракта: {cur}")
        bu.append(f"shartnoma valyutasi: {cur}")
    if s.form:
        w.append(f"contract_form = '{s.form}'")
        br.append(f"форма: {s.form}")
        bu.append(f"shakl: {s.form}")
    if s.trade_type:
        w.append(f"trade_type = '{s.trade_type}'")
        br.append(f"тип торгов: {s.trade_type}")
        bu.append(f"savdo turi: {s.trade_type}")
    if s.category:
        w.append(f"product_category = '{esc(s.category)}'")
        br.append(f"категория: {s.category}")
        bu.append(f"toifa: {s.category}")
    if s.unit and s.metric in ("volume", "unit_price"):
        w.append(f"unit = '{s.unit}'")
        br.append(f"единица: {s.unit}")
        bu.append(f"o‘lchov birligi: {s.unit}")
    if s.broker and s.metric != "lookup":
        col = {"seller": "seller_broker", "buyer": "buyer_broker"}.get(s.side or "")
        w.append(f"{col} = '{s.broker}'" if col else f"(seller_broker = '{s.broker}' OR buyer_broker = '{s.broker}')")
        br.append(f"брокер {s.broker}")
        bu.append(f"broker {s.broker}")
    if s.inn and s.metric != "lookup":
        col = {"seller": "seller_inn", "buyer": "buyer_inn"}.get(s.side or "")
        w.append(f"{col} = '{s.inn}'" if col else f"(seller_inn = '{s.inn}' OR buyer_inn = '{s.inn}')")
        br.append(f"ИНН {s.inn}")
        bu.append(f"STIR {s.inn}")
    return w, br, bu


def _where(w: list[str]) -> str:
    return (" WHERE " + " AND ".join(w)) if w else ""


def check_exists(s: Slots) -> None:
    if s.broker and not _one(f"SELECT 1 FROM brokers WHERE broker_code = '{s.broker}'"):
        raise NotFound({"ru": f"В данных нет брокера с кодом {s.broker}.",
                        "uz": f"Ma'lumotlarda {s.broker} kodli broker yo'q."})
    if s.deal_no and not _one(f"SELECT 1 FROM deals WHERE deal_no = {int(s.deal_no)}"):
        raise NotFound({"ru": f"В данных нет сделки № {s.deal_no}.",
                        "uz": f"Ma'lumotlarda {s.deal_no}-raqamli bitim yo'q."})
    if s.contract_no and not _one(f"SELECT 1 FROM contracts WHERE contract_no = '{esc(s.contract_no)}'"):
        raise NotFound({"ru": f"В данных нет контракта № {s.contract_no}.",
                        "uz": f"Ma'lumotlarda {s.contract_no}-raqamli shartnoma yo'q."})
    if s.inn and not _one(f"SELECT 1 FROM participants WHERE inn = '{s.inn}'") and not _one(
            f"SELECT 1 FROM brokers WHERE inn = '{s.inn}'"):
        raise NotFound({"ru": f"В данных нет компании с ИНН {s.inn}.",
                        "uz": f"Ma'lumotlarda {s.inn} STIRli kompaniya yo'q."})
    if s.exact_name and s.metric not in ("lookup",):
        x = esc(s.exact_name.lower())
        if not _one(f"SELECT 1 FROM contracts WHERE ulower(product_name) = '{x}' LIMIT 1") and not _one(
                f"SELECT 1 FROM deals WHERE contract_no IN (SELECT contract_no FROM contracts) AND "
                f"product_name = '{esc(s.exact_name)}' LIMIT 1"):
            # unknown quoted name: maybe a company
            if not _one(f"SELECT 1 FROM participants WHERE ulower(name) LIKE '%{x}%' LIMIT 1"):
                raise NotFound({"ru": f"В данных нет «{s.exact_name}».", "uz": f"Ma'lumotlarda «{s.exact_name}» yo'q."})


# ---------------------------------------------------------------------------
# main builder
# ---------------------------------------------------------------------------
def build(s: Slots, lang: str, qnorm: str) -> tuple[str, str, Any]:
    """Return (sql, basis, answer_fn(columns, rows) -> str)."""
    check_exists(s)
    m = s.metric
    uz = lang == "uz"
    P = period(s, lang) + subject(s, lang)
    if m in ("avg_amount", "median") and not s.currency and not s.contract_type and re.search(
            r"в сумах|so'mda|сумах|сўмда", qnorm):
        s.currency = "UZS"

    def basis(br: list[str], bu: list[str], extra_ru: str = "", extra_uz: str = "") -> str:
        parts = (bu if uz else br)
        head = ("Manba: bitimlar reyestri + shartnoma kartochkalari + USD kursi; davr: " if uz
                else "Источник: реестр сделок + карточки контрактов + курс USD; период: ") + P
        tail = (extra_uz if uz else extra_ru)
        return head + ("; " + "; ".join(parts) if parts else "") + (("; " + tail) if tail else "")

    # ------------------------------------------------------------------ simple deal metrics
    if m == "count":
        w, br, bu = deal_where(s, False)
        if s.statuses or s.exclude_ann:
            sql = f"SELECT COUNT(*) AS deals_count FROM v_deals{_where(w)}"

            def ans(c, r):
                k = r[0][0]
                st = ", ".join(s.statuses) if s.statuses else ""
                if uz:
                    what = f"«{st}» holatidagi bitimlar" if st else "bekor qilinmagan bitimlar"
                    return f"{P} {what} soni: {n(k)} ta." if k else f"{P} bunday bitim bo'lmagan (0 ta)."
                what = f"сделок в состоянии «{st}»" if st else "сделок без аннулированных"
                return f"{P}: {what} — {n(k)}." if k else f"{P} таких сделок не было (0)."
        else:
            sql = f"SELECT COUNT(*) AS deals_total, SUM(is_valid) AS deals_not_cancelled FROM v_deals{_where(w)}"

            def ans(c, r):
                k, v = r[0][0], r[0][1] or 0
                if not k:
                    return (f"{P} bitim bo'lmagan (0 ta) — bu kunda/davrda savdo o'tkazilmagan." if uz
                            else f"{P} сделок не было (0) — торги в этот день/период не проводились.")
                if uz:
                    return (f"{P} jami {n(k)} ta bitim tuzilgan, shundan {n(v)} tasi bekor qilinmagan "
                            f"(Аннулирован(Не оплачен) holatidagilardan tashqari).")
                return (f"{P} заключено {n(k)} сделок (все состояния), из них {n(v)} — без "
                        f"аннулированных (Аннулирован(Не оплачен)).")
        return sql, basis(br, bu), ans

    if m == "share":
        w, br, bu = deal_where(s, False)
        base = replace(s, statuses=None, exclude_ann=False, contract_type=None, form=None, trade_type=None,
                       region=None, product=None, grade=None, exact_name=None, category=None, currency=None,
                       broker=None, inn=None)
        wb, _, _ = deal_where(base, False)
        if s.rank_by == "sum":  # share of turnover (cancelled deals excluded on both sides)
            w, br, bu = deal_where(replace(s, exclude_ann=True), True)
            wb, _, _ = deal_where(replace(base, exclude_ann=True), True)
            sql = (f"SELECT (SELECT ROUND(SUM(amount_uzs), 2) FROM v_deals{_where(w)}) AS part_uzs, "
                   f"(SELECT ROUND(SUM(amount_uzs), 2) FROM v_deals{_where(wb)}) AS base_uzs, "
                   f"ROUND(100.0 * (SELECT SUM(amount_uzs) FROM v_deals{_where(w)}) / "
                   f"(SELECT SUM(amount_uzs) FROM v_deals{_where(wb)}), 4) AS share_pct")

            def ans_sum(c, r):
                part, base_v, pct = r[0]
                if not base_v:
                    return None
                if uz:
                    return (f"{P} aylanmadagi ulushi — {fmt_pct(pct)}: {money1(part, lang)} / jami {money1(base_v, lang, exact=False)}.\n"
                            f"Bekor qilingan bitimlar hisobga olinmadi, dollar bitimlari kurs bo'yicha.")
                return (f"Доля в обороте {P} — {fmt_pct(pct)}: {money1(part, lang)} из {money1(base_v, lang, exact=False)}.\n"
                        f"Аннулированные не учитывались, долларовые сделки пересчитаны по курсу.")
            return sql, basis(br, bu), ans_sum
        sql = (f"SELECT (SELECT COUNT(*) FROM v_deals{_where(w)}) AS part_count, "
               f"(SELECT COUNT(*) FROM v_deals{_where(wb)}) AS base_count, "
               f"ROUND(100.0 * (SELECT COUNT(*) FROM v_deals{_where(w)}) / "
               f"(SELECT COUNT(*) FROM v_deals{_where(wb)}), 2) AS share_pct")

        def ans(c, r):
            part, base_n, pct = r[0]
            if not base_n:
                return None
            if uz:
                return (f"{P} bunday bitimlar ulushi — {fmt_pct(pct)}: {n(part)} ta / jami {n(base_n)} ta bitimdan.\n"
                        f"Ulush bitimlar soni bo'yicha hisoblangan (barcha holatlar bazasida).")
            return (f"Доля таких сделок {P} — {fmt_pct(pct)}: {n(part)} из {n(base_n)} сделок.\n"
                    f"Доля посчитана по количеству сделок (база — все сделки периода).")
        return sql, basis(br, bu), ans

    if m == "sum":
        w, br, bu = deal_where(s, True)
        sql = (f"SELECT COUNT(*) AS deals_count, ROUND(SUM(amount_uzs), 2) AS total_uzs, "
               f"ROUND(SUM(amount_usd), 2) AS total_usd FROM v_deals{_where(w)}")
        usd_first = s.out_usd or s.currency == "USD" or (s.contract_type == "Экспортный" and not re.search(
            r"сум|so'm|сўм", qnorm))

        def ans(c, r):
            k, uzs, usd = r[0]
            if not k:
                return (f"{P} bunday bitimlar bo'lmagan (0 ta)." if uz else f"{P} таких сделок не было (0).")
            if uz:
                return (f"{P} bitimlar umumiy summasi (aylanma) — {money(uzs, usd, lang, usd_first)}.\n"
                        f"Bitimlar soni: {n(k)} ta. Dollar bitimlari bitim kunidagi kurs bo'yicha so'mga o'girilgan.")
            return (f"Оборот {P}: {money(uzs, usd, lang, usd_first)}.\n"
                    f"Сделок: {n(k)}. Долларовые сделки пересчитаны по курсу на дату сделки.")
        return sql, basis(br, bu), ans

    if m in ("avg_amount", "median"):
        w, br, bu = deal_where(s, True)
        native = s.currency == "UZS" or s.contract_type == "Внутренний"
        if m == "avg_amount":
            sql = (f"SELECT ROUND(AVG(amount_uzs), 4) AS avg_uzs, ROUND(AVG(amount_usd), 2) AS avg_usd, "
                   f"COUNT(*) AS deals_count FROM v_deals{_where(w)}")
            word_ru, word_uz = "Средняя сумма сделки", "Bitimning o'rtacha summasi"
        else:
            sql = (f"WITH o AS (SELECT amount_uzs AS v, ROW_NUMBER() OVER (ORDER BY amount_uzs) AS rn, "
                   f"COUNT(*) OVER () AS c FROM v_deals{_where(w)}) "
                   f"SELECT ROUND(AVG(v), 4) AS median_uzs, MAX(c) AS deals_count FROM o "
                   f"WHERE rn IN ((c + 1) / 2, (c + 2) / 2)")
            word_ru, word_uz = "Медиана суммы сделки", "Bitim summasining medianasi"

        def ans(c, r):
            row = r[0]
            if row[0] is None:
                return None
            som = "so‘m" if uz else "сум"
            val = money1(row[0], lang) + (f" ≈ {money1(row[1], lang, usd=True, exact=False)}"
                                          if m == "avg_amount" and not native and row[1] else "")
            cnt = row[-1]
            return (f"{P} {word_uz.lower()} — {val}.\nHisobda {n(cnt)} ta bitim." if uz
                    else f"{word_ru} {P}: {val}.\nУчтено сделок: {n(cnt)}.")
        return sql, basis(br, bu), ans

    if m in ("max_deal", "min_deal"):
        w, br, bu = deal_where(s, True)
        order = "DESC" if m == "max_deal" else "ASC"
        cols = "deal_no, deal_date, amount, currency, ROUND(amount_uzs, 2) AS amount_uzs, product_name, status"
        sql = (f"SELECT * FROM (SELECT 'all' AS scope, {cols} FROM v_deals{_where(w)} ORDER BY amount_uzs {order}, "
               f"deal_no LIMIT 1) UNION ALL SELECT * FROM (SELECT 'uzs_contracts' AS scope, {cols} FROM v_deals"
               f"{_where(w + [chr(39).join(['currency = ', 'Узбекский сум', ''])])} ORDER BY amount {order}, deal_no LIMIT 1)")

        def ans(c, r):
            if not r:
                return None
            main = _maxmin_text([x[1:] for x in r[:1]], lang, m, P)
            if len(r) > 1 and r[1][1] != r[0][1]:
                d2 = r[1][1:]
                main += (f"\nSo‘mdagi shartnomalar orasida: bitim № {d2[0]} — {money1(d2[2], lang)} ({ddmmyyyy(d2[1])})." if uz
                         else f"\nСреди сделок в сумовых контрактах: сделка № {d2[0]} — {money1(d2[2], lang)} ({ddmmyyyy(d2[1])}).")
            return main
        return sql, basis(br, bu), ans

    if m == "__unused__":
        def ans(c, r):
            d = r[0]
            cur = "USD" if d[3] == "Доллар США" else ("so‘m" if uz else "сум")
            extra = "" if d[3] != "Доллар США" else f" ({n(d[4])} {'so‘m' if uz else 'сум'})"
            if uz:
                kind = "eng yirik" if m == "max_deal" else "eng kichik"
                return (f"{P} summa bo'yicha {kind} bitim — № {d[0]}: {n(d[2])} {cur}{extra}.\n"
                        f"Sana: {ddmmyyyy(d[1])}, tovar: {d[5]}, holat: {d[6]}.")
            kind = "Самая крупная" if m == "max_deal" else "Самая мелкая"
            return (f"{kind} по сумме сделка {P} — № {d[0]}: {n(d[2])} {cur}{extra}.\n"
                    f"Дата: {ddmmyyyy(d[1])}, товар: {d[5]}, состояние: {d[6]}.")
        return sql, basis(br, bu), ans

    if m == "volume":
        w, br, bu = deal_where(s, True)
        sql = (f"SELECT unit, ROUND(SUM(volume), 3) AS volume, COUNT(*) AS deals_count FROM v_deals{_where(w)} "
               f"GROUP BY unit ORDER BY volume DESC")

        def ans(c, r):
            if not r:
                return None
            first = r[0]
            lines = [f"{n(x[1])} {unit_lbl(x[0], lang)}" for x in r]
            if uz:
                return (f"{P} jami {lines[0]} sotilgan ({n(first[2])} ta bitim)." +
                        (f"\nBoshqa birliklarda: {', '.join(lines[1:])}." if len(r) > 1 else ""))
            return (f"{P} продано {lines[0]} ({n(first[2])} сделок)." +
                    (f"\nВ других единицах: {', '.join(lines[1:])}." if len(r) > 1 else ""))
        return sql, basis(br, bu, "объём = количество × лот", "hajm = lotlar soni × lot"), ans

    if m == "unit_price":
        w, br, bu = deal_where(s, True)
        sql = (f"SELECT unit, ROUND(SUM(amount_uzs) / SUM(volume), 4) AS price_uzs_per_unit, "
               f"ROUND(SUM(amount_usd) / SUM(volume), 4) AS price_usd_per_unit, COUNT(*) AS deals_count, "
               f"ROUND(SUM(volume), 3) AS volume FROM v_deals{_where(w)} GROUP BY unit ORDER BY deals_count DESC")

        def ans(c, r):
            if not r:
                return None
            som = "so‘m" if uz else "сум"
            parts = [f"{money1(x[1], lang)} / {unit_lbl(x[0], lang).replace('тонн', 'тонна').replace('литров', 'литр')}"
                     f" (≈ {n(round(x[2], 2)) if x[2] is not None else '—'} $; {n(x[3])} " + ("ta bitim)" if uz else "сделок)")
                     for x in r]
            if uz:
                return (f"{P} o'rtacha tortilgan narx — {parts[0]}." +
                        (f"\nBoshqa o'lchov birligida: {'; '.join(parts[1:])}." if len(parts) > 1 else "") +
                        "\nNarx = jami summa ÷ jami hajm (lot × lotlar soni).")
            return (f"Средневзвешенная цена {P}: {parts[0]}." +
                    (f"\nВ другой единице: {'; '.join(parts[1:])}." if len(parts) > 1 else "") +
                    "\nЦена = сумма сделок ÷ объём (количество × лот).")
        return sql, basis(br, bu), ans

    if m == "avg_lots":
        w, br, bu = deal_where(s, False)
        sql = f"SELECT ROUND(AVG(quantity), 4) AS avg_lots, COUNT(*) AS deals_count FROM v_deals{_where(w)}"

        def ans(c, r):
            if r[0][0] is None:
                return None
            return (f"{P} bitta bitimda o'rtacha {n(r[0][0])} lot sotib olingan ({n(r[0][1])} ta bitim)." if uz
                    else f"{P} в среднем покупалось {n(r[0][0])} лота на сделку ({n(r[0][1])} сделок).")
        return sql, basis(br, bu), ans

    if m == "late":
        w, br, bu = deal_where(s, False)
        w = w + ["delivery_date IS NOT NULL", "delivery_date > delivery_due_date"]
        sql = f"SELECT COUNT(*) AS late_deals FROM v_deals{_where(w)}"

        def ans(c, r):
            if uz:
                return (f"{P} {n(r[0][0])} ta bitim shartnomadagi yetkazib berish muddatidan kechikib yetkazilgan.\n"
                        f"Muddat = to'lov sanasi + shartnomadagi «Срок поставки» kunlari.")
            return (f"{P} с нарушением срока поставки поставлено {n(r[0][0])} сделок.\n"
                    f"Срок = дата оплаты + «Срок поставки» (дней) из контракта.")
        return sql, basis(br, bu), ans

    if m == "undelivered_lots":
        if not s.statuses:
            s.statuses = ["Исполнен(Частично)"]
        w, br, bu = deal_where(s, False)
        sql = (f"SELECT SUM(quantity - delivered_lots) AS undelivered_lots, COUNT(*) AS deals_count "
               f"FROM v_deals{_where(w)}")

        def ans(c, r):
            if r[0][0] is None:
                return None
            return (f"{P} qisman bajarilgan bitimlar bo'yicha {n(r[0][0])} lot yetkazilmagan ({n(r[0][1])} ta bitim)." if uz
                    else f"{P} по частично исполненным сделкам не допоставлено {n(r[0][0])} лотов "
                         f"({n(r[0][1])} сделок).")
        return sql, basis(br, bu), ans

    if m in ("pay_days_avg", "pay_days_max"):
        w, br, bu = deal_where(s, False)
        w = w + ["payment_date IS NOT NULL"]
        agg = "ROUND(AVG(julianday(payment_date) - julianday(deal_date)), 4)" if m == "pay_days_avg" else \
            "CAST(MAX(julianday(payment_date) - julianday(deal_date)) AS INTEGER)"
        sql = f"SELECT {agg} AS days, COUNT(*) AS paid_deals FROM v_deals{_where(w)}"

        def ans(c, r):
            if r[0][0] is None:
                return None
            if m == "pay_days_avg":
                return (f"{P} bitimdan to'lovgacha o'rtacha {n(r[0][0])} kun o'tgan ({n(r[0][1])} ta to'langan bitim)." if uz
                        else f"{P} от сделки до оплаты в среднем проходило {n(r[0][0])} дня "
                             f"({n(r[0][1])} оплаченных сделок).")
            return (f"{P} bitimdan to'lovgacha eng uzoq muddat — {n(r[0][0])} kun." if uz
                    else f"Самый долгий срок от сделки до оплаты {P}: {n(r[0][0])} дней.")
        return sql, basis(br, bu), ans

    if m == "same_broker":
        w, br, bu = deal_where(s, False)
        w = w + ["seller_broker = buyer_broker"]
        sql = f"SELECT COUNT(*) AS same_broker_deals FROM v_deals{_where(w)}"

        def ans(c, r):
            return (f"{P} sotuvchi va xaridor tomonida bir xil broker bo'lgan {n(r[0][0])} ta bitim bor." if uz
                    else f"{P} сделок с одним и тем же брокером на обеих сторонах: {n(r[0][0])}.")
        return sql, basis(br, bu), ans

    # ------------------------------------------------------------------ ranking
    if m == "top":
        return _top(s, lang, P, basis)

    # ------------------------------------------------------------------ entities
    if m == "count_entity":
        return _count_entity(s, lang, P)
    if m == "never_traded":
        sql = ("SELECT p.inn, p.name, p.role FROM participants p WHERE p.inn NOT IN "
               "(SELECT seller_inn FROM deals UNION SELECT buyer_inn FROM deals) ORDER BY p.inn")

        def ans(c, r):
            lst = "; ".join(f"{x[1]} (STIR {x[0]})" if uz else f"{x[1]} (ИНН {x[0]})" for x in r[:10])
            return (f"Hech bir bitimda qatnashmagan ishtirokchilar: {len(r)} ta.\n{lst}" if uz
                    else f"Участников, не участвовавших ни в одной сделке: {len(r)}.\n{lst}")
        return sql, ("Manba: participants va deals (sotuvchi yoki xaridor STIR)" if uz
                     else "Источник: participants и deals (ИНН продавца или покупателя)"), ans
    if m == "rate":
        return _rate(s, lang, P)
    if m == "lookup":
        return _lookup(s, lang, qnorm)
    raise NotFound({"ru": "", "uz": ""})


def _top(s: Slots, lang: str, P: str, basis):
    uz = lang == "uz"
    by_sum = s.rank_by == "sum"
    w, br, bu = deal_where(s, by_sum)
    meas = "ROUND(SUM(amount_uzs), 2) AS total_uzs, COUNT(*) AS deals_count" if by_sum else \
        "COUNT(*) AS deals_count, ROUND(SUM(amount_uzs), 2) AS total_uzs"
    order = "DESC" if s.order == "desc" else "ASC"
    key = "total_uzs" if by_sum else "deals_count"
    lim = max(s.top_n, 5)
    g = s.group
    side_ru = side_uz = ""
    if g == "broker":
        if s.side in ("seller", "buyer"):
            col = f"{s.side}_broker"
            side_ru = " на стороне продавца" if s.side == "seller" else " на стороне покупателя"
            side_uz = " sotuvchi tomonida" if s.side == "seller" else " xaridor tomonida"
            sql = (f"SELECT b.broker_code, b.name, x.* FROM (SELECT {col} AS code, {meas} FROM v_deals{_where(w)} "
                   f"GROUP BY {col}) x JOIN brokers b ON b.broker_code = x.code ORDER BY {key} {order} LIMIT {lim}")
        else:
            side_ru, side_uz = " (на любой стороне сделки)", " (sotuvchi yoki xaridor tomonida)"
            amt = "ROUND(SUM(amount_uzs), 2) AS total_uzs, COUNT(DISTINCT deal_no) AS deals_count" if by_sum else \
                "COUNT(DISTINCT deal_no) AS deals_count, ROUND(SUM(amount_uzs), 2) AS total_uzs"
            sql = (f"WITH t AS (SELECT seller_broker AS code, deal_no, amount_uzs FROM v_deals{_where(w)} UNION "
                   f"SELECT buyer_broker, deal_no, amount_uzs FROM v_deals{_where(w)}) "
                   f"SELECT b.broker_code, b.name, x.* FROM (SELECT code, {amt} FROM t GROUP BY code) x "
                   f"JOIN brokers b ON b.broker_code = x.code ORDER BY {key} {order} LIMIT {lim}")
        label = lambda r: f"{r[0]} — {r[1]}"  # noqa: E731
        what_ru, what_uz = "брокер" + side_ru, "broker" + side_uz
    elif g in ("seller", "buyer"):
        col = f"{g}_inn"
        sql = (f"SELECT p.inn, p.name, x.* FROM (SELECT {col} AS inn_, {meas} FROM v_deals{_where(w)} GROUP BY {col}) x "
               f"JOIN participants p ON p.inn = x.inn_ ORDER BY {key} {order} LIMIT {lim}")
        label = (lambda r: f"{r[1]} (STIR {r[0]})") if uz else (lambda r: f"{r[1]} (ИНН {r[0]})")
        what_ru, what_uz = ("продавец", "sotuvchi") if g == "seller" else ("покупатель", "xaridor")
    else:
        col = {"region": "region", "category": "product_category", "industry": "industry",
               "product": "product_name", "year": "year", "month": "substr(deal_date, 1, 7)",
               "trade_type": "trade_type", "contract_form": "contract_form"}[g]
        sql = (f"SELECT {col} AS name, {meas} FROM v_deals{_where(w)} GROUP BY {col} "
               f"ORDER BY {key} {order} LIMIT {lim}")
        label = lambda r: str(r[0])  # noqa: E731
        what_ru, what_uz = {"region": ("регион", "hudud"), "category": ("категория товаров", "tovar toifasi"),
                            "industry": ("отрасль", "soha"), "product": ("наименование товара", "tovar nomi"),
                            "year": ("год", "yil"), "month": ("месяц", "oy"),
                            "trade_type": ("тип торгов", "savdo turi"),
                            "contract_form": ("форма контракта", "shartnoma shakli")}[g]

    def ans(c, r):
        if not r:
            return None
        ci = {name: i for i, name in enumerate(c)}

        def val(row):
            if by_sum:
                return money1(row[ci["total_uzs"]], lang) + (
                    f", {n(row[ci['deals_count']])} ta bitim" if uz else f", {n(row[ci['deals_count']])} сделок")
            return (f"{n(row[ci['deals_count']])} ta bitim" if uz else f"{n(row[ci['deals_count']])} сделок")
        crit_ru = "по обороту (без аннулированных, доллары по курсу)" if by_sum else "по количеству сделок"
        crit_uz = "aylanma bo'yicha (bekor qilinganlarsiz, dollar kurs bo'yicha)" if by_sum else "bitimlar soni bo'yicha"
        least = s.order == "asc"
        if s.top_n > 1:
            lines = "\n".join(f"{i}. {label(x)} — {val(x)}" for i, x in enumerate(r[: s.top_n], 1))
            if uz:
                return f"{P} {crit_uz} {'eng past' if least else 'yetakchi'} {s.top_n} ta ({what_uz}):\n{lines}"
            return f"{'Последние' if least else 'Топ-'}{s.top_n} ({what_ru}) {P} {crit_ru}:\n{lines}"
        top = r[0]
        second = (f"\n2-o'rinda: {label(r[1])} — {val(r[1])}." if uz else f"\nНа втором месте: {label(r[1])} — {val(r[1])}.") \
            if len(r) > 1 else ""
        if uz:
            return f"{P} {crit_uz} {'eng past' if least else 'yetakchi'} {what_uz}: {label(top)} — {val(top)}.{second}"
        return f"{'Меньше всего' if least else 'Лидер'} ({what_ru}) {P} {crit_ru}: {label(top)} — {val(top)}.{second}"
    return sql, basis(br, bu), ans


def _count_entity(s: Slots, lang: str, P: str):
    uz = lang == "uz"
    if s.entity == "broker":
        w = [f"region = '{esc(s.region)}'"] if s.region else []
        sql = f"SELECT COUNT(*) AS brokers_count FROM brokers{_where(w)}"
        reg = f" ({s.region})" if s.region else ""

        def ans(c, r):
            return (f"Ro'yxatda{reg} {n(r[0][0])} ta broker idorasi bor." if uz
                    else f"Брокерских контор{reg}: {n(r[0][0])}.")
        return sql, "Manba: brokers" if uz else "Источник: brokers", ans
    if s.entity == "participant":
        w = []
        if s.region:
            w.append(f"region = '{esc(s.region)}'")
        if s.role:
            w.append(f"role = '{s.role}'")
        if s.vat:
            w.append("is_vat_payer = 0" if s.vat_neg else "is_vat_payer = 1")
        sql = f"SELECT COUNT(*) AS participants_count FROM participants{_where(w)}"
        desc_ru = ", ".join(filter(None, [f"роль: {s.role}" if s.role else "", ("не плательщики НДС" if s.vat_neg else "плательщики НДС") if s.vat else "",
                                          f"регион: {s.region}" if s.region else ""]))
        desc_uz = ", ".join(filter(None, [f"rol: {s.role}" if s.role else "", ("QQS to'lovchisi emaslar" if s.vat_neg else "QQS to'lovchilari") if s.vat else "",
                                          f"hudud: {s.region}" if s.region else ""]))

        def ans(c, r):
            return (f"Ro'yxatda {n(r[0][0])} ta ishtirokchi ({desc_uz or 'barchasi'})." if uz
                    else f"Участников торгов ({desc_ru or 'всего'}): {n(r[0][0])}.")
        return sql, ("Manba: participants" if uz else "Источник: participants"), ans
    # contracts
    w = []
    if s.currency:
        w.append(f"currency = '{'Узбекский сум' if s.currency == 'UZS' else 'Доллар США'}'")
    if s.contract_type:
        w.append(f"contract_type = '{s.contract_type}'")
    if s.form:
        w.append(f"contract_form = '{s.form}'")
    if s.years:
        w.append(f"registration_date >= '{s.years[0]}-01-01' AND registration_date < '{s.years[-1] + 1}-01-01'")
    if s.product:
        w.append("(" + " OR ".join(f"ulower(product_name) LIKE '{p}'" for p in PROD[s.product][2]) + ")")
    if s.region:
        from app.core.regions import UZ_TO_RU

        w.append(f"region = '{esc(UZ_TO_RU.get(s.region, s.region))}'")
    sql = f"SELECT COUNT(*) AS contracts_count FROM contracts{_where(w)}"
    cond = " AND ".join(w)

    def ans(c, r):
        return (f"Shartnomalar soni: {n(r[0][0])} ta." if uz else f"Контрактов: {n(r[0][0])}.")
    return sql, ("Manba: contracts" if uz else "Источник: contracts") + (f" ({cond})" if cond else ""), ans


def _rate(s: Slots, lang: str, P: str):
    uz = lang == "uz"
    if s.day:
        sql = f"SELECT rate_date, rate FROM usd_rates WHERE rate_date = '{s.day}'"

        def ans(c, r):
            if not r:
                return None
            return (f"{ddmmyyyy(r[0][0])} kuni dollar kursi: 1 USD = {n(r[0][1])} so‘m." if uz
                    else f"Курс доллара на {ddmmyyyy(r[0][0])}: 1 USD = {n(r[0][1])} сум.")
        return sql, ("Manba: usd_rates" if uz else "Источник: usd_rates"), ans
    w = []
    if s.years:
        if s.month:
            w.append(f"rate_date LIKE '{s.years[0]}-{s.month:02d}-%'")
        else:
            w.append(f"rate_date >= '{s.years[0]}-01-01' AND rate_date < '{s.years[-1] + 1}-01-01'")
    if not w:
        sql = "SELECT rate_date, rate FROM usd_rates ORDER BY rate_date DESC LIMIT 1"

        def ans(c, r):
            return (f"Ma'lumotlardagi oxirgi kurs ({ddmmyyyy(r[0][0])}): 1 USD = {n(r[0][1])} so‘m." if uz
                    else f"Последний курс в данных ({ddmmyyyy(r[0][0])}): 1 USD = {n(r[0][1])} сум.")
        return sql, ("Manba: usd_rates" if uz else "Источник: usd_rates"), ans
    sql = (f"SELECT ROUND(AVG(rate), 2) AS avg_rate, MIN(rate) AS min_rate, MAX(rate) AS max_rate, COUNT(*) AS days "
           f"FROM usd_rates{_where(w)}")

    def ans(c, r):
        if not r[0][3]:
            return None
        a, lo, hi, d = r[0]
        return (f"{P} o'rtacha dollar kursi: 1 USD = {n(a)} so‘m (min {n(lo)}, max {n(hi)}; {n(d)} kun)." if uz
                else f"Средний курс доллара {P}: 1 USD = {n(a)} сум (мин. {n(lo)}, макс. {n(hi)}; {n(d)} дней).")
    return sql, ("Manba: usd_rates" if uz else "Источник: usd_rates"), ans


def _lookup(s: Slots, lang: str, t: str):
    uz = lang == "uz"
    if s.deal_no:
        sql = ("SELECT v.deal_no, v.deal_date, v.status, v.amount, v.currency, ROUND(v.amount_uzs, 2) AS amount_uzs, "
               "v.usd_rate, v.product_name, v.quantity, v.lot_size, v.unit, v.delivered_lots, v.payment_date, "
               "v.delivery_date, v.region, v.contract_no, v.seller_inn, ps.name AS seller_name, v.buyer_inn, "
               "pb.name AS buyer_name, v.seller_broker, bs.name AS seller_broker_name, v.buyer_broker, "
               "bb.name AS buyer_broker_name, v.trade_type, v.contract_form FROM v_deals v "
               "LEFT JOIN participants ps ON ps.inn = v.seller_inn LEFT JOIN participants pb ON pb.inn = v.buyer_inn "
               "LEFT JOIN brokers bs ON bs.broker_code = v.seller_broker "
               f"LEFT JOIN brokers bb ON bb.broker_code = v.buyer_broker WHERE v.deal_no = {int(s.deal_no)}")

        def ans(c, r):
            d = dict(zip(c, r[0]))
            usd = d["currency"] == "Доллар США"
            cur = "USD" if usd else ("so‘m" if uz else "сум")
            som = "so‘m" if uz else "сум"
            amt = money1(d['amount'], lang, usd=usd) + (f" = {money1(d['amount_uzs'], lang)} (kurs {n(d['usd_rate'])})" if usd and uz
                                                else f" = {money1(d['amount_uzs'], lang)} (курс {n(d['usd_rate'])})" if usd else "")
            pay = ddmmyyyy(d["payment_date"]) if d["payment_date"] else ("to'lanmagan" if uz else "нет")
            dlv = ddmmyyyy(d["delivery_date"]) if d["delivery_date"] else ("yetkazilmagan" if uz else "нет")
            if uz:
                first = _lookup_focus_uz(t, d, amt, pay, dlv)
                return (first + f"\nBitim № {d['deal_no']} ({ddmmyyyy(d['deal_date'])}): {d['product_name']}; summa {amt}; "
                        f"holat: {d['status']}; lotlar: {n(d['quantity'])}, yetkazilgan: {n(d['delivered_lots'])}; "
                        f"to'lov: {pay}, yetkazish: {dlv}.\nSotuvchi: {d['seller_name']} (STIR {d['seller_inn']}), "
                        f"broker {d['seller_broker']} {d['seller_broker_name']}; xaridor: {d['buyer_name']} "
                        f"(STIR {d['buyer_inn']}), broker {d['buyer_broker']} {d['buyer_broker_name']}.")
            first = _lookup_focus_ru(t, d, amt, pay, dlv)
            return (first + f"\nСделка № {d['deal_no']} от {ddmmyyyy(d['deal_date'])}: {d['product_name']}; сумма {amt}; "
                    f"состояние: {d['status']}; лотов: {n(d['quantity'])}, поставлено: {n(d['delivered_lots'])}; "
                    f"оплата: {pay}, поставка: {dlv}.\nПродавец: {d['seller_name']} (ИНН {d['seller_inn']}), "
                    f"брокер {d['seller_broker']} {d['seller_broker_name']}; покупатель: {d['buyer_name']} "
                    f"(ИНН {d['buyer_inn']}), брокер {d['buyer_broker']} {d['buyer_broker_name']}.")
        return sql, ("Manba: deals + participants + brokers + usd_rates" if uz
                     else "Источник: deals + participants + brokers + usd_rates"), ans
    if s.contract_no:
        sql = ("SELECT c.contract_no, c.product_name, c.base_price, c.currency, c.unit, c.lot_size, c.seller_inn, "
               "p.name AS seller_name, c.region, c.contract_type, c.contract_form, c.payment_days, c.delivery_days, "
               "c.registration_date, c.valid_until, c.product_category, c.tn_ved_code, "
               "(SELECT COUNT(*) FROM deals d WHERE d.contract_no = c.contract_no) AS deals_count FROM contracts c "
               f"LEFT JOIN participants p ON p.inn = c.seller_inn WHERE c.contract_no = '{esc(s.contract_no)}'")

        def ans(c, r):
            d = dict(zip(c, r[0]))
            cur = "USD" if d["currency"] == "Доллар США" else ("so‘m" if uz else "сум")
            if uz:
                return (f"Shartnoma № {d['contract_no']}: {d['product_name']}, bazis narx {money1(d['base_price'], lang, usd=d['currency'] == 'Доллар США')} / {d['unit']}.\n"
                        f"Sotuvchi: {d['seller_name']} (STIR {d['seller_inn']}); hudud: {d['region']}; "
                        f"{d['contract_type']}, {d['contract_form']}; to'lov muddati {n(d['payment_days'])} kun, "
                        f"yetkazish {n(d['delivery_days'])} kun; amal qiladi {ddmmyyyy(d['registration_date'])}–"
                        f"{ddmmyyyy(d['valid_until'])}; bitimlar: {n(d['deals_count'])} ta.")
            return (f"Контракт № {d['contract_no']}: {d['product_name']}, базисная цена {money1(d['base_price'], lang, usd=d['currency'] == 'Доллар США')} за {d['unit']}.\n"
                    f"Продавец: {d['seller_name']} (ИНН {d['seller_inn']}); регион: {d['region']}; "
                    f"{d['contract_type']}, {d['contract_form']}; срок оплаты {n(d['payment_days'])} дн., "
                    f"поставки {n(d['delivery_days'])} дн.; действует {ddmmyyyy(d['registration_date'])}–"
                    f"{ddmmyyyy(d['valid_until'])}; сделок по контракту: {n(d['deals_count'])}.")
        return sql, ("Manba: contracts + participants" if uz else "Источник: contracts + participants"), ans
    if s.broker:
        sql = ("SELECT b.broker_code, b.name, b.inn, b.region, (SELECT COUNT(*) FROM deals d WHERE d.seller_broker = "
               "b.broker_code OR d.buyer_broker = b.broker_code) AS deals_count FROM brokers b "
               f"WHERE b.broker_code = '{s.broker}'")

        def ans(c, r):
            code, name, inn, reg, k = r[0]
            return (f"{code} — {name}, STIR {inn}, hudud: {reg}.\nUshbu broker ishtirokidagi bitimlar: {n(k)} ta." if uz
                    else f"{code} — {name}, ИНН {inn}, регион: {reg}.\nСделок с участием брокера: {n(k)}.")
        return sql, ("Manba: brokers" if uz else "Источник: brokers"), ans
    if s.inn:
        sql = ("SELECT p.inn, p.name, p.region, p.activity_type, p.role, CASE p.is_vat_payer WHEN 1 THEN 'Да' ELSE 'Нет' "
               "END AS vat_payer, (SELECT COUNT(*) FROM deals d WHERE d.seller_inn = p.inn) AS deals_as_seller, "
               "(SELECT COUNT(*) FROM deals d WHERE d.buyer_inn = p.inn) AS deals_as_buyer FROM participants p "
               f"WHERE p.inn = '{s.inn}' UNION ALL SELECT b.inn, b.name, b.region, 'Брокер ' || b.broker_code, NULL, "
               f"NULL, NULL, NULL FROM brokers b WHERE b.inn = '{s.inn}'")

        def ans(c, r):
            d = dict(zip(c, r[0]))
            if d["role"] is None:
                return (f"STIR {d['inn']} — {d['name']} ({d['activity_type']}), hudud: {d['region']}." if uz
                        else f"ИНН {d['inn']} — {d['name']} ({d['activity_type']}), регион: {d['region']}.")
            vat = ("Ha, QQS to'lovchisi" if d["vat_payer"] == "Да" else "Yo'q, QQS to'lovchisi emas") if uz else \
                ("Да, плательщик НДС" if d["vat_payer"] == "Да" else "Нет, не плательщик НДС")
            if uz:
                return (f"STIR {d['inn']} — {d['name']}. {vat}.\nHudud: {d['region']}; faoliyat: {d['activity_type']}; "
                        f"rol: {d['role']}; bitimlar: sotuvchi sifatida {n(d['deals_as_seller'])}, xaridor sifatida "
                        f"{n(d['deals_as_buyer'])}.")
            return (f"ИНН {d['inn']} — {d['name']}. {vat}.\nРегион: {d['region']}; вид деятельности: {d['activity_type']}; "
                    f"роль: {d['role']}; сделок как продавец: {n(d['deals_as_seller'])}, как покупатель: "
                    f"{n(d['deals_as_buyer'])}.")
        return sql, ("Manba: participants" if uz else "Источник: participants"), ans
    raise NotFound({"ru": "", "uz": ""})


def _lookup_focus_ru(t: str, d: dict, amt: str, pay: str, dlv: str) -> str:
    if re.search(r"покупател", t):
        return f"Покупатель: {d['buyer_name']} (ИНН {d['buyer_inn']})."
    if re.search(r"брокер", t):
        if re.search(r"покуп", t):
            return f"Брокер покупателя: {d['buyer_broker']} — {d['buyer_broker_name']}."
        return f"Брокер продавца: {d['seller_broker']} — {d['seller_broker_name']}."
    if re.search(r"продав", t):
        return f"Продавец: {d['seller_name']} (ИНН {d['seller_inn']})."
    if re.search(r"оплач|постав", t) and re.search(r"когда|дата", t):
        return f"Оплата: {pay}; поставка: {dlv}."
    if re.search(r"состояни|статус|поставлено", t):
        return f"Состояние: {d['status']}; поставлено {n(d['delivered_lots'])} из {n(d['quantity'])} лотов."
    return f"Сумма сделки № {d['deal_no']}: {amt}."


def _lookup_focus_uz(t: str, d: dict, amt: str, pay: str, dlv: str) -> str:
    if re.search(r"broker", t):
        if re.search(r"xaridor", t):
            return f"Xaridor brokeri: {d['buyer_broker']} — {d['buyer_broker_name']}."
        return f"Sotuvchi brokeri: {d['seller_broker']} — {d['seller_broker_name']}."
    if re.search(r"xaridor|харидор", t):
        return f"Xaridor: {d['buyer_name']} (STIR {d['buyer_inn']})."
    if re.search(r"sotuvchi|сотувчи", t):
        return f"Sotuvchi: {d['seller_name']} (STIR {d['seller_inn']})."
    if re.search(r"qachon|sana", t) and re.search(r"to'la|yetkaz", t):
        return f"To'lov: {pay}; yetkazish: {dlv}."
    if re.search(r"holat|status|yetkazilgan", t):
        return f"Holati: {d['status']}; {n(d['quantity'])} lotdan {n(d['delivered_lots'])} tasi yetkazilgan."
    return f"Bitim № {d['deal_no']} summasi: {amt}."


def suggestions(s: Slots, lang: str) -> list[str]:
    """Up to 3 follow-up questions the rule engine can answer, built from the current slots."""
    y = s.years[0] if len(s.years) == 1 else 2025
    uz = lang == "uz"
    prod = PROD[s.product][4 if uz else 3] if s.product and not s.exact_name else None
    out: list[str] = []
    if prod:
        out += ([f"{y}-yilda {prod} bo'yicha aylanma qancha?", f"{y}-yilda {prod} necha tonna sotilgan?",
                 f"{y}-yilda {prod} bir tonnasining o'rtacha narxi qancha?"] if uz else
                [f"Какой оборот по товару {prod} в {y} году?", f"Сколько тонн по товару {prod} продано в {y} году?",
                 f"Какова средневзвешенная цена за тонну по товару {prod} в {y} году?"])
    elif s.metric == "count":
        out += ([f"{y}-yilda aylanma qancha?", f"{y}-yilda qaysi viloyatda eng ko'p bitim tuzilgan?",
                 f"{y}-yilda eng ko'p bitim tuzgan broker qaysi?"] if uz else
                [f"Какой оборот в {y} году?", f"В каком регионе больше всего сделок в {y} году?",
                 f"Какой брокер заключил больше всего сделок в {y} году?"])
    elif s.metric in ("sum", "avg_amount", "median"):
        out += ([f"{y}-yilda nechta bitim tuzilgan?", f"{y}-yilda aylanma bo'yicha yetakchi tovar toifasi qaysi?",
                 f"{y}-yilda summa bo'yicha eng yirik bitim qaysi?"] if uz else
                [f"Сколько сделок было в {y} году?", f"Какая категория товаров лидер по обороту в {y} году?",
                 f"Какая самая крупная по сумме сделка в {y} году?"])
    elif s.metric == "top":
        out += ([f"{y}-yilda aylanma bo'yicha yetakchi sotuvchi kompaniya qaysi?",
                 f"{y}-yilda qaysi viloyatda aylanma eng katta?", f"{y}-yilda nechta bitim tuzilgan?"] if uz else
                [f"Какой продавец лидер по обороту в {y} году?", f"В каком регионе наибольший оборот в {y} году?",
                 f"Сколько сделок было в {y} году?"])
    elif s.metric == "lookup" and s.deal_no:
        out += ([f"{s.deal_no}-raqamli bitimda xaridor kim?", f"{s.deal_no}-raqamli bitimda sotuvchining brokeri kim?"]
                if uz else [f"Кто покупатель по сделке № {s.deal_no}?", f"Кто брокер продавца по сделке № {s.deal_no}?"])
    else:
        out += ([f"{y}-yilda nechta bitim tuzilgan?", f"{y}-yilda aylanma qancha?"] if uz else
                [f"Сколько сделок было в {y} году?", f"Какой оборот в {y} году?"])
    return out[:3]


def last_rate_line(lang: str) -> str:
    r = _one("SELECT rate_date, rate FROM usd_rates ORDER BY rate_date DESC LIMIT 1")[0]
    return (f"Ma'lumotlarda prognoz yo'q. Oxirgi ma'lum kurs ({ddmmyyyy(r[0])}): 1 USD = {n(r[1])} so‘m." if lang == "uz"
            else f"Прогнозов в данных нет. Последний известный курс ({ddmmyyyy(r[0])}): 1 USD = {n(r[1])} сум.")


def cap(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def _maxmin_text(r, lang, m, P):
    uz = lang == "uz"
    d = r[0]
    is_usd = d[3] == "Доллар США"
    amount = money1(d[2], lang, usd=is_usd) + (f" ≈ {money1(d[4], lang)}" if is_usd else "")
    if uz:
        kind = "eng yirik" if m == "max_deal" else "eng kichik"
        return (f"{P} summa bo'yicha {kind} bitim — № {d[0]}: {amount}.\n"
                f"Sana: {ddmmyyyy(d[1])}, tovar: {d[5]}, holat: {d[6]}; bekor qilingan bitimlar hisobga olinmadi.")
    kind = "Самая крупная" if m == "max_deal" else "Самая мелкая"
    return (f"{kind} по сумме сделка {P} — № {d[0]}: {amount}.\n"
            f"Дата: {ddmmyyyy(d[1])}, товар: {d[5]}, состояние: {d[6]}; аннулированные не учитывались.")
