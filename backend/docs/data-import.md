# Data Import documentation

## Source files (UTF-8 CSV, comma-delimited, never modified)

- `deals_2022.csv` … `deals_2026.csv` — deals (~500 000 total)
- `contracts.csv` — contract cards (~6 616)
- `participants.csv` — companies (~14 392)
- `brokers.csv` — brokerages (~120)
- `usd_rates.csv` — daily USD rate (~1 765)

## Import service (`app/services/import_service.py`)

- Reads CSV with `utf-8` encoding.
- Validates header structure (required columns) per file.
- Parses numbers with spaces as thousands separators and dot as decimal.
- Parses dates `DD.MM.YYYY`, times `HH:MM:SS`.
- Validates each required field; invalid rows are counted and reported (never invented).
- Detects duplicates by natural key and skips them (repeatable, no duplication).
- Upsert semantics: re-import updates changed fields, skips unchanged.
- Historical deal values are never automatically changed.
- Transactional batch inserts (commit every `IMPORT_BATCH_SIZE`, default 5000).
- Full report: total/inserted/updated/skipped/invalid + per-row errors + file errors.

## Order

brokers → participants → usd_rates → contracts → deals (dependency order).

## Endpoint

`POST /api/v1/admin/import` (admin only) imports all files.
`POST /api/v1/admin/import/{file}` imports a single file.
