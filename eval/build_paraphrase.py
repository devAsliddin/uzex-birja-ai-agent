"""Build eval/paraphrase.jsonl — independent paraphrase eval set. Every value computed from data/*.csv."""
import json, os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load, num, dt
import pandas as pd

d, c, p, b, u = load()
CAN = "Аннулирован(Не оплачен)"
d["amt"] = num(d["Сумма сделки"])
d["qty"] = num(d["Количество"])
d["lot"] = num(d["Лот"])
d["vol"] = d["qty"] * d["lot"]
d["dd"] = dt(d["Дата сделки"])
d["y"] = d["dd"].dt.year
d["m"] = d["dd"].dt.month
cur = c.set_index("Номер контракта")["Валюта"]
d["cur"] = d["Номер контракта"].map(cur)
u["dd"] = dt(u["Дата"]); u["rate"] = num(u["Курс"])
rate = u.set_index("dd")["rate"]
d["rate"] = d["dd"].map(rate)
d["usd"] = d["cur"] == "Доллар США"
d["uzs"] = d["amt"].where(~d["usd"], d["amt"] * d["rate"])
d["ok"] = d["Состояние сделки"] != CAN
assert d["cur"].notna().all() and d.loc[d.usd, "rate"].notna().all()
lname = d["Наименование товара"].str.lower()
pname = p.set_index("ИНН")["Наименование"]
bname = b.set_index("Код брокера")["Наименование"]
cat = c.set_index("Номер контракта")["Категория товара"]
d["cat"] = d["Номер контракта"].map(cat)

Q = []
def add(lang, cat_, q, val, unit, notes, tol=0.0, kind="exact"):
    if isinstance(val, float):
        val = round(val, 4)
    Q.append(dict(id=f"p{len(Q)+1:02d}", lang=lang, category=cat_, question=q,
                  expected=dict(value=val, unit=unit, notes=notes), kind=kind, tolerance=tol))

def prod(regex):
    m = lname.str.contains(regex, regex=True)
    return m

def names(m):
    return sorted(d.loc[m, "Наименование товара"].unique().tolist())

def top(series, k=1):
    s = series.sort_values(ascending=False)
    return s

Y = lambda y: d["y"] == y
OK = d["ok"]

# ---------------- counts ----------------
m = Y(2025) & d["m"].between(4, 6)
add("ru", "count", "Какое количество сделок пришлось на II квартал 2025 г.?", int(m.sum()), "сделок",
    "Дата сделки 01.04.2025–30.06.2025, все статусы.")
m = Y(2023) & (d["m"] == 11)
add("uz", "count", "2023 yil noyabr oyida qancha bitim bolgan", int(m.sum()), "bitim",
    "Lowercase, без пунктуации. Дата сделки в 11.2023, все статусы.")
m = Y(2024) & (d["Регион"] == "Namangan viloyati")
add("ru", "count", "скок сделок было по наманганской области за 24 год", int(m.sum()), "сделок",
    "Сленг/сокращение. Регион = 'Namangan viloyati', 2024, все статусы.")
m = Y(2026) & (d["Состояние сделки"] == "Исполнен(Частично)")
add("uz", "count", "2026-yilda nechta bitim faqat qisman bajarilgan (tovar to‘liq yetkazilmagan)?", int(m.sum()), "bitim",
    "Состояние = 'Исполнен(Частично)', 2026.")
m = Y(2023) & (d["Тип контракта"] == "Экспортный")
add("ru", "count", "Сколько было экспортных контрактных сделок за 2023-й?", int(m.sum()), "сделок",
    "Тип контракта = 'Экспортный', 2023, все статусы.")
m = Y(2024) & (d["Форма контракта"] == "Форвард")
add("uz", "count", "Forvard shaklidagi bitimlar soni 2024-yil uchun qancha?", int(m.sum()), "bitim",
    "Форма контракта = 'Форвард', 2024, все статусы.")
m = d["Тип торгов"] == "Обратный аукцион"
add("ru", "count", "Сколько всего сделок заключено на обратном аукционе за весь период?", int(m.sum()), "сделок",
    "Тип торгов = 'Обратный аукцион', 2022–2026, все статусы.")
