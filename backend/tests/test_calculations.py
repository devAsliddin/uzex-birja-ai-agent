"""Business calculation tests."""

from datetime import date

from app.services.calculation_service import (
    calculate_amount_uzs,
    calculate_unit_price,
    calculate_volume,
)


def test_volume():
    assert calculate_volume(100, 5) == 500
    assert calculate_volume(None, 5) is None
    assert calculate_volume(100, None) is None


def test_unit_price():
    assert calculate_unit_price(1000, 100, 5) == 1000 / 500
    assert calculate_unit_price(1000, 0, 5) is None
    assert calculate_unit_price(None, 100, 5) is None


async def test_amount_uzs_with_rate(db):
    # fixture usd_rates: 03.01.2022 is missing; calculation service reports it, FX SQL falls back
    result = await calculate_amount_uzs(100.0, date(2022, 1, 5), db)
    assert result["rate_available"] is True
    assert result["rate"] == 10840
    assert result["amount_uzs"] == 100.0 * 10840


async def test_amount_uzs_no_rate(db):
    result = await calculate_amount_uzs(100.0, date(2020, 1, 1), db)
    assert result["rate_available"] is False and result["amount_uzs"] is None


def test_resolve_rate_nearest_previous():
    from app.services.fx import resolve_rate

    days = [date(2022, 1, 1), date(2022, 1, 2), date(2022, 1, 4)]
    rates = [1.0, 2.0, 4.0]
    assert resolve_rate(days, rates, date(2022, 1, 3)) == 2.0
    assert resolve_rate(days, rates, date(2022, 1, 4)) == 4.0
    assert resolve_rate(days, rates, date(2021, 12, 31)) is None
