"""Independent ground-truth builder for the exchange-deals QA agent.

Reads ONLY the raw CSVs in ../data (no backend code / DB) and writes golden.jsonl.
Run:  python eval/build_golden.py
"""
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load, num, dt  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden.jsonl")
ANN = "Аннулирован(Не оплачен)"

deals, con, par, br, usd = load()

# ---------- derived columns ----------
d = deals.copy()
d["qty"] = num(d["Количество"])
d["lot"] = num(d["Лот"])
d["amt"] = num(d["Сумма сделки"])
d["start"] = num(d["Стартовая цена"])
d["dlv"] = num(d["Поставлено"])
d["dd"] = dt(d["Дата сделки"])
d["pd"] = dt(d["Дата оплаты"])
d["vd"] = dt(d["Дата поставки"])
d["year"] = d["dd"].dt.year
d["month"] = d["dd"].dt.month
d["vol"] = d["qty"] * d["lot"]
cc = con.copy()
cc["base"] = num(cc["Базисная цена"])
cc["pay_term"] = num(cc["Срок оплаты"])
cc["dlv_term"] = num(cc["Срок поставки"])
d = d.merge(
    cc[["Номер контракта", "Валюта", "Категория товара", "pay_term", "dlv_term"]],
    on="Номер контракта", how="left", validate="many_to_one",
)
rates = usd.assign(dd=dt(usd["Дата"]), rate=num(usd["Курс"]))[["dd", "rate"]]
d = d.merge(rates, on="dd", how="left", validate="many_to_one")
assert d["rate"].notna().all()
d["is_usd"] = d["Валюта"] == "Доллар США"
d["amt_uzs"] = d["amt"].where(~d["is_usd"], d["amt"] * d["rate"])
ok = d["Состояние сделки"] != ANN  # "без аннулированных"

parname = par.set_index("ИНН")["Наименование"]
brname = br.set_index("Код брокера")["Наименование"]
brreg = br.set_index("Код брокера")["Регион"]
dn = d.set_index("Номер сделки")

Q = []


def add(qid, lang, cat, question, value, unit, notes, kind="exact", tol=0.0):
    if isinstance(value, float):
        value = round(value, 4)
    Q.append({
        "id": qid, "lang": lang, "category": cat, "question": question,
        "expected": {"value": value, "unit": unit, "notes": notes},
        "kind": kind, "tolerance": tol,
    })


def y(yr):
    return d["year"] == yr


# ===================== COUNTS =====================
add("c01", "ru", "count", "Сколько всего сделок было заключено в 2023 году?",
    int(y(2023).sum()), "сделок", "Все строки deals с годом Даты сделки = 2023, любые статусы.")
add("c02", "uz", "count", "2025-yilda bekor qilinganlarni hisobga olmaganda nechta bitim tuzilgan?",
    int((y(2025) & ok).sum()), "bitim", f"Год 2025, Состояние != '{ANN}'.")
m = (d["year"] == 2024) & (d["month"] == 3)
add("c03", "ru", "count", "Сколько сделок прошло в марте 2024 года?",
    int(m.sum()), "сделок", "Дата сделки в 03.2024, все статусы.")
m = (d["year"] == 2024) & (d["month"] == 6) & (d["Регион"] == "Samarqand viloyati")
add("c04", "uz", "count", "2024-yil iyun oyida Samarqand viloyatida nechta bitim bo‘lgan?",
    int(m.sum()), "bitim", "Регион сделки = 'Samarqand viloyati' (регион склада продавца), 06.2024, все статусы.")
m = y(2022) & (d["Состояние сделки"] == ANN)
add("c05", "ru", "count", "Сколько сделок за 2022 год было аннулировано из-за неоплаты?",
    int(m.sum()), "сделок", f"Состояние = '{ANN}', год 2022.")
add("c06", "uz", "count", "Тошкент шаҳрида нечта брокерлик идораси рўйхатдан ўтган?",
    int((br["Регион"] == "Toshkent shahri").sum()), "broker",
    "brokers.csv, Регион = 'Toshkent shahri' (Ташкент-город, НЕ Ташкентская область). Uzbek Cyrillic question.")