ms = prod("сахар")
m = Y(2024) & ms
add("uz", "count", "2024 йилда шакар бўйича нечта битим тузилган?", int(m.sum()), "битим",
    f"Uzbek Cyrillic. Наименование содержит 'сахар' (без учёта регистра): {names(ms)}. 2024, все статусы.")
m = d["Состояние сделки"] == "Ждёт оплату"
add("ru", "count", "Сколько сделок сейчас висит в статусе «ждёт оплату»?", int(m.sum()), "сделок",
    "Состояние = 'Ждёт оплату' (на 30.10.2026), все годы.")
m = Y(2022) & (d["m"] == 12)
add("ru", "count", "skolko sdelok bylo v dekabre 2022", int(m.sum()), "сделок",
    "Транслит, без пунктуации. 12.2022, все статусы.")
m = Y(2025) & (d["Регион"] == "Toshkent shahri") & (d["Форма контракта"] == "Спот")
add("uz", "count", "2025 yilda Toshkent shahrida спот сделки soni qancha", int(m.sum()), "bitim",
    "Смешанный RU/UZ. Регион='Toshkent shahri', Форма='Спот', 2025, все статусы.")
m = Y(2026) & (d["Форма контракта"] == "Фьючерс")
add("uz", "count", "2026 da fyuchrs bitimlar nechta", int(m.sum()), "bitim",
    "Опечатка 'fyuchrs'. Форма контракта='Фьючерс', 2026, все статусы.")

# ---------------- sums ----------------
m = Y(2023) & OK
add("uz", "sum", "2023-yilning umumiy savdo aylanmasi so‘mda qancha bo‘ldi? (bekor qilinganlar hisobga olinmasin)", float(d.loc[m, "uzs"].sum()), "so‘m",
    "Σ amt_uzs, 2023, без аннулированных; USD-контракты × курс на дату сделки.", 0.001)
m = Y(2025) & OK & d["usd"]
add("ru", "sum", "На какую сумму в долларах заключили долларовые (экспортные) сделки в 2025 году, без аннулированных?", float(d.loc[m, "amt"].sum()), "USD",
    f"Σ Сумма сделки (в USD) по контрактам с Валюта='Доллар США', 2025, без аннулированных; {int(m.sum())} сделок.", 0.001)
m = Y(2026) & OK & (d["Регион"] == "Samarqand viloyati")
add("uz", "sum", "samarqand viloyati 2026 yil aylanmasi necha so'm", float(d.loc[m, "uzs"].sum()), "so‘m",
    "Регион='Samarqand viloyati', 2026, без аннулированных, USD×курс.", 0.001)
mc = prod("цемент")
m = Y(2024) & OK & mc
add("ru", "sum", "Оборот по цементу в 2024 году в сумах (неоплаченные аннулированные не считать)?", float(d.loc[m, "uzs"].sum()), "сум",
    f"Наименование содержит 'цемент' (без учёта регистра; включает портландцемент): {len(names(mc))} вариантов, напр. {names(mc)[:4]}. 2024, без аннулированных.", 0.001)
m = Y(2025) & OK & (d["Брокер продавца"] == "BK017")
add("uz", "sum", "BK017 broker sotuvchi tomonida 2025-yilda jami qancha so‘mlik bitim tuzgan?", float(d.loc[m, "uzs"].sum()), "so‘m",
    f"Брокер продавца='BK017' ({bname['BK017']}), 2025, без аннулированных, USD×курс.", 0.001)
# a big buyer in 2024
g = d[Y(2024) & OK].groupby("ИНН покупателя")["uzs"].sum().sort_values(ascending=False)
inn_b = g.index[5]
add("ru", "sum", f"Сколько сумов потратила компания с ИНН {inn_b} на покупки на бирже в 2024 году?", float(g.iloc[5]), "сум",
    f"ИНН покупателя={inn_b} ({pname[inn_b]}), 2024, без аннулированных, USD×курс.", 0.001)

