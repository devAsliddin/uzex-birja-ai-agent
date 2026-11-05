# API contract - Birja reyestri backend

Base URL: `http://127.0.0.1:8000/api/v1` (CORS: `http://localhost:3000`, `http://127.0.0.1:3000`).
All endpoints below are **public, read-only (no login)**. Swagger: `http://127.0.0.1:8000/docs`.
Errors: `{"error": "...", "code": "not_found|validation_error|rate_limit_exceeded|internal_error", "status_code": 404}`
(FastAPI validation errors are the standard `422 {"detail": [...]}`).
Money values are JSON numbers (float). Dates are ISO `YYYY-MM-DD`, times `HH:MM:SS`.
Amount/`turnover` are in UZS unless `currency=USD` is requested (analytics only).
USD contracts: `amount` is in USD, `amount_uzs` = amount x rate on deal date.

## Region naming
Deals/brokers/participants store Uzbek Latin ("Toshkent viloyati"); contracts store Russian ("Ташкентская область").
Every response that has `region` also has `region_key` = canonical Uzbek Latin name. The `region` filter accepts
either spelling. `GET /meta/filters` -> `region_labels_ru` maps key -> Russian label.

## GET /meta/filters
```json
{"statuses": ["Аннулирован(Не оплачен)","Ждёт оплату","Заключен","Исполнен","Исполнен(Частично)","Не подписан","Новый","Оплачен"],
 "regions": ["Andijon viloyati", "..."], "broker_regions": ["..."],
 "region_labels_ru": {"Toshkent shahri": "г. Ташкент", "...": "..."},
 "trade_types": ["Английский аукцион","Двусторонний аукцион","Обратный аукцион"],
 "years": [2022,2023,2024,2025,2026]}
```

## GET /brokers?page=1&limit=50&region=&search=&sort=rating|name|deals|turnover
`limit` max 200 (120 brokers total). `search` matches code, name or INN (case-insensitive).
```json
{"items": [{"broker_code":"BK111","name":"\"Gucham Broker\" MChJ","inn":"971147570","region":"Sirdaryo viloyati",
            "region_key":"Sirdaryo viloyati","deals_count":32422,"turnover_uzs":21947463403115.18,"rating":1}],
 "total":120,"page":1,"limit":50,"pages":3}
```
`rating` = rank by turnover (1 = highest). Turnover/deal count count a deal once for each broker on either side.

## GET /brokers/{code}   (e.g. BK001; 404 if unknown)
```json
{"broker_code":"BK001","name":"...","inn":"...","region":"...","region_key":"...",
 "rating":{"rank":61,"of":120},
 "stats":{"deals_count":4348,"deals_as_seller_broker":2320,"deals_as_buyer_broker":2038,
          "turnover_uzs":4649534216449.88,"avg_deal_uzs":1069350095.78,
          "by_status":[{"status":"Исполнен","deals_count":3854,"turnover_uzs":4060946888556.41}]}}
```

## GET /deals
Query: `start_date`, `end_date` (YYYY-MM-DD, inclusive), `status` (repeat param or comma list:
`?status=Оплачен&status=Новый`), `broker` (code; matches seller OR buyer broker), `region`, `search`
(product name substring, or exact deal number), `seller_inn`, `buyer_inn`, `contract_no`,
`sort=deal_date|deal_no|amount|quantity|status` (default `deal_date`), `order=asc|desc` (default desc),
`page` (>=1), `limit` (1..500, default 50), `export=csv|xlsx` (returns a file instead of JSON),
`with_status_counts=true` (adds `status_counts: {status: n}` computed for the current filters EXCLUDING the status filter; ~100 ms).
```json
{"items":[{"deal_no":604082,"deal_date":"2026-10-30","deal_time":"10:44:07","trade_type":"Английский аукцион",
  "quantity":10,"amount":1192369.5,"currency":"Узбекский сум","amount_uzs":1192369.5,"start_price":6658.98,
  "contract_no":"100034","product_name":"...","lot_size":1.0,"unit":"тонна","region":"Toshkent viloyati",
  "region_key":"Toshkent viloyati","contract_type":"Внутренний","contract_form":"Спот","status":"Исполнен",
  "seller_inn":"...","seller_name":"...","buyer_inn":"...","buyer_name":"...","seller_broker":"BK082","buyer_broker":"BK072",
  "payment_date":null,"delivery_date":null,"delivered_lots":null}],
 "total":183605,"page":1,"limit":50,"pages":3673,
 "status_counts":{"Исполнен":178679,"Оплачен":5854}}  // status_counts only with with_status_counts=true
```
`currency` is `"Узбекский сум"` or `"Доллар США"`; `payment_date`, `delivery_date`, `delivered_lots` may be null.

