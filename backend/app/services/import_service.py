"""CSV import service (TZ section 2: ETL pipeline + cleansing).

Seeding order (referential integrity):
    1. brokers.csv, participants.csv, usd_rates.csv  (independent tables)
    2. contracts.csv                                 (seller INN -> participants.inn)
    3. deals_2022.csv ... deals_2026.csv             (sequential, batched)

Cleansing rules:
    * UTF-8 (BOM tolerated), comma separated, quoted fields parsed by ``csv``.
    * Dates ``DD.MM.YYYY`` -> ISO ``YYYY-MM-DD``.
    * Money/number columns: thousand separators (spaces, NBSP) removed
      (``1 250 000.00`` -> ``1250000.00``).
    * Empty ``Дата оплаты`` / ``Дата поставки`` / ``Поставлено`` -> NULL.
    * USD contracts: the UZS amount is derived at query time from ``usd_rates``
      on the deal date (nearest previous date when the exact day is missing),
      see ``app.services.fx``. Original deal values are never altered.

Import is idempotent: rows whose primary key already exists are skipped, so the
same files can be imported repeatedly. Rows violating NOT NULL / CHECK rules of
the schema are reported as invalid (never invented). Unknown foreign keys on
optional references are set to NULL and counted in ``warnings``.
"""

from __future__ import annotations

import csv
import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.broker import Broker
from app.db.models.contract import Contract
from app.db.models.deal import Deal
from app.db.models.participant import Participant
from app.db.models.usd_rate import UsdRate

log = logging.getLogger("uzex_ai.import")

CURRENCY_UZS = "Узбекский сум"
CURRENCY_USD = "Доллар США"
ROLES = ("Продавец", "Покупатель")
CONTRACT_TYPES = ("Внутренний", "Экспортный")
CONTRACT_FORMS = ("Спот", "Форвард", "Фьючерс")

_SPACES = (" ", " ", " ", " ")


# ---------------------------------------------------------------------------
# Cleansing helpers
# ---------------------------------------------------------------------------
def _strip(value: str | None) -> str | None:
    if value is None:
        return None
    v = str(value).strip()
    return v or None


def _clean_number(value: str | None) -> str | None:
    v = _strip(value)
    if v is None:
        return None
    for ch in _SPACES:
        v = v.replace(ch, "")
    if "," in v and "." not in v:
        v = v.replace(",", ".")
    elif "," in v:
        v = v.replace(",", "")
    return v or None


def parse_decimal(value: str | None, scale: int | None = None) -> float | None:
    """'1 250 000.00' -> 1250000.0 ; empty/invalid -> None."""
    v = _clean_number(value)
    if v is None:
        return None
    try:
        d = Decimal(v)
    except (InvalidOperation, ValueError):
        return None
    if not d.is_finite():
        return None
    if scale is not None:
        d = round(d, scale)
    return float(d)


def parse_int(value: str | None) -> int | None:
    v = _clean_number(value)
    if v is None:
        return None
    try:
        d = Decimal(v)
    except (InvalidOperation, ValueError):
        return None
    if not d.is_finite() or d != d.to_integral_value():
        return None
    return int(d)


def parse_date(value: str | None) -> date | None:
    """DD.MM.YYYY -> date (ISO YYYY-MM-DD also accepted)."""
    v = _strip(value)
    if v is None:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def parse_time(value: str | None) -> time | None:
    v = _strip(value)
    if v is None:
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(v, fmt).time()
        except ValueError:
            continue
    return None


def parse_bool(value: str | None) -> bool | None:
    v = _strip(value)
    if v is None:
        return None
    low = v.lower()
    if low in {"да", "yes", "true", "1", "y", "ha"}:
        return True
    if low in {"нет", "no", "false", "0", "n", "yo'q", "yoq"}:
        return False
    return None


def normalize_currency(value: str | None) -> str | None:
    v = _strip(value)
    if v is None:
        return None
    low = v.lower()
    if low in {"usd", "$"} or "доллар" in low or "dollar" in low:
        return CURRENCY_USD
    if low in {"uzs", "sum", "so'm", "som"} or "сум" in low:
        return CURRENCY_UZS
    return None


