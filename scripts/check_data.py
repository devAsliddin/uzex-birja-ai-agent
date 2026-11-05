"""Integrity check for the CSV dataset in data/.

Checks: headers equal the importer's *_COLUMNS lists (read from
backend/app/services/import_service.py via AST, so it never drifts),
row counts vs the TZ, unique keys, every FK resolves, dates/times/numbers
parse with the importer's rules, and deal lifecycle consistency.

    python scripts/check_data.py            # expects full-size counts
    python scripts/check_data.py --no-counts  # for --scale runs
"""

from __future__ import annotations

import argparse
import ast
import csv
import re
import sys
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMPORTER = ROOT / "backend" / "app" / "services" / "import_service.py"

EXPECTED = {
    "brokers.csv": 120, "participants.csv": 14_392, "usd_rates.csv": 1_765, "contracts.csv": 6_616,
    "deals_2022.csv": 84_299, "deals_2023.csv": 93_985, "deals_2024.csv": 106_647,
    "deals_2025.csv": 115_763, "deals_2026.csv": 99_306,
}
FILE_TO_COLS = {
    "brokers.csv": "BROKERS_COLUMNS", "participants.csv": "PARTICIPANTS_COLUMNS",
    "usd_rates.csv": "USD_RATES_COLUMNS", "contracts.csv": "CONTRACTS_COLUMNS",
}
CUTOFF = date(2026, 10, 30)
MONEY_RE = re.compile(r"^-?\d{1,3}( \d{3})*\.\d{2}$")

errors: list[str] = []


def err(msg: str) -> None:
    if len(errors) < 200:
        errors.append(msg)
    elif len(errors) == 200:
        errors.append("... (truncated)")