add("c07", "ru", "count", "Сколько участников торгов являются плательщиками НДС?",
    int((par["Плательщик НДС"] == "Да").sum()), "участников", "participants.csv, Плательщик НДС = 'Да'.")
add("c08", "uz", "count", "Ro‘yxatda nechta sotuvchi kompaniya bor?",
    int((par["Роль"] == "Продавец").sum()), "kompaniya", "participants.csv, Роль = 'Продавец'.")
m = y(2025) & (d["Регион"] == "Namangan viloyati")
add("c09", "ru", "count", "Сколько сделок было по Наманганской области в 2025 году?",
    int(m.sum()), "сделок",
    "Регион в deals латиницей: 'Namangan viloyati' (= 'Наманганская область' в contracts.csv). Все статусы.")
m = y(2024) & (d["Тип контракта"] == "Экспортный")
add("c10", "uz", "count", "2024-yilda nechta eksport bitimi tuzilgan?",
    int(m.sum()), "bitim", "Тип контракта = 'Экспортный', год 2024, все статусы.")
add("c11", "ru", "count", "Сколько фьючерсных сделок было за весь период?",
    int((d["Форма контракта"] == "Фьючерс").sum()), "сделок", "Форма контракта = 'Фьючерс', 2022–2026, все статусы.")
add("c12", "uz", "count", "Nechta shartnoma AQSh dollarida tuzilgan?",
    int((con["Валюта"] == "Доллар США").sum()), "shartnoma", "contracts.csv, Валюта = 'Доллар США'.")
never = set(par["ИНН"]) - set(d["ИНН продавца"]) - set(d["ИНН покупателя"])
add("c13", "ru", "count", "Сколько зарегистрированных участников ни разу не участвовали ни в одной сделке?",
    len(never), "участников", f"ИНН из participants.csv, отсутствующие в обеих колонках ИНН deals: {sorted(never)}.")
m = (d["Регион"] == "Toshkent viloyati")
add("c14", "uz", "count", "Toshkent viloyatidagi omborlardan jami nechta bitim bo‘lgan (Toshkent shahri bundan mustasno)?",
    int(m.sum()), "bitim", "Регион = 'Toshkent viloyati' только; 'Toshkent shahri' не включён. Все годы, все статусы.")

# ===================== SUMS =====================
m = y(2024) & ok
add("s01", "ru", "sum",
    "Каков общий оборот биржи в сумах за 2024 год без учёта аннулированных сделок? Долларовые сделки пересчитайте по курсу на дату сделки.",
    float(d.loc[m, "amt_uzs"].sum()), "сум",
    "Сумма сделки; для контрактов в USD × курс usd_rates на Дату сделки. Исключено только 'Аннулирован(Не оплачен)'.", tol=0.001)
m = y(2025) & ok & ~d["is_usd"]
add("s02", "uz", "sum", "2025-yilda so‘mdagi (ichki) bitimlarning umumiy summasi qancha, bekor qilinganlarsiz?",
    float(d.loc[m, "amt"].sum()), "so‘m", "Только контракты в UZS (Внутренний), год 2025, без аннулированных.", tol=0.001)
m = y(2023) & ok & d["is_usd"]
add("s03", "ru", "sum", "Какая общая сумма экспортных сделок в долларах США за 2023 год без аннулированных?",
    float(d.loc[m, "amt"].sum()), "USD", "Контракты в USD (= все Экспортные), год 2023, сумма в USD без конвертации.", tol=0.001)
m = y(2026) & ok & d["is_usd"]
add("s04", "uz", "sum",
    "2026-yildagi eksport bitimlarining so‘mdagi summasi qancha (bitim kunidagi dollar kursi bo‘yicha, bekor qilinganlarsiz)?",
    float(d.loc[m, "amt_uzs"].sum()), "so‘m", "USD-сделки 2026 × курс на дату сделки, без аннулированных.", tol=0.001)