## GET /deals/{deal_no}   (404 if unknown)
Flat deal fields as above plus `volume` (quantity x lot), `usd_rate`
(`{"requested_date","rate_date","rate","exact"}`; nearest previous day if the exact day is missing) and nested objects:
`contract` (full contract card incl. `tn_ved_code, product_group, product_category, industry, base_price,
deposit_percent, delivery_basis, packaging, warehouse_address, payment_term_days, delivery_term_days,
registration_date, valid_until, ...`), `seller` / `buyer`
(`{inn,name,region,activity,role,vat_payer(bool)}`), `seller_broker` / `buyer_broker` (`{code,name,inn,region}`; may be null).

## GET /analytics/summary?year=&currency=UZS|USD
Cached server-side (10 min). `year` omitted = all years. `yearly` always lists all years; `monthly` only if `year` given.
```json
{"year":null,"currency":"UZS","total_turnover":220477157554431.75,"deals_count":500000,"broker_count":120,
 "usd_rate":{"date":"2026-10-31","rate":13357.84},
 "status_counts":{"Исполнен":431061,"Оплачен":5854},  // for the selected year (all years if omitted)
 "yearly":[{"year":2022,"deals_count":84299,"turnover":29934581605629.86}],
 "monthly":[{"month":1,"deals_count":7049,"turnover":632794999.57}],
 "regions":[{"region":"Toshkent shahri","region_ru":"г. Ташкент","deals_count":24478,"turnover":861471190.05,"share_pct":19.07}],
 "top_categories":[{"category":"Металлопродукция","deals_count":18597,"turnover":479835896.32}]}
```
**Turnover basis:** `total_turnover`, `yearly[].turnover`, `monthly[].turnover`, `regions[].turnover/share_pct`,
`top_categories[].turnover` and broker `turnover_uzs` EXCLUDE status `Аннулирован(Не оплачен)` (the deal did not happen).
Deal counts (`deals_count`, `deals_count` per year/region/broker, `status_counts`) include ALL deals; the response also has
`annulled_deals_count` and `turnover_basis` (text). Broker rating ranks by this executed turnover. In `/brokers/{code}`
`stats.by_status[]` shows `turnover_uzs = 0` for the annulled status. `/deals` rows still show each deal's own `amount`.
Search (`/deals?search=`): case-insensitive for Cyrillic and Latin on product name, or exact deal number.

## GET /export/deals?format=csv|xlsx&<same filters as /deals>
Streams a file (`Content-Disposition: attachment; filename="deals_YYYY-MM-DD.csv"`), max 500 000 rows,
rate limit 10 requests/min/IP (429 beyond). CSV is UTF-8 with BOM. Columns: `deal_no, deal_date, deal_time,
trade_type, quantity, amount, currency, amount_uzs, start_price, contract_no, product_name, lot_size, unit, region,
contract_type, contract_form, status, seller_inn, seller_name, buyer_inn, buyer_name, seller_broker, buyer_broker,
payment_date, delivery_date, delivered_lots`. Same file via `GET /deals?export=xlsx&...`.
Tip: build the download link as a plain `<a href>`; do not fetch it into memory for large ranges.

## GET /health  (root, not under /api/v1)
`{"status":"ok","database":"ok",...}`

## Measured (SQLite, 500k deals, real dataset)
(real dataset: 8 statuses) /deals first page ~15-30 ms, filtered ~20-60 ms, page 5000 ~0.4 s; /brokers, /meta, /analytics/summary are pre-warmed
at startup (cold ~1.5-2.5 s, cached ~2 ms); CSV export of 500k rows ~30 s.