def _choice(value: str | None, allowed: tuple[str, ...]) -> str | None:
    v = _strip(value)
    if v is None:
        return None
    for a in allowed:
        if v.lower() == a.lower():
            return a
    return None


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
@dataclass
class ImportRecordResult:
    ok: bool
    row: int
    action: str
    errors: list[str] = field(default_factory=list)


@dataclass
class ImportReport:
    file: str
    table: str
    total_rows: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    invalid: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: dict[str, int] = field(default_factory=dict)
    record_errors: list[ImportRecordResult] = field(default_factory=list)

    @property
    def valid_rows(self) -> int:
        return self.inserted + self.updated + self.skipped

    def summary_line(self) -> str:
        return (
            f"{self.file}: total={self.total_rows} inserted={self.inserted} "
            f"skipped={self.skipped} invalid={self.invalid}"
            + (f" warnings={self.warnings}" if self.warnings else "")
        )


MAX_RECORD_ERRORS = 200


@dataclass
class _Spec:
    file_name: str
    table: str
    model: Any
    pk: str
    required_columns: list[str]
    parse_row: Callable[[dict[str, str], ImportService, Counter], dict[str, Any] | None]
    # attribute names that must be non-null (NOT NULL columns in the TZ DDL)
    not_null: list[str]


# ---------------------------------------------------------------------------
# Row parsers
# ---------------------------------------------------------------------------
def _p_broker(row: dict[str, str], svc: ImportService, w: Counter) -> dict[str, Any] | None:
    return {
        "code": _strip(row.get("Код брокера")),
        "name": _strip(row.get("Наименование")),
        "inn": _strip(row.get("ИНН")),
        "region": _strip(row.get("Регион")),
    }


def _p_participant(row: dict[str, str], svc: ImportService, w: Counter) -> dict[str, Any] | None:
    role = _choice(row.get("Роль"), ROLES)
    if _strip(row.get("Роль")) and role is None:
        w["participants.role_unrecognised_to_null"] += 1
    return {
        "inn": _strip(row.get("ИНН")),
        "name": _strip(row.get("Наименование")),
        "region": _strip(row.get("Регион")),
        "activity": _strip(row.get("Вид деятельности")),
        "role": role,
        "vat_payer": bool(parse_bool(row.get("Плательщик НДС"))),
    }


def _p_usd(row: dict[str, str], svc: ImportService, w: Counter) -> dict[str, Any] | None:
    return {"date": parse_date(row.get("Дата")), "rate": parse_decimal(row.get("Курс"), 2)}


def _p_contract(row: dict[str, str], svc: ImportService, w: Counter) -> dict[str, Any] | None:
    cur_raw = _strip(row.get("Валюта"))
    cur = normalize_currency(cur_raw)
    if cur_raw and cur is None:
        w["contracts.currency_unrecognised_to_null"] += 1
    seller = _strip(row.get("ИНН продавца"))
    if seller and seller not in svc.known_inns:
        w["contracts.unknown_seller_inn_to_null"] += 1
        seller = None
    deposit = parse_decimal((row.get("Сумма залога") or "").replace("%", ""), 2)
    if deposit is not None and not (0 <= deposit < 1000):
        deposit = None
    ctype = _choice(row.get("Тип контракта"), CONTRACT_TYPES)
    cform = _choice(row.get("Форма контракта"), CONTRACT_FORMS)
    return {
        "contract_number": _strip(row.get("Номер контракта")),
        "product_name": _strip(row.get("Наименование продукта")),
        "tn_ved_code": _strip(row.get("Код ТН ВЭД")),
        "product_group": _strip(row.get("Группа товара")),
        "product_category": _strip(row.get("Категория товара")),
        "industry": _strip(row.get("Отрасль промышленности")),
        "unit": _strip(row.get("Единица измерения")),
        "lot_size": parse_decimal(row.get("Лот"), 3),
        "currency": cur,
        "base_price": parse_decimal(row.get("Базисная цена"), 2),
        "deposit_percent": deposit,
        "delivery_basis": _strip(row.get("Базис поставки")),
        "packaging": _strip(row.get("Упаковка")),
        "region": _strip(row.get("Регион")),
        "warehouse_address": _strip(row.get("Адрес склада")),
        "auction_type": _strip(row.get("Тип торгов")),
        "contract_type": ctype,
        "contract_form": cform,
        "payment_term_days": parse_int(row.get("Срок оплаты")),
        "delivery_term_days": parse_int(row.get("Срок поставки")),
        "seller_inn": seller,
        "registration_date": parse_date(row.get("Дата регистрации")),
        "valid_until": parse_date(row.get("Действует до")),
    }