# ---------------- top ----------------
g = d[Y(2023)].groupby("Брокер продавца").size().sort_values(ascending=False)
add("ru", "top", "Какая брокерская контора чаще всех выступала на стороне продавца в 2023 году?", [g.index[0], bname[g.index[0]]], "код, наименование",
    f"count by Брокер продавца, 2023, все статусы. {g.index[0]}={g.iloc[0]}; 2-е {g.index[1]}={g.iloc[1]}.")
g = d[Y(2026) & OK].groupby("Брокер покупателя")["uzs"].sum().sort_values(ascending=False)
add("uz", "top", "2026-yilda xaridor brokerlari ichida aylanma bo‘yicha birinchi o‘rinda kim?", [g.index[0], bname[g.index[0]]], "kod, nomi",
    f"sum amt_uzs by Брокер покупателя, 2026, без аннулированных. {g.iloc[0]:.2f}; 2-е {g.index[1]}={g.iloc[1]:.2f}.")
x = d[Y(2022) & OK]
both = pd.concat([x[["Брокер продавца", "uzs"]].rename(columns={"Брокер продавца": "br"}),
                  x.loc[x["Брокер продавца"] != x["Брокер покупателя"], ["Брокер покупателя", "uzs"]].rename(columns={"Брокер покупателя": "br"})])
g = both.groupby("br")["uzs"].sum().sort_values(ascending=False)
add("ru", "top", "Какой брокер в 2022 году прокрутил наибольший оборот, если считать обе стороны сделки (продавец + покупатель)?", [g.index[0], bname[g.index[0]]], "код, наименование",
    f"Σ amt_uzs сделок, где брокер на любой стороне (сделка с одним брокером на обеих сторонах считается один раз), 2022, без аннулированных. {g.iloc[0]:.2f}; 2-е {g.index[1]}={g.iloc[1]:.2f}.")
g = d[Y(2024) & OK].groupby("Регион")["uzs"].sum().sort_values(ascending=False)
add("uz", "top", "2024-yilda qaysi hududda savdo aylanmasi eng katta bo‘lgan?", g.index[0], "hudud",
    f"sum amt_uzs by Регион (склад продавца), 2024, без аннулированных. {g.iloc[0]:.2f}; 2-е {g.index[1]}={g.iloc[1]:.2f}.")
g = d[Y(2026) & OK].groupby("cat")["uzs"].sum().sort_values(ascending=False)
add("ru", "top", "Какая категория товаров дала больше всего оборота в 2026 году?", g.index[0], "категория",
    f"contracts.Категория товара, sum amt_uzs, 2026, без аннулированных. {g.iloc[0]:.2f}; 2-е {g.index[1]}={g.iloc[1]:.2f}.")
g = d[Y(2025) & OK].groupby("Наименование товара")["uzs"].sum().sort_values(ascending=False)
add("uz", "top", "2025-yilda aylanma bo‘yicha eng yirik 3 ta tovar nomini ayting (reyestrdagi yozilishi bo‘yicha).", g.index[:3].tolist(), "tovar nomi",
    f"sum amt_uzs by Наименование товара (как есть), 2025, без аннулированных. Значения: {[round(v,2) for v in g.iloc[:4]]}; 4-е {g.index[3]}.")
g = d[Y(2023)].groupby("ИНН продавца").size().sort_values(ascending=False)
add("ru", "top", "У какого продавца было больше всего сделок в 2023 году?", [g.index[0], pname[g.index[0]]], "ИНН, наименование",
    f"count by ИНН продавца, 2023, все статусы. {g.iloc[0]}; 2-е {g.index[1]}={g.iloc[1]}.")
g = d[Y(2026)].groupby("ИНН покупателя").size().sort_values(ascending=False)
add("uz", "top", "2026 йилда энг кўп битим тузган харидор ким?", [g.index[0], pname[g.index[0]]], "STIR, nomi",
    f"Uzbek Cyrillic. count by ИНН покупателя, 2026, все статусы. {g.iloc[0]}; 2-е {g.index[1]}={g.iloc[1]}.")