m = ok & d["is_usd"]
add("s05", "ru", "sum", "Каков суммарный оборот в долларах США по всем экспортным сделкам за весь период (без аннулированных)?",
    float(d.loc[m, "amt"].sum()), "USD", "Все годы, Валюта контракта = USD, без аннулированных.", tol=0.001)
m = y(2022) & ok & (d["Регион"] == "Buxoro viloyati")
add("s06", "uz", "sum",
    "2022-yilda Buxoro viloyatidagi bitimlar umumiy aylanmasi so‘mda qancha (bekor qilinganlarsiz, dollar bitimlari kurs bo‘yicha)?",
    float(d.loc[m, "amt_uzs"].sum()), "so‘m", "Регион = 'Buxoro viloyati', 2022, без аннулированных, USD×курс.", tol=0.001)

# ===================== TOP-N =====================
m = y(2024) & ok
g = d[m].groupby("Брокер продавца")["amt_uzs"].sum().sort_values(ascending=False)
add("t01", "ru", "top",
    "Какой брокер на стороне продавца имел наибольший оборот в 2024 году (в сумах, без аннулированных, доллары по курсу)?",
    [g.index[0], brname[g.index[0]]], "код, наименование",
    f"groupby Брокер продавца, sum amt_uzs. Оборот лидера = {g.iloc[0]:.2f}; 2-е место {g.index[1]} = {g.iloc[1]:.2f}.")
m = y(2025)
g = d[m].groupby("Брокер покупателя").size().sort_values(ascending=False)
add("t02", "uz", "top", "2025-yilda xaridor tomonida eng ko‘p bitim tuzgan broker qaysi?",
    [g.index[0], brname[g.index[0]]], "kod, nomi",
    f"groupby Брокер покупателя, count, год 2025, все статусы. Лидер {g.iloc[0]} сделок; 2-е {g.index[1]}={g.iloc[1]}.")
m = y(2023) & ok
g = d[m].groupby("Категория товара")["amt_uzs"].sum().sort_values(ascending=False)
add("t03", "ru", "top", "Какая категория товаров была лидером по обороту в сумах в 2023 году (без аннулированных)?",
    g.index[0], "категория", f"contracts.Категория товара, sum amt_uzs. Лидер {g.iloc[0]:.2f}; 2-е {g.index[1]}={g.iloc[1]:.2f}.")
m = y(2024) & ok
g = d[m].groupby("ИНН продавца")["amt_uzs"].sum().sort_values(ascending=False)
add("t04", "uz", "top",
    "2024-yilda savdo summasi bo‘yicha eng yirik sotuvchi kompaniya qaysi (so‘mda, bekor qilinganlarsiz)?",
    [g.index[0], parname[g.index[0]]], "STIR, nomi",
    f"groupby ИНН продавца, sum amt_uzs. Сумма {g.iloc[0]:.2f}; 2-е {g.index[1]}={g.iloc[1]:.2f}.")
m = y(2025) & ok
g = d[m].groupby("ИНН покупателя")["amt_uzs"].sum().sort_values(ascending=False)
add("t05", "ru", "top",
    "Какой покупатель потратил больше всего денег на бирже в 2025 году (в сумах, без аннулированных)?",
    [g.index[0], parname[g.index[0]]], "ИНН, наименование",
    f"groupby ИНН покупателя, sum amt_uzs. Сумма {g.iloc[0]:.2f}; 2-е {g.index[1]}={g.iloc[1]:.2f}.")
g = d[y(2026)].groupby("Регион").size().sort_values(ascending=False)
add("t06", "uz", "top", "2026-yilda qaysi viloyatda eng ko‘p bitim tuzilgan?",
    g.index[0], "hudud", f"groupby Регион (склад продавца), count, все статусы. {g.iloc[0]}; 2-е {g.index[1]}={g.iloc[1]}.")
g = d[y(2022)].groupby("Наименование товара").size().sort_values(ascending=False)
add("t07", "ru", "top",
    "Назовите три наименования товара с наибольшим числом сделок в 2022 году (по наименованию, как оно записано в реестре).",
    list(g.index[:3]), "наименования",
    f"groupby Наименование товара (строка как есть, без нормализации), count. {g.head(4).to_dict()}.")
