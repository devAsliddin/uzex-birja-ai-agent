# Birja reyestri - backend (FastAPI + SQLAlchemy async)

Commodity exchange deals and brokers registry (500k deals). Local, no Docker: SQLite (WAL) by default,
PostgreSQL via `DATABASE_URL=postgresql+asyncpg://...` (code is dialect-neutral; Postgres path not run here).

## Run (from project root)
    .\run_backend.ps1        # venv, alembic upgrade head, uvicorn on http://127.0.0.1:8000
    .\import_data.ps1        # imports .\data\*.csv (idempotent, ~3 min for 500k deals on SQLite)

Manual: `python -m venv .venv; .venv\Scripts\pip install -r requirements-dev.txt; copy .env.example .env`
(set SECRET_KEY, ADMIN_PASSWORD), `alembic upgrade head`, `python -m app.cli_import`,
`uvicorn app.main:app --host 127.0.0.1 --port 8000`. Docs: /docs. Tests: `pytest` (fixture CSVs in tests/fixtures), `ruff check .`.

## API
See `../API_CONTRACT.md`. Public read-only: /brokers, /brokers/{code}, /deals, /deals/{deal_no},
/analytics/summary, /export/deals, /meta/filters. Auth required: writes, /admin/*, /ai/*, /statistics/*, /contracts, /participants.

## Design notes
- Core tables follow TZ section 3 exactly (columns, CHECKs, FKs, 4 indexes) - migration `alembic/versions/0001_initial_schema.py`.
- ETL: brokers+participants+usd_rates -> contracts -> deals_2022..2026, batched executemany, idempotent (existing PKs skipped).
- USD contracts: `amount_uzs` is computed in SQL from usd_rates on the deal date (nearest previous day fallback), not stored.
- Regions: stored as-is; `app/core/regions.py` maps Russian/Latin spellings to one Uzbek Latin key.
- Analytics/broker rating/meta are cached (TTL 10 min) and pre-warmed at startup. Export is streamed, capped by EXPORT_MAX_ROWS, rate-limited.