g = d[Y(2025)].groupby("Регион").size().sort_values(ascending=False)
add("ru", "top", "Топ-3 региона по числу сделок за 2025 год?", g.index[:3].tolist(), "регионы",
    f"count by Регион, 2025, все статусы. {g.iloc[:4].to_dict()}.")

# ---------------- lookups ----------------
rng = random.Random(20261105)
def pick(mask):
    idx = d.index[mask].tolist()
    return d.loc[rng.choice(idx)]
r = pick(Y(2024) & OK)
add("ru", "lookup", f"кто покупатель по сделке {r['Номер сделки']}", [r["ИНН покупателя"], pname[r["ИНН покупателя"]]], "ИНН, наименование",
    "Lowercase, без '?'. deals.ИНН покупателя → participants.Наименование.")
r = pick(Y(2023))
add("uz", "lookup", f"{r['Номер сделки']}-sonli bitimda sotuvchi kim edi?", [r["ИНН продавца"], pname[r["ИНН продавца"]]], "STIR, nomi",
    "deals.ИНН продавца → participants.")
r = pick(Y(2025) & (d["Брокер продавца"] != d["Брокер покупателя"]))
add("ru", "lookup", f"Какие брокеры участвовали в сделке №{r['Номер сделки']} — со стороны продавца и покупателя?",
    [r["Брокер продавца"], bname[r["Брокер продавца"]], r["Брокер покупателя"], bname[r["Брокер покупателя"]]], "код/имя продавца, код/имя покупателя",
    "deals.Брокер продавца, Брокер покупателя → brokers.Наименование.")
r = pick(d["Состояние сделки"] == "Оплачен")
add("uz", "lookup", f"{r['Номер сделки']} raqamli bitimning holati qanday?", r["Состояние сделки"], "holat",
    "deals.Состояние сделки (Оплачен = to‘langan, hali yetkazilmagan).")
r = pick(Y(2022) & (d["Дата поставки"] != ""))
add("ru", "lookup", f"Когда была оплачена и когда поставлена сделка {r['Номер сделки']}?", [r["Дата оплаты"], r["Дата поставки"]], "дата оплаты, дата поставки",
    f"deals.Дата оплаты, Дата поставки. Дата сделки {r['Дата сделки']}.")
r = pick(d["usd"] & OK)
add("uz", "lookup", f"{r['Номер сделки']}-bitim summasi dollarda qancha?", float(r["amt"]), "USD",
    f"Контракт {r['Номер контракта']} в USD; Сумма сделки = {r['Сумма сделки']}. В сумах = {r['uzs']:.2f} (курс {r['rate']}).", 0.0001)
cr = c.iloc[rng.randrange(len(c))]
add("ru", "lookup", f"Какая базисная цена указана в контракте {cr['Номер контракта']}?", float(cr["Базисная цена"]), cr["Валюта"] + " за " + cr["Единица измерения"],
    f"contracts.Базисная цена; товар {cr['Наименование продукта']}.", 0.0001)
cr = c.iloc[rng.randrange(len(c))]
add("uz", "lookup", f"{cr['Номер контракта']} shartnoma bo‘yicha sotuvchi qaysi kompaniya", [cr["ИНН продавца"], pname[cr["ИНН продавца"]]], "STIR, nomi",
    "contracts.ИНН продавца → participants.")
cr = c.iloc[rng.randrange(len(c))]
add("ru", "lookup", f"Что за товар по контракту {cr['Номер контракта']}?", cr["Наименование продукта"], "товар",
    f"contracts.Наименование продукта (+ атрибуты: Марка='{cr['Марка товара']}', Сорт='{cr['Сорт товара']}', Класс='{cr['Класс товара']}'); единица {cr['Единица измерения']}.")
br = b.iloc[rng.randrange(len(b))]
add("uz", "lookup", f"{br['Код брокера']} kodi qaysi brokerga tegishli va u qayerda joylashgan?", [br["Наименование"], br["Регион"]], "nomi, hudud",
    f"brokers.csv; ИНН брокера {br['ИНН']}.")