g = d[ok].groupby("Брокер продавца").size().add(d[ok].groupby("Брокер покупателя").size(), fill_value=0).sort_values(ascending=False)
add("t08", "uz", "top",
    "Butun davr mobaynida (sotuvchi yoki xaridor tomonida) eng ko‘p bitimda qatnashgan broker qaysi, bekor qilinganlarsiz?",
    [g.index[0], brname[g.index[0]]], "kod, nomi",
    f"count(Брокер продавца)+count(Брокер покупателя), без аннулированных; сделка с одним брокером на обеих сторонах считается 2 раза. {g.iloc[0]:.0f}; 2-е {g.index[1]}={g.iloc[1]:.0f}.")
g = d[ok & y(2025)].groupby("Категория товара").size().sort_values(ascending=False)
add("t09", "ru", "top", "Какая категория товаров была самой популярной по количеству сделок в 2025 году (без аннулированных)?",
    g.index[0], "категория", f"count by Категория товара. {g.head(3).to_dict()}.")

# ===================== LOOKUPS =====================
samp = d[d["year"] == 2025].sample(6, random_state=42)
r = samp.iloc[0]
add("l01", "ru", "lookup", f"Какова сумма сделки № {r['Номер сделки']}?",
    float(r["amt"]), "USD" if r["is_usd"] else "сум", f"deals.Сумма сделки строки {r['Номер сделки']}; валюта контракта {r['Валюта']}.", tol=0.0001)
r = samp.iloc[1]
add("l02", "uz", "lookup", f"{r['Номер сделки']}-raqamli bitimda xaridor kim bo‘lgan?",
    [r["ИНН покупателя"], parname[r["ИНН покупателя"]]], "STIR, nomi", "ИНН покупателя → participants.Наименование.")
r = d[d["Состояние сделки"] == "Исполнен(Частично)"].sample(1, random_state=7).iloc[0]
add("l03", "ru", "lookup", f"В каком состоянии сделка № {r['Номер сделки']} и сколько лотов по ней поставлено?",
    [r["Состояние сделки"], int(r["dlv"]), int(r["qty"])], "состояние, поставлено лотов, куплено лотов",
    "Состояние сделки, Поставлено, Количество.")
r = samp.iloc[2]
add("l04", "uz", "lookup", f"{r['Номер сделки']}-sonli bitimda sotuvchining brokeri kim edi?",
    [r["Брокер продавца"], brname[r["Брокер продавца"]]], "kod, nomi", "deals.Брокер продавца → brokers.Наименование.")
cs = cc.sample(3, random_state=11)
c0 = cs.iloc[0]
add("l05", "ru", "lookup", f"Какая базисная цена указана в контракте № {c0['Номер контракта']}?",
    float(c0["base"]), f"{c0['Валюта']} за {c0['Единица измерения']}", "contracts.Базисная цена (за единицу измерения).", tol=0.0001)
c1 = cs.iloc[1]
add("l06", "uz", "lookup", f"{c1['Номер контракта']}-raqamli shartnoma bo‘yicha sotuvchi kim?",
    [c1["ИНН продавца"], parname[c1["ИНН продавца"]]], "STIR, nomi", "contracts.ИНН продавца → participants.")
add("l07", "ru", "lookup", "Какой был курс доллара 15.06.2025?",
    float(num(usd.loc[usd["Дата"] == "15.06.2025", "Курс"]).iloc[0]), "сум за 1 USD", "usd_rates.csv, Дата = 15.06.2025 (воскресенье — курс всё равно есть).", tol=0.0)
add("l08", "uz", "lookup", "BK045 kodli broker qanday nomlanadi va qaysi hududda joylashgan?",
    [brname["BK045"], brreg["BK045"]], "nomi, hudud", "brokers.csv, Код брокера = BK045.")
add("l09", "ru", "lookup", "Какой ИНН у брокерской конторы BK017?",
    br.set_index("Код брокера").loc["BK017", "ИНН"], "ИНН", "brokers.csv.")
