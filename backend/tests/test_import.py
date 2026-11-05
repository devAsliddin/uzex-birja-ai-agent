"""ETL / cleansing tests on fixture CSVs."""

from datetime import date, time

from sqlalchemy import func, select

from app.db.models.contract import Contract
from app.db.models.deal import Deal
from app.db.models.participant import Participant
from app.services.import_service import (
    ImportService,
    normalize_currency,
    parse_bool,
    parse_date,
    parse_decimal,
    parse_int,
    parse_time,
)

FIXTURES_DIR = __import__("pathlib").Path(__file__).parent / "fixtures"


def test_parsers():
    assert parse_decimal("1 250 000.00") == 1250000.0
    assert parse_decimal("1 250 000.5") == 1250000.5
    assert parse_decimal("543 505 640") == 543505640.0
    assert parse_decimal("") is None and parse_decimal("abc") is None
    assert parse_int("79 720") == 79720 and parse_int("") is None and parse_int("1.5") is None
    assert parse_date("03.01.2022") == date(2022, 1, 3) and parse_date("") is None
    assert parse_date("31.02.2022") is None
    assert parse_time("10:04:49") == time(10, 4, 49)
    assert parse_bool("Да") is True and parse_bool("Нет") is False and parse_bool("") is None
    assert normalize_currency("Доллар США") == "Доллар США"
    assert normalize_currency("USD") == "Доллар США"
    assert normalize_currency("Узбекский сум") == "Узбекский сум"


async def test_counts_and_reports(seeded):
    assert seeded["brokers"].inserted == 3
    assert seeded["participants"].inserted == 3
    assert seeded["usd_rates"].inserted == 5
    assert seeded["contracts"].inserted == 2
    d = seeded["deals"]
    assert d.total_rows == 6 and d.inserted == 5 and d.invalid == 1
    # unknown buyer INN + unknown buyer broker are nulled and counted
    assert d.warnings["deals.unknown_buyer_inn_to_null"] == 1
    assert d.warnings["deals.unknown_buyer_broker_to_null"] == 1


async def test_cleansing_values(db):
    d = (await db.execute(select(Deal).where(Deal.deal_number == 1000))).scalar_one()
    assert d.amount == 1250000.0 and d.start_price == 3731.07
    assert d.deal_date == date(2022, 1, 3) and d.payment_date == date(2022, 1, 5)
    assert d.product_name == "Профиль, алюминиевый"  # quoted comma preserved
    d2 = (await db.execute(select(Deal).where(Deal.deal_number == 1001))).scalar_one()
    assert d2.payment_date is None and d2.delivery_date is None and d2.delivered_quantity is None
    d3 = (await db.execute(select(Deal).where(Deal.deal_number == 2000))).scalar_one()
    assert d3.buyer_inn is None and d3.broker_buyer_code is None
    c = (await db.execute(select(Contract).where(Contract.contract_number == "100001"))).scalar_one()
    assert c.base_price == 54078.5 and c.deposit_percent == 10.0
    p = (await db.execute(select(Participant).where(Participant.inn == "200000002"))).scalar_one()
    assert p.vat_payer is False and p.role == "Покупатель"


async def test_idempotent_reimport(db, seeded):
    reports = await ImportService(data_dir=str(FIXTURES_DIR)).import_all(db)
    after = (await db.execute(select(func.count()).select_from(Deal))).scalar_one()
    assert after == 5
    assert all(r.inserted == 0 for r in reports)


async def test_missing_dir_reports_error(db):
    report = await ImportService(data_dir="/nonexistent/path").import_brokers(db)
    assert report.total_rows == 0 and report.errors