pr = p.iloc[rng.randrange(len(p))]
add("ru", "lookup", f"Как называется организация с ИНН {pr['ИНН']}?", pr["Наименование"], "наименование",
    f"participants.csv; регион {pr['Регион']}, роль {pr['Роль']}.")
pr = p[p["Плательщик НДС"] == "Нет"].iloc[rng.randrange(int((p["Плательщик НДС"] == "Нет").sum()))]
add("uz", "lookup", f"STIR {pr['ИНН']} bo‘lgan kompaniya QQS to‘lovchisimi?", pr["Плательщик НДС"], "Да/Нет",
    f"participants.Плательщик НДС = '{pr['Плательщик НДС']}' (QQS to‘lovchisi emas); {pr['Наименование']}.")

# ---------------- rates ----------------
add("ru", "rate", "Какой был курс доллара 17.08.2023?", float(rate[pd.Timestamp("2023-08-17")]), "сум за 1 USD",
    "usd_rates.csv, Дата=17.08.2023.", 0.0001)
mm = (u["dd"].dt.year == 2025) & (u["dd"].dt.month == 3)
add("uz", "rate", "2025 йил март ойида долларнинг ўртача курси қанча бўлган?", float(u.loc[mm, "rate"].mean()), "so‘m",
    f"Uzbek Cyrillic. Среднее по всем {int(mm.sum())} календарным дням 03.2025 из usd_rates.csv.", 0.001)

# ---------------- reference counts ----------------
add("ru", "ref_count", "Сколько брокерских контор зарегистрировано в Ташкенте (городе)?", int((b["Регион"] == "Toshkent shahri").sum()), "брокеров",
    "brokers.Регион = 'Toshkent shahri'.")
mm = (p["Роль"] == "Продавец") & (p["Регион"] == "Samarqand viloyati")
add("uz", "ref_count", "Samarqand viloyatida nechta sotuvchi kompaniya ro‘yxatda bor?", int(mm.sum()), "kompaniya",
    "participants: Роль='Продавец', Регион='Samarqand viloyati'.")
add("ru", "ref_count", "Сколько участников не являются плательщиками НДС?", int((p["Плательщик НДС"] == "Нет").sum()), "компаний",
    "participants.Плательщик НДС = 'Нет'.")

# ---------------- shares / stats ----------------
x = d[Y(2024)]
add("uz", "share", "2024-yilda bitimlarning necha foizi to‘lanmagani uchun bekor qilingan?", float((x["Состояние сделки"] == CAN).mean() * 100), "%",
    f"{int((x['Состояние сделки']==CAN).sum())} / {len(x)} × 100, 2024.", 0.001)
x = d[Y(2025)]
add("ru", "share", "Какую долю (в %) от всех сделок 2025 года составили экспортные?", float((x["Тип контракта"] == "Экспортный").mean() * 100), "%",
    f"count Экспортный / count all, 2025, все статусы: {int((x['Тип контракта']=='Экспортный').sum())}/{len(x)}.", 0.001)
x = d[Y(2022) & OK]
add("uz", "share", "2022 йилда экспорт битимлари умумий айланманинг неча фоизини ташкил қилган?", float(x.loc[x["Тип контракта"] == "Экспортный", "uzs"].sum() / x["uzs"].sum() * 100), "%",
    "Uzbek Cyrillic. Σ amt_uzs Экспортный / Σ amt_uzs всех, 2022, без аннулированных.", 0.001)
x = d[Y(2023) & OK]
add("uz", "stat", "2023-yilda o‘rtacha bitim summasi necha so‘m bo‘lgan (bekor qilinganlarsiz)?", float(x["uzs"].mean()), "so‘m",
    f"mean amt_uzs, 2023, без аннулированных, n={len(x)}.", 0.001)
x = d[Y(2026) & OK]
i = x["uzs"].idxmax()
add("ru", "stat", "Какова сумма самой крупной сделки 2026 года в сумах?", float(x.loc[i, "uzs"]), "сум",
    f"max amt_uzs, 2026, без аннулированных: сделка {x.loc[i,'Номер сделки']} ({x.loc[i,'Наименование товара']}, валюта {x.loc[i,'cur']}).", 0.001)