p0 = par[par["Роль"] == "Продавец"].sample(1, random_state=3).iloc[0]
add("l10", "uz", "lookup", f"STIR {p0['ИНН']} bo‘lgan kompaniya qanday nomlanadi va QQS to‘lovchisimi?",
    [p0["Наименование"], p0["Плательщик НДС"]], "nomi, QQS", "participants.csv.")
r = samp.iloc[3]
add("l11", "ru", "lookup", f"Когда была оплачена и когда поставлена сделка № {r['Номер сделки']}?",
    [r["Дата оплаты"] or None, r["Дата поставки"] or None], "дата оплаты, дата поставки", f"Состояние {r['Состояние сделки']}.")
r = d[d["is_usd"]].sample(1, random_state=5).iloc[0]
add("l12", "uz", "lookup", f"{r['Номер сделки']}-raqamli bitim summasi so‘mda qancha bo‘ladi (bitim kunidagi kurs bo‘yicha)?",
    float(r["amt_uzs"]), "so‘m", f"USD-сделка: {r['amt']} USD × курс {r['rate']} на {r['Дата сделки']}.", tol=0.0005)

# ===================== AVERAGES / PRICES / EXTREMES =====================
m = y(2024) & ok & ~d["is_usd"]
add("a01", "ru", "avg", "Какая средняя сумма сделки в сумах по внутренним сделкам за 2024 год без аннулированных?",
    float(d.loc[m, "amt"].mean()), "сум", "Среднее арифметическое Сумма сделки, UZS-контракты, 2024, без аннулированных.", tol=0.001)
m = y(2025) & ok & ~d["is_usd"]
add("a02", "uz", "avg", "2025-yilda ichki bitimlar summasining medianasi qancha (bekor qilinganlarsiz)?",
    float(d.loc[m, "amt"].median()), "so‘m", "Медиана Сумма сделки, UZS-контракты, 2025, без аннулированных.", tol=0.001)
m = (d["Наименование товара"] == "Сахар белый") & (d["year"] == 2025) & (d["month"] == 5) & ok
add("a03", "ru", "price",
    "Какова средневзвешенная цена за тонну товара «Сахар белый» в мае 2025 года (без аннулированных)?",
    float(d.loc[m, "amt"].sum() / d.loc[m, "vol"].sum()), "сум/тонна",
    f"Только наименование ровно 'Сахар белый' (НЕ 'САХАР-ПЕСОК'). Σсумма/Σ(Количество×Лот), {int(m.sum())} сделок.", tol=0.001)
CARB = ["Карбамид Марка Б", "Мочевина (карбамид) Марка Б", "КАРБАМИД МАРКА Б"]
m = d["Наименование товара"].isin(CARB) & (d["year"] == 2024) & (d["month"] == 10) & ok
add("a04", "uz", "price",
    "2024-yil oktabrda karbamid (B markali, barcha yozilish variantlari) bir tonnasining o‘rtacha tortilgan narxi qancha bo‘lgan (bekor qilinganlarsiz)?",
    float(d.loc[m, "amt"].sum() / d.loc[m, "vol"].sum()), "so‘m/tonna",
    f"Наименования {CARB}. Σсумма/Σ(Количество×Лот), {int(m.sum())} сделок, единица {d.loc[m,'Единица измерения'].unique().tolist()}.", tol=0.001)
x = d[y(2025) & ~d["is_usd"]].sort_values("amt", ascending=False).iloc[0]
add("a05", "ru", "extreme", "Какая самая крупная по сумме сделка в сумах за 2025 год (номер и сумма)?",
    [x["Номер сделки"], float(x["amt"])], "номер, сум",
    f"Max Сумма сделки среди UZS-контрактов 2025, любые статусы (статус лидера: {x['Состояние сделки']}).")
x = d[y(2023) & ~d["is_usd"]].sort_values("amt").iloc[0]
add("a06", "uz", "extreme", "2023-yilda so‘mdagi eng kichik summali bitim qaysi (raqami va summasi)?",
    [x["Номер сделки"], float(x["amt"])], "raqam, so‘m", f"Min Сумма сделки UZS 2023, любые статусы ({x['Состояние сделки']}).")