def _p_deal(row: dict[str, str], svc: ImportService, w: Counter) -> dict[str, Any] | None:
    contract = _strip(row.get("Номер контракта"))
    if contract and contract not in svc.known_contracts:
        w["deals.unknown_contract_to_null"] += 1
        contract = None
    out: dict[str, Any] = {}
    for attr, col, known, key in (
        ("seller_inn", "ИНН продавца", svc.known_inns, "deals.unknown_seller_inn_to_null"),
        ("buyer_inn", "ИНН покупателя", svc.known_inns, "deals.unknown_buyer_inn_to_null"),
        ("broker_seller_code", "Брокер продавца", svc.known_brokers, "deals.unknown_seller_broker_to_null"),
        ("broker_buyer_code", "Брокер покупателя", svc.known_brokers, "deals.unknown_buyer_broker_to_null"),
    ):
        val = _strip(row.get(col))
        if val and val not in known:
            w[key] += 1
            val = None
        out[attr] = val
    out.update(
        {
            "deal_number": parse_int(row.get("Номер сделки")),
            "deal_date": parse_date(row.get("Дата сделки")),
            "deal_time": parse_time(row.get("Время сделки")),
            "auction_type": _strip(row.get("Тип торгов")),
            "quantity": parse_int(row.get("Количество")),
            "amount": parse_decimal(row.get("Сумма сделки"), 2),
            "start_price": parse_decimal(row.get("Стартовая цена"), 2),
            "contract_number": contract,
            "product_name": _strip(row.get("Наименование товара")),
            "lot_size": parse_decimal(row.get("Лот"), 3),
            "unit": _strip(row.get("Единица измерения")),
            "region": _strip(row.get("Регион")),
            "contract_type": _strip(row.get("Тип контракта")),
            "contract_form": _strip(row.get("Форма контракта")),
            "status": _strip(row.get("Состояние сделки")),
            "payment_date": parse_date(row.get("Дата оплаты")),
            "delivery_date": parse_date(row.get("Дата поставки")),
            "delivered_quantity": parse_int(row.get("Поставлено")),
        }
    )
    return out


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class ImportService:
    """Idempotent, batched CSV import."""

    SPECS: dict[str, _Spec] = {
        "brokers": _Spec(
            "brokers.csv", "brokers", Broker, "code",
            ["Код брокера", "Наименование", "ИНН", "Регион"], _p_broker,
            ["code", "name", "inn", "region"],
        ),
        "participants": _Spec(
            "participants.csv", "participants", Participant, "inn",
            ["ИНН", "Наименование", "Регион"], _p_participant,
            ["inn", "name", "region"],
        ),
        "usd_rates": _Spec(
            "usd_rates.csv", "usd_rates", UsdRate, "date",
            ["Дата", "Курс"], _p_usd, ["date", "rate"],
        ),
        "contracts": _Spec(
            "contracts.csv", "contracts", Contract, "contract_number",
            ["Номер контракта", "Наименование продукта"], _p_contract,
            [
                "contract_number", "product_name", "unit", "lot_size", "base_price",
                "payment_term_days", "delivery_term_days", "registration_date", "valid_until",
            ],
        ),
    }
    DEAL_SPEC = _Spec(
        "deals_*.csv", "deals", Deal, "deal_number",
        ["Номер сделки", "Дата сделки"], _p_deal,
        [
            "deal_number", "deal_date", "deal_time", "auction_type", "quantity", "amount",
            "start_price", "product_name", "lot_size", "unit", "status",
        ],
    )

    # Full CSV headers (also read by scripts/check_data.py via AST).
    DEALS_COLUMNS = [
        "Номер сделки", "Дата сделки", "Время сделки", "Тип торгов", "Количество",
        "Сумма сделки", "Стартовая цена", "Номер контракта", "Наименование товара",
        "Лот", "Единица измерения", "Регион", "Тип контракта", "Форма контракта",
        "Состояние сделки", "ИНН продавца", "ИНН покупателя", "Брокер продавца",
        "Брокер покупателя", "Дата оплаты", "Дата поставки", "Поставлено",
    ]
    DEALS_REQUIRED = ["Номер сделки", "Дата сделки"]
    CONTRACTS_COLUMNS = [
        "Номер контракта", "Наименование продукта", "Марка товара", "Размер товара",
        "Сорт товара", "Тип товара", "Класс товара", "Код ТН ВЭД", "Группа товара",
        "Категория товара", "Отрасль промышленности", "Единица измерения", "Лот",
        "Валюта", "Базисная цена", "Сумма залога", "Базис поставки", "Регион",
        "Адрес склада", "Тип торгов", "Тип контракта", "Форма контракта", "Срок оплаты",
        "Срок поставки", "Упаковка", "ИНН продавца", "Дата регистрации", "Действует до",
    ]
    CONTRACTS_REQUIRED = ["Номер контракта"]
    PARTICIPANTS_COLUMNS = [
        "ИНН", "Наименование", "Регион", "Вид деятельности", "Роль", "Плательщик НДС",
    ]
    PARTICIPANTS_REQUIRED = ["ИНН", "Наименование"]
    BROKERS_COLUMNS = ["Код брокера", "Наименование", "ИНН", "Регион"]
    BROKERS_REQUIRED = ["Код брокера", "Наименование"]
    USD_RATES_COLUMNS = ["Дата", "Курс"]
    USD_RATES_REQUIRED = ["Дата", "Курс"]

    def __init__(self, data_dir: str | None = None) -> None:
        d = Path(data_dir or settings.data_dir)
        # relative paths are resolved against the backend directory
        self.data_dir = d if d.is_absolute() else Path(__file__).resolve().parents[2] / d
        self.known_inns: set[str] = set()
        self.known_contracts: set[str] = set()
        self.known_brokers: set[str] = set()

    # -- public API -----------------------------------------------------
    async def import_all(self, db: AsyncSession) -> list[ImportReport]:
        reports = [
            await self.import_brokers(db),
            await self.import_participants(db),
            await self.import_usd_rates(db),
            await self.import_contracts(db),
            await self.import_deals(db),
        ]
        try:  # cached analytics are stale after an import
            from app.core.redis import cache

            await cache.clear()
        except Exception:  # pragma: no cover
            log.warning("cache clear failed after import")
        return reports

    async def import_brokers(self, db: AsyncSession) -> ImportReport:
        return await self._import_file(db, self.SPECS["brokers"], self.data_dir / "brokers.csv")

    async def import_participants(self, db: AsyncSession) -> ImportReport:
        return await self._import_file(
            db, self.SPECS["participants"], self.data_dir / "participants.csv"
        )

    async def import_usd_rates(self, db: AsyncSession) -> ImportReport:
        return await self._import_file(db, self.SPECS["usd_rates"], self.data_dir / "usd_rates.csv")

    async def import_contracts(self, db: AsyncSession) -> ImportReport:
        self.known_inns = await self._existing(db, Participant.inn)
        return await self._import_file(db, self.SPECS["contracts"], self.data_dir / "contracts.csv")

    async def import_deals(self, db: AsyncSession) -> ImportReport:
        total = ImportReport(file="deals_*.csv", table="deals")
        files = sorted(self.data_dir.glob("deals_*.csv"))
        if not files:
            total.errors.append("deals_*.csv files not found in DATA_DIR")
            return total
        self.known_inns = await self._existing(db, Participant.inn)
        self.known_brokers = await self._existing(db, Broker.code)
        self.known_contracts = await self._existing(db, Contract.contract_number)
        for path in files:  # deals_2022 ... deals_2026, sequentially
            r = await self._import_file(db, self.DEAL_SPEC, path)
            total.total_rows += r.total_rows
            total.inserted += r.inserted
            total.skipped += r.skipped
            total.invalid += r.invalid
            total.errors.extend(r.errors)
            for k, v in r.warnings.items():
                total.warnings[k] = total.warnings.get(k, 0) + v
            total.record_errors.extend(r.record_errors[: max(0, MAX_RECORD_ERRORS - len(total.record_errors))])
        return total

    # -- internals ------------------------------------------------------
    @staticmethod
    async def _existing(db: AsyncSession, col: Any) -> set[str]:
        return set((await db.execute(select(col))).scalars().all())

    @staticmethod
    def _insert_stmt(db: AsyncSession, model: Any):
        name = db.get_bind().dialect.name
        if name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        return insert(model).on_conflict_do_nothing()

    async def _import_file(self, db: AsyncSession, spec: _Spec, path: Path) -> ImportReport:
        report = ImportReport(file=path.name, table=spec.table)
        if not path.exists():
            report.errors.append(f"file not found: {path.name}")
            log.error("Import file missing: %s", path)
            return report

        warn: Counter = Counter()
        pk_col = getattr(spec.model, spec.pk)
        existing = await self._existing(db, pk_col)
        stmt = self._insert_stmt(db, spec.model)
        batch: list[dict[str, Any]] = []
        batch_rows: list[int] = []

        async def flush() -> None:
            if not batch:
                return
            await self._flush(db, stmt, batch, batch_rows, report)
            batch.clear()
            batch_rows.clear()

        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            reader.fieldnames = [(fn or "").strip() for fn in reader.fieldnames or []]
            missing = [c for c in spec.required_columns if c not in reader.fieldnames]
            if missing:
                report.errors.append(f"missing columns: {missing}")
                return report

            for row_num, row in enumerate(reader, start=2):
                report.total_rows += 1
                parsed = spec.parse_row(row, self, warn)
                bad = [k for k in spec.not_null if parsed is None or parsed.get(k) is None]
                if parsed is None or bad:
                    report.invalid += 1
                    if len(report.record_errors) < MAX_RECORD_ERRORS:
                        report.record_errors.append(
                            ImportRecordResult(False, row_num, "invalid", [f"missing/invalid: {bad}"])
                        )
                    continue
                pk = parsed[spec.pk]
                if pk in existing:
                    report.skipped += 1
                    continue
                existing.add(pk)
                batch.append(parsed)
                batch_rows.append(row_num)
                if len(batch) >= settings.import_batch_size:
                    await flush()
            await flush()

        report.warnings = dict(warn)
        if spec.table == "participants":
            self.known_inns = existing
        elif spec.table == "brokers":
            self.known_brokers = existing
        elif spec.table == "contracts":
            self.known_contracts = existing
        log.info("Imported %s: %s", path.name, report.summary_line())
        return report

    async def _flush(
        self,
        db: AsyncSession,
        stmt: Any,
        batch: list[dict[str, Any]],
        rows: list[int],
        report: ImportReport,
    ) -> None:
        try:
            await db.execute(stmt, batch)
            await db.commit()
            report.inserted += len(batch)
            return
        except Exception:
            await db.rollback()
        # Isolate bad rows (e.g. CHECK violation) with row-by-row inserts.
        for data, row_num in zip(batch, rows, strict=True):
            try:
                await db.execute(stmt, [data])
                await db.commit()
                report.inserted += 1
            except Exception as exc:
                await db.rollback()
                report.invalid += 1
                if len(report.record_errors) < MAX_RECORD_ERRORS:
                    report.record_errors.append(
                        ImportRecordResult(False, row_num, "invalid", [type(exc).__name__])
                    )
