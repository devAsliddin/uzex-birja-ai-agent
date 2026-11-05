"""Read-side queries for the exchange registry (brokers, deals, analytics).

All queries use SQL aggregation / pagination (500k deals) and bound parameters
only. USD contracts are converted to UZS in SQL via ``app.services.fx``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import String, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import FunctionElement

from app.core.config import settings
from app.core.regions import UZ_TO_RU, canonical_region, region_variants
from app.core.ttl_cache import cached
from app.db.models.broker import Broker
from app.db.models.contract import Contract
from app.db.models.deal import Deal
from app.db.models.participant import Participant
from app.db.models.usd_rate import UsdRate
from app.services import fx


class ci_lower(FunctionElement):  # noqa: N801
    """Case-insensitive lower(): Python casefold on SQLite (Cyrillic-safe), lower() elsewhere."""

    type = String()
    inherit_cache = True


@compiles(ci_lower)
def _ci_default(element, compiler, **kw):
    return f"lower({compiler.process(element.clauses, **kw)})"


@compiles(ci_lower, "sqlite")
def _ci_sqlite(element, compiler, **kw):
    return f"py_casefold({compiler.process(element.clauses, **kw)})"


Seller = aliased(Participant, name="seller_p")
Buyer = aliased(Participant, name="buyer_p")

DEAL_SORTS = {
    "deal_date": None,  # handled specially (deal_date, deal_no)
    "deal_no": Deal.deal_number,
    "amount": Deal.amount,
    "quantity": Deal.quantity,
    "status": Deal.status,
}


def _f(v: Any) -> float | None:
    return None if v is None else float(v)


def split_multi(values: Sequence[str] | None) -> list[str]:
    """Accept repeated params and comma separated lists: ?status=A&status=B,C"""
    out: list[str] = []
    for v in values or []:
        out.extend(p.strip() for p in v.split(",") if p.strip())
    return out


def _like(term: str) -> str:
    esc = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{esc}%"


# ---------------------------------------------------------------------------
# Deals
# ---------------------------------------------------------------------------
def deal_conditions(
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    statuses: Sequence[str] | None = None,
    broker: str | None = None,
    region: str | None = None,
    search: str | None = None,
    seller_inn: str | None = None,
    buyer_inn: str | None = None,
    contract_no: str | None = None,
    product_names: list[str] | None = None,
) -> list[Any]:
    c: list[Any] = []
    if start_date:
        c.append(Deal.deal_date >= start_date)
    if end_date:
        c.append(Deal.deal_date <= end_date)
    if statuses:
        c.append(Deal.status.in_(list(statuses)))
    if broker:
        c.append(or_(Deal.broker_seller_code == broker, Deal.broker_buyer_code == broker))
    if region:
        c.append(Deal.region.in_(region_variants(region)))
    if seller_inn:
        c.append(Deal.seller_inn == seller_inn)
    if buyer_inn:
        c.append(Deal.buyer_inn == buyer_inn)
    if contract_no:
        c.append(Deal.contract_number == contract_no)
    if search:
        term = search.strip()
        if product_names is not None:  # resolved case-insensitively (see resolve_search)
            conds = [Deal.product_name.in_(product_names)]
        else:
            conds = [ci_lower(Deal.product_name).like(_like(term.casefold()), escape="\\")]
        if term.isdigit() and len(term) <= 18:
            conds.append(Deal.deal_number == int(term))
        c.append(or_(*conds))
    return c


async def _distinct_product_names() -> list[str]:
    from app.db.session import get_read_session_factory

    async def load() -> list[str]:
        async with get_read_session_factory()() as s:
            rows = await s.execute(select(Deal.product_name).distinct())
            return [r[0] for r in rows.all() if r[0]]

    return await cached("product_names", settings.cache_ttl_seconds, load)


async def resolve_search(term: str | None) -> list[str] | None:
    """Case-insensitive (Cyrillic-safe) product-name match via the cached distinct list."""
    if not term or not term.strip():
        return None
    needle = term.strip().casefold()
    return [n for n in await _distinct_product_names() if needle in n.casefold()]


def _deal_select():
    cols = [
        Deal.deal_number.label("deal_no"),
        Deal.deal_date,
        Deal.deal_time,
        Deal.auction_type.label("trade_type"),
        Deal.quantity,
        Deal.amount,
        Deal.start_price,
        Contract.currency,
        fx.amount_uzs_expr().label("amount_uzs"),
        Deal.contract_number.label("contract_no"),
        Deal.product_name,
        Deal.lot_size,
        Deal.unit,
        Deal.region,
        Deal.contract_type,
        Deal.contract_form,
        Deal.status,
        Deal.seller_inn,
        Seller.name.label("seller_name"),
        Deal.buyer_inn,
        Buyer.name.label("buyer_name"),
        Deal.broker_seller_code.label("seller_broker"),
        Deal.broker_buyer_code.label("buyer_broker"),
        Deal.payment_date,
        Deal.delivery_date,
        Deal.delivered_quantity.label("delivered_lots"),
    ]
    return (
        select(*cols)
        .select_from(Deal)
        .outerjoin(Contract, Contract.contract_number == Deal.contract_number)
        .outerjoin(Seller, Seller.inn == Deal.seller_inn)
        .outerjoin(Buyer, Buyer.inn == Deal.buyer_inn)
    )


EXPORT_COLUMNS = [
    "deal_no", "deal_date", "deal_time", "trade_type", "quantity", "amount", "currency",
    "amount_uzs", "start_price", "contract_no", "product_name", "lot_size", "unit", "region",
    "contract_type", "contract_form", "status", "seller_inn", "seller_name", "buyer_inn",
    "buyer_name", "seller_broker", "buyer_broker", "payment_date", "delivery_date",
    "delivered_lots",
]


def _row_to_dict(r: Any) -> dict[str, Any]:
    d = dict(r._mapping)
    for k in ("amount", "amount_uzs", "start_price", "lot_size"):
        d[k] = _f(d.get(k))
    d["region_key"] = canonical_region(d.get("region"))
    return d


async def list_deals(
    db: AsyncSession,
    *,
    conditions: list[Any],
    page: int,
    limit: int,
    sort: str = "deal_date",
    desc: bool = True,
    status_conditions: list[Any] | None = None,
) -> dict[str, Any]:
    """``status_conditions``: filters WITHOUT the status filter; when given,
    the result carries ``status_counts`` for those filters."""
    where = and_(*conditions) if conditions else None
    count_q = select(func.count()).select_from(Deal)
    if where is not None:
        count_q = count_q.where(where)
    total = (await db.execute(count_q)).scalar_one()

    q = _deal_select()
    if where is not None:
        q = q.where(where)
    if sort == "deal_date" or sort not in DEAL_SORTS:
        # Mirrors idx_deals_date_status (deal_date DESC, status, rowid) so the
        # ORDER BY is satisfied by the index (no 500k-row sort) and is stable.
        q = q.order_by(
            Deal.deal_date.desc() if desc else Deal.deal_date.asc(),
            Deal.status.asc() if desc else Deal.status.desc(),
            Deal.deal_number.asc() if desc else Deal.deal_number.desc(),
        )
    else:
        col = DEAL_SORTS[sort]
        q = q.order_by(col.desc() if desc else col.asc(), Deal.deal_number.asc())
    q = q.offset((page - 1) * limit).limit(limit)
    rows = (await db.execute(q)).all()
    pages = (total + limit - 1) // limit if limit else 0
    out: dict[str, Any] = {
        "items": [_row_to_dict(r) for r in rows],
        "total": total,
        "page": page,
        "limit": limit,
        "pages": pages,
    }
    if status_conditions is not None:
        sq = select(Deal.status, func.count()).select_from(Deal).group_by(Deal.status)
        if status_conditions:
            sq = sq.where(and_(*status_conditions))
        out["status_counts"] = dict((await db.execute(sq)).all())
    return out


def export_query(conditions: list[Any]):
    q = _deal_select()
    if conditions:
        q = q.where(and_(*conditions))
    return q.order_by(Deal.deal_number.asc()).limit(settings.export_max_rows)


async def _rate_for(db: AsyncSession, day: date) -> dict[str, Any] | None:
    row = (
        await db.execute(
            select(UsdRate.date, UsdRate.rate)
            .where(UsdRate.date <= day)
            .order_by(UsdRate.date.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return None
    return {"requested_date": day, "rate_date": row[0], "rate": float(row[1]), "exact": row[0] == day}


def _obj(o: Any, fields: Sequence[str]) -> dict[str, Any] | None:
    if o is None:
        return None
    out: dict[str, Any] = {}
    for f in fields:
        v = getattr(o, f)
        out[f] = float(v) if hasattr(v, "as_integer_ratio") and not isinstance(v, (int, bool)) else v
    return out


async def deal_card(db: AsyncSession, deal_no: int) -> dict[str, Any] | None:
    deal = (await db.execute(select(Deal).where(Deal.deal_number == deal_no))).scalar_one_or_none()
    if deal is None:
        return None
    c = deal.contract
    currency = c.currency if c else None
    rate = await _rate_for(db, deal.deal_date)
    is_usd = currency == fx.CURRENCY_USD
    amount_uzs = deal.amount
    if is_usd:
        amount_uzs = round(deal.amount * rate["rate"], 2) if rate else None
    return {
        "deal_no": deal.deal_number,
        "deal_date": deal.deal_date,
        "deal_time": deal.deal_time,
        "trade_type": deal.auction_type,
        "quantity": deal.quantity,
        "amount": _f(deal.amount),
        "currency": currency,
        "amount_uzs": _f(amount_uzs),
        "start_price": _f(deal.start_price),
        "lot_size": _f(deal.lot_size),
        "unit": deal.unit,
        "volume": deal.volume,
        "product_name": deal.product_name,
        "region": deal.region,
        "region_key": canonical_region(deal.region),
        "contract_no": deal.contract_number,
        "contract_type": deal.contract_type,
        "contract_form": deal.contract_form,
        "status": deal.status,
        "payment_date": deal.payment_date,
        "delivery_date": deal.delivery_date,
        "delivered_lots": deal.delivered_quantity,
        "usd_rate": rate,
        "contract": _obj(
            c,
            [
                "contract_number", "product_name", "tn_ved_code", "product_group",
                "product_category", "industry", "unit", "lot_size", "currency", "base_price",
                "deposit_percent", "delivery_basis", "packaging", "region", "warehouse_address",
                "auction_type", "contract_type", "contract_form", "payment_term_days",
                "delivery_term_days", "seller_inn", "registration_date", "valid_until",
            ],
        ),
        "seller": _obj(deal.seller, ["inn", "name", "region", "activity", "role", "vat_payer"]),
        "buyer": _obj(deal.buyer, ["inn", "name", "region", "activity", "role", "vat_payer"]),
        "seller_broker": _obj(deal.broker_seller, ["code", "name", "inn", "region"]),
        "buyer_broker": _obj(deal.broker_buyer, ["code", "name", "inn", "region"]),
    }


# ---------------------------------------------------------------------------
# Brokers
# ---------------------------------------------------------------------------
async def _broker_aggregates(db: AsyncSession) -> dict[str, dict[str, Any]]:
    """Per-broker deal counts and UZS turnover (broker as seller-side or buyer-side)."""
    uzs = fx.executed_amount_expr("UZS")
    out: dict[str, dict[str, Any]] = {}

    async def collect(code_col: Any, role: str, extra: Any = None) -> list[Any]:
        q = (
            select(code_col, Deal.status, func.count(), func.coalesce(func.sum(uzs), 0))
            .select_from(Deal)
            .outerjoin(Contract, Contract.contract_number == Deal.contract_number)
            .where(code_col.is_not(None))
            .group_by(code_col, Deal.status)
        )
        if extra is not None:
            q = q.where(extra)
        return list((await db.execute(q)).all())

    for role, col in (
        ("seller", Deal.broker_seller_code),
        ("buyer", Deal.broker_buyer_code),
    ):
        for code, status, cnt, turn in await collect(col, role):
            a = out.setdefault(
                code,
                {"deals": 0, "turnover": 0.0, "as_seller": 0, "as_buyer": 0, "by_status": {}},
            )
            a["deals"] += cnt
            a["turnover"] += float(turn)
            a["as_" + role] += cnt
            s = a["by_status"].setdefault(status, {"deals": 0, "turnover": 0.0})
            s["deals"] += cnt
            s["turnover"] += float(turn)
    # a deal where seller broker == buyer broker was counted twice: subtract once
    same = await collect(Deal.broker_seller_code, "both", Deal.broker_seller_code == Deal.broker_buyer_code)
    for code, status, cnt, turn in same:
        a = out[code]
        a["deals"] -= cnt
        a["turnover"] -= float(turn)
        s = a["by_status"][status]
        s["deals"] -= cnt
        s["turnover"] -= float(turn)
    ranked = sorted(out.items(), key=lambda kv: (-kv[1]["turnover"], kv[0]))
    for i, (_, a) in enumerate(ranked, start=1):
        a["rank"] = i
    return out


async def broker_aggregates(db: AsyncSession) -> dict[str, dict[str, Any]]:
    return await cached("broker_aggregates", settings.cache_ttl_seconds, lambda: _broker_aggregates(db))


async def list_brokers(
    db: AsyncSession,
    *,
    page: int,
    limit: int,
    region: str | None,
    search: str | None,
    sort: str = "rating",
) -> dict[str, Any]:
    agg = await broker_aggregates(db)
    q = select(Broker)
    if region:
        q = q.where(Broker.region.in_(region_variants(region)))
    brokers = list((await db.execute(q)).scalars().all())
    if search:
        needle = search.strip().casefold()
        brokers = [
            b for b in brokers if needle in f"{b.code} {b.name} {b.inn}".casefold()
        ]
    total_brokers = (await db.execute(select(func.count()).select_from(Broker))).scalar_one()
    items = []
    for b in brokers:
        a = agg.get(b.code, {})
        items.append(
            {
                "broker_code": b.code,
                "name": b.name,
                "inn": b.inn,
                "region": b.region,
                "region_key": canonical_region(b.region),
                "deals_count": a.get("deals", 0),
                "turnover_uzs": round(a.get("turnover", 0.0), 2),
                "rating": a.get("rank", total_brokers),
            }
        )
    keys = {
        "rating": lambda i: (i["rating"], i["broker_code"]),
        "name": lambda i: i["name"].lower(),
        "deals": lambda i: (-i["deals_count"], i["broker_code"]),
        "turnover": lambda i: (-i["turnover_uzs"], i["broker_code"]),
    }
    items.sort(key=keys.get(sort, keys["rating"]))
    total = len(items)
    start = (page - 1) * limit
    return {
        "items": items[start : start + limit],
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if limit else 0,
    }


async def broker_profile(db: AsyncSession, code: str) -> dict[str, Any] | None:
    b = (await db.execute(select(Broker).where(Broker.code == code))).scalar_one_or_none()
    if b is None:
        return None
    agg = await broker_aggregates(db)
    a = agg.get(code, {"deals": 0, "turnover": 0.0, "as_seller": 0, "as_buyer": 0, "by_status": {}})
    total_brokers = (await db.execute(select(func.count()).select_from(Broker))).scalar_one()
    return {
        "broker_code": b.code,
        "name": b.name,
        "inn": b.inn,
        "region": b.region,
        "region_key": canonical_region(b.region),
        "rating": {"rank": a.get("rank", total_brokers), "of": total_brokers},
        "stats": {
            "deals_count": a["deals"],
            "deals_as_seller_broker": a["as_seller"],
            "deals_as_buyer_broker": a["as_buyer"],
            "turnover_uzs": round(a["turnover"], 2),
            "avg_deal_uzs": round(a["turnover"] / a["deals"], 2) if a["deals"] else None,
            "by_status": [
                {"status": s, "deals_count": v["deals"], "turnover_uzs": round(v["turnover"], 2)}
                for s, v in sorted(a["by_status"].items(), key=lambda kv: -kv[1]["deals"])
            ],
        },
    }


# ---------------------------------------------------------------------------
# Analytics / meta
# ---------------------------------------------------------------------------
async def _summary(db: AsyncSession, year: int | None, currency: str) -> dict[str, Any]:
    amt = fx.executed_amount_expr(currency)
    yr = func.extract("year", Deal.deal_date)
    base = select(Deal).outerjoin(Contract, Contract.contract_number == Deal.contract_number)  # noqa: F841

    def scoped(q: Any) -> Any:
        return q.where(yr == year) if year else q

    def joined(*cols: Any) -> Any:
        return select(*cols).select_from(Deal).outerjoin(
            Contract, Contract.contract_number == Deal.contract_number
        )

    yearly_rows = (
        await db.execute(
            joined(yr, func.count(), func.coalesce(func.sum(amt), 0)).group_by(yr).order_by(yr)
        )
    ).all()
    yearly = [
        {"year": int(y), "deals_count": c, "turnover": round(float(t), 2)} for y, c, t in yearly_rows
    ]
    if year:
        sel = [y for y in yearly if y["year"] == year]
        deals_count = sel[0]["deals_count"] if sel else 0
        turnover = sel[0]["turnover"] if sel else 0.0
    else:
        deals_count = sum(y["deals_count"] for y in yearly)
        turnover = round(sum(y["turnover"] for y in yearly), 2)

    region_rows = (
        await db.execute(
            scoped(
                joined(Deal.region, func.count(), func.coalesce(func.sum(amt), 0))
                .where(Deal.region.is_not(None))
                .group_by(Deal.region)
            ).order_by(func.sum(amt).desc())
        )
    ).all()
    merged: dict[str, list[float]] = {}
    for r, c, t in region_rows:
        m = merged.setdefault(canonical_region(r) or r, [0, 0.0])
        m[0] += c
        m[1] += float(t)
    reg_total = sum(v[1] for v in merged.values()) or 1.0
    regions = [
        {
            "region": k,
            "region_ru": UZ_TO_RU.get(k),
            "deals_count": int(v[0]),
            "turnover": round(v[1], 2),
            "share_pct": round(v[1] / reg_total * 100, 2),
        }
        for k, v in sorted(merged.items(), key=lambda kv: -kv[1][1])
    ]

    cat_rows = (
        await db.execute(
            scoped(
                joined(Contract.product_category, func.count(), func.coalesce(func.sum(amt), 0))
                .where(Contract.product_category.is_not(None))
                .group_by(Contract.product_category)
            )
            .order_by(func.sum(amt).desc())
            .limit(10)
        )
    ).all()
    top_categories = [
        {"category": k, "deals_count": c, "turnover": round(float(t), 2)} for k, c, t in cat_rows
    ]

    monthly: list[dict[str, Any]] = []
    if year:
        mo = func.extract("month", Deal.deal_date)
        m_rows = (
            await db.execute(
                scoped(joined(mo, func.count(), func.coalesce(func.sum(amt), 0))).group_by(mo).order_by(mo)
            )
        ).all()
        monthly = [
            {"month": int(m), "deals_count": c, "turnover": round(float(t), 2)} for m, c, t in m_rows
        ]

    sc = select(Deal.status, func.count()).select_from(Deal).group_by(Deal.status)
    status_counts = dict((await db.execute(scoped(sc))).all())

    last = (
        await db.execute(select(UsdRate.date, UsdRate.rate).order_by(UsdRate.date.desc()).limit(1))
    ).first()
    today = date.today()
    cur = await _rate_for(db, today)
    usd_current = (
        {"date": cur["rate_date"], "rate": cur["rate"]}
        if cur
        else ({"date": last[0], "rate": float(last[1])} if last else None)
    )
    broker_count = (await db.execute(select(func.count()).select_from(Broker))).scalar_one()
    return {
        "year": year,
        "currency": currency.upper(),
        "total_turnover": turnover,
        "deals_count": deals_count,
        "broker_count": broker_count,
        "usd_rate": usd_current,
        "status_counts": status_counts,
        "annulled_deals_count": status_counts.get(fx.STATUS_ANNULLED, 0),
        "turnover_basis": f"excludes status {fx.STATUS_ANNULLED}; deals_count includes all deals",
        "yearly": yearly,
        "monthly": monthly,
        "regions": regions,
        "top_categories": top_categories,
    }


async def analytics_summary(db: AsyncSession, year: int | None, currency: str) -> dict[str, Any]:
    cur = "USD" if currency.upper() == "USD" else "UZS"
    return await cached(
        f"summary:{year}:{cur}", settings.cache_ttl_seconds, lambda: _summary(db, year, cur)
    )


async def _meta(db: AsyncSession) -> dict[str, Any]:
    async def distinct(col: Any) -> list[str]:
        rows = await db.execute(select(col).where(col.is_not(None)).distinct().order_by(col))
        return [r[0] for r in rows.all()]

    yr = func.extract("year", Deal.deal_date)
    years = [int(r[0]) for r in (await db.execute(select(yr).distinct().order_by(yr))).all()]
    return {
        "statuses": await distinct(Deal.status),
        "regions": sorted({canonical_region(r) for r in await distinct(Deal.region)} - {None}),
        "broker_regions": sorted({canonical_region(r) for r in await distinct(Broker.region)} - {None}),
        "region_labels_ru": UZ_TO_RU,
        "trade_types": await distinct(Deal.auction_type),
        "years": years,
    }


async def meta_filters(db: AsyncSession) -> dict[str, Any]:
    return await cached("meta_filters", settings.cache_ttl_seconds, lambda: _meta(db))