AI92 = ["БЕНЗИН АВТОМОБИЛЬНЫЙ Марка АИ-92", "Бензин Марка АИ-92"]
m = d["Наименование товара"].isin(AI92) & y(2025) & ok & (d["Единица измерения"] == "тонна")
add("a07", "ru", "price",
    "Сколько в среднем стоила тонна бензина АИ-92 в 2025 году (средневзвешенно, без аннулированных, только сделки в тоннах)?",
    float(d.loc[m, "amt"].sum() / d.loc[m, "vol"].sum()), "сум/тонна",
    f"Наименования {AI92}; ЛОВУШКА: этот товар продаётся и в литрах, и в тоннах — взяты только 'тонна'. {int(m.sum())} сделок.", tol=0.001)
m = y(2024) & ok
add("a08", "uz", "avg", "2024-yilda bitta bitimda o‘rtacha nechta lot sotib olingan (bekor qilinganlarsiz)?",
    float(d.loc[m, "qty"].mean()), "lot", "mean(Количество), 2024, без аннулированных.", tol=0.001)

# ===================== TIME LOGIC =====================
d["late"] = (d["vd"] - d["pd"]).dt.days > d["dlv_term"]
add("tm01", "ru", "time",
    "Сколько сделок за весь период были поставлены с нарушением срока поставки по контракту?",
    int(d["late"].sum()), "сделок",
    "Дата поставки − Дата оплаты (дни) > contracts.Срок поставки (срок отсчитывается от даты оплаты). Только сделки с датой поставки.")
add("tm02", "uz", "time", "2025-yilda tuzilgan bitimlardan nechtasi shartnomadagi yetkazib berish muddatidan kechikib yetkazilgan?",
    int((d["late"] & y(2025)).sum()), "bitim", "Как tm01, Дата сделки в 2025.")
m = y(2024) & d["pd"].notna()
add("tm03", "ru", "time", "Сколько в среднем дней проходило от заключения сделки до её оплаты в 2024 году?",
    float(((d.loc[m, "pd"] - d.loc[m, "dd"]).dt.days).mean()), "дней",
    "mean(Дата оплаты − Дата сделки) по сделкам 2024 с непустой датой оплаты.", tol=0.005)
add("tm04", "uz", "time", "2026-yilda nechta bitim qisman bajarilgan?",
    int((y(2026) & (d["Состояние сделки"] == "Исполнен(Частично)")).sum()), "bitim", "Состояние = 'Исполнен(Частично)', 2026.")
add("tm05", "ru", "time", "Сколько сделок по состоянию на 30.10.2026 находились в статусе «Ждёт оплату»?",
    int((d["Состояние сделки"] == "Ждёт оплату").sum()), "сделок",
    "Состояние = 'Ждёт оплату' (споты). Форварды/фьючерсы без оплаты имеют статус 'Заключен' и сюда НЕ входят.")
add("tm06", "uz", "time", "Nechta bitim to‘langan, lekin tovar hali yetkazilmagan?",
    int((d["Состояние сделки"] == "Оплачен").sum()), "bitim", "Состояние = 'Оплачен'.")
m = y(2025) & (d["Состояние сделки"] == "Исполнен(Частично)")
add("tm07", "ru", "time", "Сколько лотов в сумме не допоставлено по частично исполненным сделкам 2025 года?",
    int((d.loc[m, "qty"] - d.loc[m, "dlv"]).sum()), "лотов", "Σ(Количество − Поставлено) для 'Исполнен(Частично)', 2025.")
UNPAID = ["Ждёт оплату", "Заключен", "Новый", "Не подписан"]
add("tm08", "uz", "time",
    "30.10.2026 holatiga ko‘ra hali to‘lanmagan, lekin bekor ham qilinmagan bitimlar nechta (barcha holatlar bo‘yicha)?",
    int(d["Состояние сделки"].isin(UNPAID).sum()), "bitim", f"Состояния {UNPAID} (дата оплаты пуста, не аннулированы).")
