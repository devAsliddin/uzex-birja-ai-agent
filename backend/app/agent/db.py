"""Read-only SQL execution for the agent.

Every query runs on a fresh ``mode=ro`` SQLite connection with ``PRAGMA query_only=ON``.
Only one SELECT/WITH statement is accepted; a progress handler enforces a timeout.
A TEMP view ``v_deals`` (deals + contract currency/classification + USD rate) is created
per connection so the model never has to re-derive the currency conversion.
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import settings

ANNULLED = "Аннулирован(Не оплачен)"

V_DEALS_SQL = f"""
CREATE TEMP VIEW v_deals AS
SELECT d.deal_no, d.deal_date, d.deal_time, d.trade_type, d.quantity, d.amount, d.start_price,
       d.contract_no, d.product_name, d.lot_size, d.unit, d.region, d.contract_type, d.contract_form,
       d.status, d.seller_inn, d.buyer_inn, d.seller_broker, d.buyer_broker,
       d.payment_date, d.delivery_date, d.delivered_lots,
       c.currency AS currency,
       CASE WHEN c.currency = 'Доллар США' THEN 1 ELSE 0 END AS is_usd,
       r.rate AS usd_rate,
       CASE WHEN c.currency = 'Доллар США' THEN d.amount * r.rate ELSE d.amount END AS amount_uzs,
       CASE WHEN c.currency = 'Доллар США' THEN d.amount ELSE d.amount / r.rate END AS amount_usd,
       d.quantity * d.lot_size AS volume,
       CASE WHEN d.quantity > 0 THEN d.amount / (d.quantity * d.lot_size) END AS unit_price,
       c.product_name AS contract_product, c.product_group, c.product_category, c.industry,
       c.tn_ved_code, c.base_price, c.payment_days, c.delivery_days, c.region AS contract_region,
       CASE WHEN d.payment_date IS NOT NULL
            THEN date(d.payment_date, '+' || c.delivery_days || ' days') END AS delivery_due_date,
       CASE WHEN d.status <> '{ANNULLED}' THEN 1 ELSE 0 END AS is_valid,
       CAST(substr(d.deal_date, 1, 4) AS INTEGER) AS year,
       CAST(substr(d.deal_date, 6, 2) AS INTEGER) AS month
FROM deals d
LEFT JOIN contracts c ON c.contract_no = d.contract_no
LEFT JOIN usd_rates r ON r.rate_date = d.deal_date
"""

_FORBIDDEN = re.compile(
    r"\b(attach|detach|pragma|insert|update|delete|replace|drop|create|alter|vacuum|reindex|"
    r"analyze|begin|commit|rollback|savepoint|release|load_extension|writefile|readfile|edit)\b",
    re.IGNORECASE,
)


class SQLValidationError(ValueError):
    pass


def db_path() -> Path:
    url = os.environ.get("AGENT_DATABASE_PATH") or settings.database_url
    if "///" in url:
        url = url.split("///", 1)[1]
    p = Path(url)
    if not p.is_absolute():
        p = (Path(__file__).resolve().parents[2] / p).resolve()
    return p


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n]*", " ", sql)
    return sql.strip()


def _without_strings(sql: str) -> str:
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def validate_sql(sql: str) -> str:
    """Return a cleaned single SELECT/WITH statement or raise SQLValidationError."""
    if not sql or not sql.strip():
        raise SQLValidationError("empty SQL")
    s = _strip_comments(sql).rstrip().rstrip(";").strip()
    bare = _without_strings(s)
    if ";" in bare:
        raise SQLValidationError("only one statement is allowed")
    head = bare.lstrip("( \n\t").split(None, 1)[0].lower() if bare.strip() else ""
    if head not in ("select", "with"):
        raise SQLValidationError("only SELECT/WITH queries are allowed")
    m = _FORBIDDEN.search(bare)
    if m:
        raise SQLValidationError(f"forbidden keyword: {m.group(1)}")
    if len(s) > 8000:
        raise SQLValidationError("SQL too long")
    return s


@dataclass
class QueryResult:
    sql: str
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    elapsed_ms: int = 0


def connect() -> sqlite3.Connection:
    path = db_path()
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5, check_same_thread=False)
    conn.execute(V_DEALS_SQL)  # TEMP schema only (in-memory), main DB stays read-only
    conn.execute("PRAGMA query_only=ON")
    return conn


def run_query(sql: str, *, max_rows: int = 200, timeout_s: float = 15.0) -> QueryResult:
    clean = validate_sql(sql)
    t0 = time.monotonic()
    deadline = t0 + timeout_s
    conn = connect()
    try:
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
        try:
            cur = conn.execute(clean)
        except sqlite3.OperationalError as exc:
            if "interrupted" in str(exc).lower():
                raise TimeoutError(f"query exceeded {timeout_s:.0f}s") from None
            raise
        columns = [d[0] for d in (cur.description or [])]
        rows: list[list[Any]] = []
        truncated = False
        for row in cur:
            if len(rows) >= max_rows:
                truncated = True
                break
            rows.append(list(row))
        return QueryResult(
            sql=clean,
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            elapsed_ms=int((time.monotonic() - t0) * 1000),
        )
    finally:
        conn.close()