x = d[Y(2022) & OK]
i = x["uzs"].idxmin()
add("uz", "stat", "2022 yildagi eng kichik bitim summasi qancha edi", float(x.loc[i, "uzs"]), "so‘m",
    f"min amt_uzs, 2022, без аннулированных: сделка {x.loc[i,'Номер сделки']} ({x.loc[i,'Наименование товара']}).", 0.001)

# ---------------- volume / price ----------------
mw = prod("пшениц")
m = Y(2025) & OK & mw & (d["Единица измерения"] == "тонна")
add("ru", "volume", "Сколько тонн пшеницы продали в 2025 году?", float(d.loc[m, "vol"].sum()), "тонн",
    f"Σ Количество×Лот, наименование содержит 'пшениц' (все {len(names(mw))} вариантов, все в тоннах), 2025, без аннулированных.", 0.001)
mk = prod("катод")
m = Y(2025) & OK & mk
add("uz", "volume", "2025 da medniy katod necha tonna sotilgan", float(d.loc[m, "vol"].sum()), "tonna",
    f"Смешанный RU/UZ. Наименование содержит 'катод': {names(mk)}; 2025, без аннулированных.", 0.001)
m = Y(2024) & OK & ms
add("ru", "price", "Какая средневзвешенная цена тонны сахара в 2024 году (в сумах)?", float(d.loc[m, "uzs"].sum() / d.loc[m, "vol"].sum()), "сум/тонна",
    f"Σ amt_uzs / Σ(Количество×Лот), сахар: {names(ms)} (все в тоннах), 2024, без аннулированных.", 0.001)
mb = prod("аи-92")
m = Y(2024) & OK & mb & (d["Единица измерения"] == "литр")
add("uz", "volume", "2024 йилда АИ-92 бензини неча литр сотилган (литрда ўлчанган битимлар, бекор қилинганларсиз)?", float(d.loc[m, "vol"].sum()), "litr",
    f"Uzbek Cyrillic. Наименование содержит 'аи-92', Единица='литр': {sorted(d.loc[mb & (d['Единица измерения']=='литр'),'Наименование товара'].unique())}; 2024, без аннулированных.", 0.001)
m = Y(2026) & OK & mb & (d["Единица измерения"] == "тонна")
add("ru", "volume", "Сколько тонн бензина АИ-92 продано в 2026 году (только сделки в тоннах)?", float(d.loc[m, "vol"].sum()), "тонн",
    f"Наименование содержит 'аи-92', Единица='тонна': {sorted(d.loc[mb & (d['Единица измерения']=='тонна'),'Наименование товара'].unique())}; 2026, без аннулированных. Литровые сделки не суммируются с тоннами.", 0.001)
mp = lname.str.contains(r"хлопок[- ]сырец", regex=True)
m = Y(2024) & OK & mp
add("uz", "volume", "2024-yilda paxta xomashyosi (xlopok-sirets, spot va forvard) jami necha kilogramm sotilgan?", float(d.loc[m, "vol"].sum()), "kg",
    f"Наименование по regex 'хлопок[- ]сырец' без учёта регистра ({len(names(mp))} вариантов, включая (СПОТ) и (ФОРВАРД)), все в кг; 2024, без аннулированных.", 0.001)
m = Y(2024) & OK & mw
add("uz", "price", "2024 yilda bug‘doyning 1 tonnasi o‘rtacha (vaznli) necha so‘mdan sotilgan?", float(d.loc[m, "uzs"].sum() / d.loc[m, "vol"].sum()), "so‘m/tonna",
    "Σ amt_uzs / Σ(Количество×Лот), наименование содержит 'пшениц', 2024, без аннулированных.", 0.001)