m = d["pd"].notna()
add("tm09", "ru", "time", "Какой самый долгий срок (в днях) между сделкой и её оплатой за всю историю?",
    int((d.loc[m, "pd"] - d.loc[m, "dd"]).dt.days.max()), "дней", "max(Дата оплаты − Дата сделки).")

# ===================== TRICKY =====================
CU = sorted([n for n in d["Наименование товара"].unique() if "катод" in n.lower() or "медн" in n.lower()])
mcu = d["Наименование товара"].isin(CU)
add("x01", "ru", "tricky", "Сколько всего было сделок по медному катоду за весь период (все варианты написания и марки)?",
    int(mcu.sum()), "сделок", f"Наименования, совпавшие по 'катод'/'медн' (без учёта регистра): {CU}. Все статусы. Часть в USD, часть в UZS.")
m = mcu & y(2024) & ok
add("x02", "uz", "tricky", "2024-yilda mis katod jami necha tonna sotilgan (barcha yozilish variantlari, bekor qilinganlarsiz)?",
    float(d.loc[m, "vol"].sum()), "tonna", f"Σ(Количество×Лот) по {CU}, 2024, без аннулированных.", tol=0.0001)
m = mcu & ok
add("x03", "ru", "tricky",
    "Каков общий оборот по медному катоду в сумах за весь период без аннулированных (долларовые сделки по курсу на дату)?",
    float(d.loc[m, "amt_uzs"].sum()), "сум", f"{CU}; USD-контракты × курс на дату сделки + UZS-контракты.", tol=0.001)
same = d["Брокер продавца"] == d["Брокер покупателя"]
add("x04", "uz", "tricky", "2024-yilda sotuvchi va xaridor tomonida bir xil broker bo‘lgan nechta bitim bor?",
    int((same & y(2024)).sum()), "bitim", "Брокер продавца == Брокер покупателя, 2024, все статусы.")
add("x05", "uz", "tricky", "Тошкент шаҳридаги омборлардан 2023 йилда нечта битим тузилган?",
    int((y(2023) & (d["Регион"] == "Toshkent shahri")).sum()), "bitim",
    "Uzbek Cyrillic; Регион = 'Toshkent shahri' (= 'г. Ташкент' в contracts). Все статусы.")
m = (d["Регион"] == "Farg‘ona viloyati") & y(2025) & ok
add("x06", "ru", "tricky", "Какой оборот в сумах был по Ферганской области в 2025 году без аннулированных?",
    float(d.loc[m, "amt_uzs"].sum()), "сум", "Регион = 'Farg‘ona viloyati' (с апострофом U+2018), USD×курс.", tol=0.001)
COT = sorted([n for n in d["Наименование товара"].unique() if n.lower().replace("-", " ").startswith("хлопок сырец (спот)")])
m = d["Наименование товара"].isin(COT) & y(2025)
add("x07", "uz", "tricky", "2025-yilda paxta xomashyosi (spot, barcha navlar va yozilish variantlari) bo‘yicha nechta bitim bo‘lgan?",
    int(m.sum()), "bitim", f"Наименование начинается с 'Хлопок-сырец (спот)'/'Хлопок сырец (спот)' без учёта регистра; {len(COT)} вариантов. Форвард/фьючерс не включены.")
m = d["Наименование товара"].isin(AI92) & y(2025) & ok
add("x08", "ru", "tricky", "Сколько литров бензина АИ-92 продано в 2025 году в сделках, где единица измерения — литр (без аннулированных)?",
    float(d.loc[m & (d["Единица измерения"] == "литр"), "vol"].sum()), "литров",
    f"{AI92}, Единица = 'литр', Σ(Количество×Лот).", tol=0.0001)

# ===================== NO DATA TRAPS =====================
all_nums = set(d["Номер сделки"].astype(int))
gap = next(n for n in range(300000, 700000) if n not in all_nums)
assert not (d["year"] == 2021).any()
add("n01", "ru", "no_data", "Сколько сделок было заключено в 2021 году?", None, "",
    "Данные начинаются 03.01.2022 — за 2021 данных нет (не 0, а отсутствие периода).", kind="no_data")
