# Testing documentation

## Framework

pytest + pytest-asyncio. Async fixtures in `tests/conftest.py` use a throwaway SQLite
test database (`test_uzex_ai.db`) created/dropped per session.

## Run

```bash
cd backend
pytest tests/
```

## Coverage areas

- unit: calculations, security (password/JWT)
- import: all CSV files, repeatability/no-duplication, missing file
- AI tools: registry, search/details tools, exchange rate (available/missing),
  calculations, volume guard
- API: health, auth, deals list (200/401)
- Edge cases: empty DB, missing currency rate, missing record, invalid CSV

## Quality tooling

- ruff (lint) — `ruff check app tests`
- mypy (static types) — `mypy app`

## Notes

Tests never use production data destructively. The test DB is a scratch SQLite file.