# ---------------- delivery / brokers ----------------
srok = c.set_index("Номер контракта")["Срок поставки"].astype(int)
x = d[(d["Дата поставки"] != "") & Y(2025)]
late = (dt(x["Дата поставки"]) - dt(x["Дата оплаты"])).dt.days > x["Номер контракта"].map(srok)
add("ru", "delivery", "Сколько сделок 2025 года поставили с опозданием, т.е. позже срока поставки по контракту?", int(late.sum()), "сделок",
    "Дата поставки − Дата оплаты > contracts.Срок поставки (дней); только сделки с заполненной Датой поставки; год Даты сделки = 2025.")
x = d[Y(2025) & (d["Состояние сделки"] == "Исполнен(Частично)")]
add("uz", "delivery", "2025-yilda qisman bajarilgan bitimlarda jami nechta lot yetkazilmay qolgan?", int((x["qty"] - num(x["Поставлено"])).sum()), "lot",
    f"Σ(Количество − Поставлено) по Состояние='Исполнен(Частично)', 2025 ({len(x)} сделок).")
m = d["Брокер продавца"] == d["Брокер покупателя"]
add("ru", "same_broker", "Во скольких сделках за всю историю один и тот же брокер представлял и продавца, и покупателя?", int(m.sum()), "сделок",
    "Брокер продавца == Брокер покупателя, 2022–2026, все статусы.")

# ---------------- no_data ----------------
missing = 450262
assert missing not in set(d["Номер сделки"].astype(int)) and 100001 < missing < 604956
assert "BK121" not in set(b["Код брокера"]) and "111222333" not in set(p["ИНН"])
assert not lname.str.contains("кофе|coffee|qahva|золот").any()
assert not d["Дата сделки"].isin(["01.01.2022", "02.01.2022"]).any()
assert d["dd"].max() == pd.Timestamp("2026-10-30")
ND = [
 ("ru", "Сколько сделок было заключено в декабре 2026 года?", "Сделки заканчиваются 30.10.2026; декабря 2026 в данных нет."),
 ("uz", "1-2 yanvar 2022 kunlari nechta bitim bo‘lgan?", "Сделки начинаются 03.01.2022; 01–02.01.2022 сделок нет (курс USD при этом есть)."),
 ("ru", "Покажи наименование и регион брокера BK121", "brokers.csv содержит только BK001–BK120."),
 ("uz", f"{missing} raqamli bitim bo‘yicha xaridor kim?", f"Номер {missing} внутри диапазона, но пропущен в deals (README: часть номеров пропущена)."),
 ("ru", "Какая компания с ИНН 111222333 и сколько у неё сделок?", "ИНН 111222333 отсутствует в participants и deals."),
 ("uz", "kofe bo‘yicha birjada qancha savdo bo‘lgan 2024 da", "Нет наименований с 'кофе'/'coffee'/'qahva' в deals и contracts."),
 ("ru", "Кто директор и какой телефон у брокерской конторы BK005?", "brokers.csv: только код, наименование, ИНН, регион — нет ФИО и телефонов."),
 ("uz", "Ertaga dollar kursi qancha bo‘ladi?", "Прогноза нет; usd_rates.csv — исторические значения до 31.10.2026."),
 ("ru", "Почему в 2024 году аннулировали так много сделок?", "Причин аннулирования в данных нет (есть только статус)."),
 ("uz", "Олтин бўйича энг катта битим қайси?", "Uzbek Cyrillic. Нет наименований с 'золот'/'oltin'/'gold'."),
]
for lang, q, notes in ND:
    add(lang, "no_data", q, None, "", notes, 0.0, "no_data")

# trim to 60: drop overlapping items (by draft id), then renumber
DROP = {"p05", "p07", "p27", "p30", "p38", "p04", "p06", "p29", "p50", "p57"}
Q = [q for q in Q if q["id"] not in DROP]
for i, q in enumerate(Q, 1):
    q["id"] = f"p{i:02d}"

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paraphrase.jsonl")
with open(out, "w", encoding="utf-8") as f:
    for q in Q:
        f.write(json.dumps(q, ensure_ascii=False, default=lambda o: o.item() if hasattr(o, "item") else str(o)) + "\n")
from collections import Counter
print(len(Q), Counter(q["lang"] for q in Q), Counter(q["category"] for q in Q))