assert str(gap) not in set(d["Номер сделки"])
add("n02", "uz", "no_data", f"{gap}-raqamli bitim summasi qancha?", None, "",
    f"Номер {gap} внутри диапазона, но пропущен (README: некоторые номера пропущены).", kind="no_data")
assert "BK999" not in set(br["Код брокера"])
add("n03", "ru", "no_data", "Как называется брокер с кодом BK999 и в каком он регионе?", None, "",
    "Брокеры только BK001–BK120.", kind="no_data")
assert not d["Наименование товара"].str.lower().str.contains("золот|oltin").any()
add("n04", "uz", "no_data", "Birjada oltin bo‘yicha nechta bitim tuzilgan va o‘rtacha narxi qancha?", None, "",
    "Ни одного наименования с 'золот'/'oltin' в deals и contracts.", kind="no_data")
add("n05", "ru", "no_data", f"Какой номер телефона и кто директор компании с ИНН {p0['ИНН']}?", None, "",
    "participants.csv не содержит телефонов и ФИО директоров (только ИНН, наименование, регион, вид деятельности, роль, НДС).",
    kind="no_data")
add("n06", "uz", "no_data", "2025-yil mart oyida Londondagi LME birjasida mis narxi qancha bo‘lgan?", None, "",
    "Внешние биржевые котировки отсутствуют в данных.", kind="no_data")
assert not (d["dd"] == pd.Timestamp("2024-05-12")).any()
add("n07", "ru", "no_data", "Какие сделки были заключены в воскресенье 12 мая 2024 года и на какую сумму?", None, "",
    "Торгов в выходные нет вообще (все сделки пн–пт). Приемлемо: 'сделок в этот день нет'; нельзя выдумывать сделки.",
    kind="no_data")
add("n08", "uz", "no_data", "15.06.2025 sanasida yevro kursi qancha bo‘lgan?", None, "",
    "usd_rates.csv содержит только курс USD.", kind="no_data")
assert d["dd"].max() == pd.Timestamp("2026-10-30")
add("n09", "ru", "no_data", "Какой оборот биржи был в ноябре 2026 года?", None, "",
    "Данные заканчиваются 30.10.2026 (курс есть до 31.10.2026, сделок после 30.10 нет).", kind="no_data")
assert not (usd["Дата"] == "01.01.2021").any()
add("n10", "uz", "no_data", "01.01.2021 sanasida dollar kursi qancha edi?", None, "",
    "usd_rates.csv начинается с 01.01.2022.", kind="no_data")
assert not (d["dd"] == pd.Timestamp("2024-03-08")).any()
add("n11", "ru", "no_data", "Сколько сделок прошло 8 марта 2024 года и кто был крупнейшим покупателем в этот день?", None, "",
    "8 марта 2024 (пт, праздник) торгов не было. Приемлемо: 'в этот день сделок нет'.", kind="no_data")
add("n12", "uz", "no_data", f"STIR {p0['ИНН']} bo‘lgan kompaniyaning bank hisob raqami qanday?", None, "",
    "Банковских реквизитов нет ни в одном файле (в contracts.Адрес склада есть только адрес склада, не юр.адрес/счёт).",
    kind="no_data")

# ---------- write ----------
with open(OUT, "w", encoding="utf-8") as f:
    for q in Q:
        f.write(json.dumps(q, ensure_ascii=False, default=lambda o: o.item() if hasattr(o, "item") else str(o)) + "\n")

ids = [q["id"] for q in Q]
assert len(ids) == len(set(ids))
df = pd.DataFrame(Q)
print(f"wrote {len(Q)} questions -> {OUT}")
print(df.groupby(["lang"]).size().to_dict(), df.groupby("kind").size().to_dict())
print(df.groupby("category").size().to_dict())
if "-v" in sys.argv:
    for q in Q:
        print(q["id"], q["lang"], q["question"][:70], "=>", q["expected"]["value"])
