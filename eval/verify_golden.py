"""Second, independent computation (stdlib csv only, no pandas) for a sample of golden.jsonl answers."""
import csv
import glob
import json
import os
from collections import Counter, defaultdict
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "..", "data")
ANN = "Аннулирован(Не оплачен)"


def rows(name):
    with open(os.path.join(D, name), encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f)


def n(s):
    return float(s.replace(" ", "").replace(" ", ""))


def pdate(s):
    dd, mm, yy = s.split(".")
    return date(int(yy), int(mm), int(dd))


con = {r["Номер контракта"]: r for r in rows("contracts.csv")}
rate = {r["Дата"]: n(r["Курс"]) for r in rows("usd_rates.csv")}
deals = []
for f in sorted(glob.glob(os.path.join(D, "deals_*.csv"))):
    with open(f, encoding="utf-8", newline="") as fh:
        deals.extend(csv.DictReader(fh))

gold = {}
with open(os.path.join(HERE, "golden.jsonl"), encoding="utf-8") as f:
    for line in f:
        q = json.loads(line)
        gold[q["id"]] = q["expected"]["value"]


def uzs(r):
    a = n(r["Сумма сделки"])
    return a * rate[r["Дата сделки"]] if con[r["Номер контракта"]]["Валюта"] == "Доллар США" else a


calc = {}
yr = lambda r: r["Дата сделки"][-4:]  # noqa: E731
calc["c01"] = sum(1 for r in deals if yr(r) == "2023")
calc["c02"] = sum(1 for r in deals if yr(r) == "2025" and r["Состояние сделки"] != ANN)
calc["c05"] = sum(1 for r in deals if yr(r) == "2022" and r["Состояние сделки"] == ANN)
calc["c09"] = sum(1 for r in deals if yr(r) == "2025" and con[r["Номер контракта"]]["Регион"] == "Наманганская область")
calc["s01"] = sum(uzs(r) for r in deals if yr(r) == "2024" and r["Состояние сделки"] != ANN)
calc["s03"] = sum(n(r["Сумма сделки"]) for r in deals if yr(r) == "2023" and r["Состояние сделки"] != ANN
                  and r["Тип контракта"] == "Экспортный")
acc = defaultdict(float)
for r in deals:
    if yr(r) == "2024" and r["Состояние сделки"] != ANN:
        acc[r["Брокер продавца"]] += uzs(r)
calc["t01"] = max(acc, key=acc.get)
gold["t01"] = gold["t01"][0]
c = Counter(r["Регион"] for r in deals if yr(r) == "2026")
calc["t06"] = c.most_common(1)[0][0]
late = 0
for r in deals:
    if r["Дата поставки"]:
        if (pdate(r["Дата поставки"]) - pdate(r["Дата оплаты"])).days > int(con[r["Номер контракта"]]["Срок поставки"]):
            late += 1
calc["tm01"] = late
ds = [(pdate(r["Дата оплаты"]) - pdate(r["Дата сделки"])).days for r in deals if yr(r) == "2024" and r["Дата оплаты"]]
calc["tm03"] = sum(ds) / len(ds)
calc["tm05"] = sum(1 for r in deals if r["Состояние сделки"] == "Ждёт оплату")
cu = [r for r in deals if any(k in r["Наименование товара"].lower() for k in ("катод", "медн"))]
calc["x01"] = len(cu)
calc["x02"] = sum(n(r["Количество"]) * n(r["Лот"]) for r in cu if yr(r) == "2024" and r["Состояние сделки"] != ANN)
s = [r for r in deals if r["Наименование товара"] == "Сахар белый" and r["Дата сделки"][3:] == "05.2025"
     and r["Состояние сделки"] != ANN]
calc["a03"] = sum(n(r["Сумма сделки"]) for r in s) / sum(n(r["Количество"]) * n(r["Лот"]) for r in s)
calc["x04"] = sum(1 for r in deals if yr(r) == "2024" and r["Брокер продавца"] == r["Брокер покупателя"])
calc["n07"] = sum(1 for r in deals if pdate(r["Дата сделки"]).weekday() >= 5)  # expect 0 -> trap valid
gold["n07"] = 0
calc["n01"] = sum(1 for r in deals if yr(r) == "2021")
gold["n01"] = 0

fails = 0
for k, v in calc.items():
    g = gold[k]
    okk = abs(v - g) <= 1e-6 * max(1, abs(g)) if isinstance(v, (int, float)) else v == g
    fails += not okk
    print(f"{'OK  ' if okk else 'FAIL'} {k}: golden={g} independent={v}")
print(f"\n{len(calc) - fails}/{len(calc)} matched")
