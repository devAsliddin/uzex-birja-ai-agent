"""Public API tests (no login) on fixture data."""

import csv
import io

import pytest

API = "/api/v1"


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200 and r.json()["database"] == "ok"


async def test_deals_public_list_and_pagination(client):
    r = await client.get(f"{API}/deals", params={"limit": 2})
    assert r.status_code == 200
    j = r.json()
    assert j["total"] == 5 and len(j["items"]) == 2 and j["pages"] == 3
    assert j["items"][0]["deal_no"] == 2000  # newest first
    r2 = await client.get(f"{API}/deals", params={"limit": 2, "page": 3})
    assert len(r2.json()["items"]) == 1


async def test_deals_filters(client):
    r = await client.get(
        f"{API}/deals",
        params={"start_date": "2022-01-03", "end_date": "2022-01-03", "status": ["Исполнен", "Заключен"]},
    )
    assert {d["deal_no"] for d in r.json()["items"]} == {1000, 1002}
    r = await client.get(f"{API}/deals", params={"status": "Исполнен,Оплачен"})
    assert {d["deal_no"] for d in r.json()["items"]} == {1000, 1003}
    r = await client.get(f"{API}/deals", params={"broker": "BK003"})
    assert {d["deal_no"] for d in r.json()["items"]} == {1002, 1003}
    r = await client.get(f"{API}/deals", params={"region": "Самаркандская область"})
    assert [d["deal_no"] for d in r.json()["items"]] == [2000]
    r = await client.get(f"{API}/deals", params={"region": "Samarqand viloyati"})
    assert [d["deal_no"] for d in r.json()["items"]] == [2000]
    r = await client.get(
        f"{API}/deals", params={"status": "Исполнен", "with_status_counts": True, "broker": "BK001"}
    )
    j = r.json()
    assert j["total"] == 1 and j["status_counts"]["Оплачен"] == 1 and sum(j["status_counts"].values()) == 4
    r = await client.get(f"{API}/deals", params={"search": "1001"})
    assert [d["deal_no"] for d in r.json()["items"]] == [1001]
    r = await client.get(f"{API}/deals", params={"search": "100%_"})  # LIKE wildcards are escaped
    assert r.json()["total"] == 0


async def test_usd_conversion_with_previous_day_fallback(client):
    # 03.01.2022 has no rate -> nearest previous day (02.01.2022 = 10810)
    j = (await client.get(f"{API}/deals/1002")).json()
    assert j["currency"] == "Доллар США"
    assert j["usd_rate"]["rate_date"] == "2022-01-02" and j["usd_rate"]["exact"] is False
    assert j["amount_uzs"] == pytest.approx(273558.87 * 10810, rel=1e-9)
    items = (await client.get(f"{API}/deals", params={"search": "1002"})).json()["items"]
    assert items[0]["amount_uzs"] == pytest.approx(273558.87 * 10810, rel=1e-9)
    j = (await client.get(f"{API}/deals/1000")).json()  # UZS contract: no conversion
    assert j["amount_uzs"] == j["amount"] == 1250000.0


async def test_deal_card(client):
    j = (await client.get(f"{API}/deals/1000")).json()
    assert j["contract"]["contract_number"] == "100001"
    assert j["seller"]["inn"] == "200000001" and j["buyer"]["inn"] == "200000002"
    assert j["seller_broker"]["code"] == "BK001" and j["buyer_broker"]["code"] == "BK002"
    assert j["usd_rate"]["rate"] == 10810 and j["usd_rate"]["rate_date"] == "2022-01-02"
    r = await client.get(f"{API}/deals/999999")
    assert r.status_code == 404 and "Traceback" not in r.text


async def test_brokers_rating_and_profile(client):
    j = (await client.get(f"{API}/brokers")).json()
    assert j["total"] == 3
    ratings = [b["rating"] for b in j["items"]]
    assert ratings == sorted(ratings) and ratings[0] == 1
    assert j["items"][0]["deals_count"] >= 1 and j["items"][0]["turnover_uzs"] > 0
    j = (await client.get(f"{API}/brokers", params={"region": "Toshkent shahri"})).json()
    assert {b["broker_code"] for b in j["items"]} == {"BK001", "BK003"}
    j = (await client.get(f"{API}/brokers", params={"search": "beta"})).json()
    assert [b["broker_code"] for b in j["items"]] == ["BK002"]
    p = (await client.get(f"{API}/brokers/BK002")).json()
    # BK002: both sides on 1001 (counted once) + buyer broker on 1000
    assert p["stats"]["deals_count"] == 2
    assert p["rating"]["of"] == 3
    assert (await client.get(f"{API}/brokers/BK999")).status_code == 404


async def test_analytics_summary(client):
    j = (await client.get(f"{API}/analytics/summary")).json()
    assert j["deals_count"] == 5 and j["broker_count"] == 3
    assert {y["year"] for y in j["yearly"]} == {2022, 2023}
    assert j["usd_rate"]["rate"] == 11000
    assert sum(j["status_counts"].values()) == 5 and j["status_counts"]["Исполнен"] == 1
    expected = 1250000 + 543505640 + 273558.87 * 10810 + 1000 * 10840 + 5000000
    assert j["total_turnover"] == pytest.approx(expected, rel=1e-6)
    assert sum(r["share_pct"] for r in j["regions"]) == pytest.approx(100, abs=0.1)
    usd = (await client.get(f"{API}/analytics/summary", params={"currency": "USD", "year": 2022})).json()
    assert usd["currency"] == "USD" and usd["monthly"] and usd["deals_count"] == 4
    assert (await client.get(f"{API}/analytics/summary", params={"currency": "EUR"})).status_code == 422


async def test_meta_filters(client):
    j = (await client.get(f"{API}/meta/filters")).json()
    assert "Исполнен" in j["statuses"] and "Toshkent viloyati" in j["regions"]
    assert j["years"] == [2022, 2023]


async def test_export_csv_xlsx(client):
    r = await client.get(f"{API}/export/deals", params={"format": "csv", "status": "Исполнен"})
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0][0] == "deal_no" and len(rows) == 2 and rows[1][0] == "1000"
    r = await client.get(f"{API}/deals", params={"export": "xlsx"})
    assert r.status_code == 200 and r.content[:2] == b"PK"
    from openpyxl import load_workbook

    ws = load_workbook(io.BytesIO(r.content)).active
    assert ws.max_row == 6


async def test_export_rate_limited_and_capped(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "export_max_rows", 2)
    r = await client.get(f"{API}/export/deals")
    assert len(list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))) == 3  # header + 2
    codes = [(await client.get(f"{API}/export/deals")).status_code for _ in range(12)]
    assert 429 in codes


async def test_writes_and_admin_require_auth(client):
    assert (await client.post(f"{API}/admin/import")).status_code == 401
    assert (await client.post(f"{API}/deals", json={})).status_code in (401, 422)
    assert (await client.post(f"{API}/ai/chat", json={"message": "x"})).status_code in (401, 403)


async def test_cors_and_validation(client):
    r = await client.options(
        f"{API}/deals",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
    r = await client.get(f"{API}/deals", params={"limit": 100000})
    assert r.status_code == 422


async def test_cyrillic_search_case_insensitive(client):
    for term in ("КАТОД", "катод", "Катод"):
        r = await client.get(f"{API}/deals", params={"search": term})
        assert {d["deal_no"] for d in r.json()["items"]} == {1002, 1003}