def importer_columns() -> dict[str, list[str]]:
    tree = ast.parse(IMPORTER.read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name.endswith("_COLUMNS") or name.endswith("_REQUIRED"):
                out[name] = ast.literal_eval(node.value)
    return out


def pdate(v: str) -> date | None:
    v = v.strip()
    if not v:
        return None
    return datetime.strptime(v, "%d.%m.%Y").date()


def pnum(v: str) -> Decimal | None:
    v = v.strip().replace(" ", "").replace(" ", "")
    if not v:
        return None
    return Decimal(v)


def read(path: Path):
    with open(path, encoding="utf-8", newline="") as f:
        r = csv.reader(f)
        header = next(r)
        return header, list(r)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    ap.add_argument("--no-counts", action="store_true", help="skip TZ row-count comparison")
    args = ap.parse_args()
    d = args.data
    cols = importer_columns()
    file_cols = dict(FILE_TO_COLS)
    tables: dict[str, list[dict[str, str]]] = {}
    deal_files = sorted(d.glob("deals_*.csv"))

    for name in list(FILE_TO_COLS) + [p.name for p in deal_files]:
        p = d / name
        if not p.exists():
            err(f"missing file {name}")
            continue
        header, rows = read(p)
        want = cols[file_cols.get(name, "DEALS_COLUMNS")]
        if header != want:
            err(f"{name}: header mismatch\n  got  {header}\n  want {want}")
        bad_len = sum(1 for r in rows if len(r) != len(header))
        if bad_len:
            err(f"{name}: {bad_len} rows with wrong field count")
        tables[name] = [dict(zip(header, r)) for r in rows]
        if not args.no_counts and name in EXPECTED and len(rows) != EXPECTED[name]:
            err(f"{name}: {len(rows)} rows, TZ says {EXPECTED[name]}")
        print(f"  {name:<18} {len(rows):>8} rows")

    brokers = {r["Код брокера"]: r for r in tables.get("brokers.csv", [])}
    parts = {r["ИНН"]: r for r in tables.get("participants.csv", [])}
    contracts = {r["Номер контракта"]: r for r in tables.get("contracts.csv", [])}
    rates = {}
    for r in tables.get("usd_rates.csv", []):
        rates[pdate(r["Дата"])] = pnum(r["Курс"])

    # uniqueness
    for name, key in (("brokers.csv", "Код брокера"), ("participants.csv", "ИНН"),
                      ("contracts.csv", "Номер контракта"), ("usd_rates.csv", "Дата")):
        vals = [r[key] for r in tables.get(name, [])]
        if len(vals) != len(set(vals)):
            err(f"{name}: duplicate {key}")
    all_inns = list(parts) + [b["ИНН"] for b in brokers.values()]
    if len(all_inns) != len(set(all_inns)):
        err("broker INN collides with participant INN")
    for inn in all_inns:
        if not re.fullmatch(r"\d{9}", inn):
            err(f"bad INN {inn!r}")
    for code in brokers:
        if not re.fullmatch(r"BK\d{3}", code):
            err(f"bad broker code {code}")
    for p in parts.values():
        if p["Роль"] not in ("Продавец", "Покупатель"):
            err(f"participant role {p['Роль']!r}")

    # usd rates: every calendar day, no gaps
    if rates:
        ds = sorted(rates)
        if (ds[-1] - ds[0]).days + 1 != len(ds):
            err("usd_rates has gaps")
        print(f"  usd_rates: {ds[0]} .. {ds[-1]}, {min(rates.values())} .. {max(rates.values())}")

    # contracts
    cur = Counter()
    for c in contracts.values():
        if c["ИНН продавца"] not in parts:
            err(f"contract {c['Номер контракта']}: seller INN not in participants")
        elif parts[c["ИНН продавца"]]["Роль"] != "Продавец":
            err(f"contract {c['Номер контракта']}: seller is not a Продавец")
        reg, valid = pdate(c["Дата регистрации"]), pdate(c["Действует до"])
        if not reg or not valid or valid <= reg:
            err(f"contract {c['Номер контракта']}: bad validity")
        if c["Валюта"] not in ("Узбекский сум", "Доллар США"):
            err(f"contract currency {c['Валюта']!r}")
        if not MONEY_RE.match(c["Базисная цена"]):
            err(f"contract base price format {c['Базисная цена']!r}")
        if c["Тип контракта"] not in ("Внутренний", "Экспортный"):
            err(f"contract type {c['Тип контракта']!r}")
        if c["Форма контракта"] not in ("Спот", "Форвард", "Фьючерс"):
            err(f"contract form {c['Форма контракта']!r}")
        int(c["Срок оплаты"]), int(c["Срок поставки"]), int(c["Лот"].replace(" ", ""))
        cur[c["Валюта"]] += 1
    if contracts:
        print(f"  contracts currency: {dict(cur)} (USD {cur['Доллар США'] / len(contracts):.1%})")

    # deals
    seen_no: set[str] = set()
    status = Counter()
    used_contracts: set[str] = set()
    year_amount: dict[str, Decimal] = {}
    total = 0
    for p in deal_files:
        year = p.stem.split("_")[1]
        amt = Decimal(0)
        for r in tables.get(p.name, []):
            total += 1
            no = r["Номер сделки"]
            if no in seen_no:
                err(f"duplicate deal {no}")
            seen_no.add(no)
            if int(no) >= 2**31:
                err(f"deal {no} overflows INTEGER")
            dd = pdate(r["Дата сделки"])
            if dd is None or str(dd.year) != year or dd > CUTOFF:
                err(f"deal {no}: date {r['Дата сделки']} not in {year}/cutoff")
            datetime.strptime(r["Время сделки"], "%H:%M:%S")
            c = contracts.get(r["Номер контракта"])
            if c is None:
                err(f"deal {no}: contract not found")
                continue
            used_contracts.add(r["Номер контракта"])
            if not (pdate(c["Дата регистрации"]) <= dd <= pdate(c["Действует до"])):
                err(f"deal {no}: outside contract validity")
            if r["ИНН продавца"] != c["ИНН продавца"]:
                err(f"deal {no}: seller differs from contract seller")
            if r["ИНН покупателя"] not in parts:
                err(f"deal {no}: buyer not found")
            if r["ИНН продавца"] == r["ИНН покупателя"]:
                err(f"deal {no}: seller == buyer")
            for k in ("Брокер продавца", "Брокер покупателя"):
                if r[k] not in brokers:
                    err(f"deal {no}: {k} {r[k]} not found")
            if c["Валюта"] == "Доллар США" and dd not in rates:
                err(f"deal {no}: no USD rate for {dd}")
            for k in ("Сумма сделки", "Стартовая цена"):
                if not MONEY_RE.match(r[k]):
                    err(f"deal {no}: {k} format {r[k]!r}")
            try:
                qty, lot = int(r["Количество"]), int(r["Лот"].replace(" ", ""))
                amount, start = pnum(r["Сумма сделки"]), pnum(r["Стартовая цена"])
            except (ValueError, InvalidOperation):
                err(f"deal {no}: numeric parse error")
                continue
            ratio = amount / (qty * lot * start)
            if not (Decimal("0.9") <= ratio <= Decimal("1.4")):
                err(f"deal {no}: amount/start ratio {ratio:.3f}")
            amt += amount if c["Валюта"] != "Доллар США" else amount * rates[dd]
            st = r["Состояние сделки"]
            status[st] += 1
            pay, dlv, got = pdate(r["Дата оплаты"]), pdate(r["Дата поставки"]), r["Поставлено"]
            if st == "Исполнен":
                if not (pay and dlv and got) or not (dd <= pay <= dlv <= CUTOFF) or int(got) != qty:
                    err(f"deal {no}: Исполнен but lifecycle fields inconsistent")
            elif st == "Ждёт поставку":
                if not pay or dlv or got or pay > CUTOFF:
                    err(f"deal {no}: Ждёт поставку inconsistent")
            elif st in ("Ждёт оплату", "Аннулирован", "Новый"):
                if pay or dlv or got:
                    err(f"deal {no}: {st} must have empty payment/delivery")
            else:
                err(f"deal {no}: unknown status {st!r}")
        year_amount[year] = amt
    print(f"  deals total: {total}, contracts used: {len(used_contracts)}/{len(contracts)}")
    print("  statuses: " + ", ".join(f"{k} {v} ({v / max(1, total):.1%})" for k, v in status.most_common()))
    print("  turnover (bn UZS): " + ", ".join(f"{y}: {a / 10**9:,.0f}" for y, a in year_amount.items()))

    if errors:
        print(f"\nFAIL: {len(errors)} problem(s)")
        for e in errors:
            print("  - " + e)
        return 1
    print("\nOK: all integrity checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
