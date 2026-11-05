# Architecture — UZEX AI Backend

## Pattern

Modular Monolith with clear separation of concerns:
`api` → `services` → `crud` → `db models` → PostgreSQL.

Cross-cutting concerns (config, security, logging, cache) live in `core/`.
The AI engine lives in `app/ai/` and depends only on the read-only DB session and tool registry.

## Layers

1. **API layer** (`app/api/v1/endpoints/`) — FastAPI route handlers, pagination, filtering,
   sorting, validation, consistent error responses, auth dependencies.
2. **Services layer** (`app/services/`) — business logic: CSV import, calculations,
   statistics, auth, evaluation.
3. **CRUD layer** (`app/crud/`) — generic + model-specific async CRUD operations.
4. **DB layer** (`app/db/`) — SQLAlchemy 2.0 async models, session/engine, base.

## Concurrency

All DB access is async (SQLAlchemy 2.0 + asyncpg for PostgreSQL; aiosqlite for SQLite).
`get_session()` yields a read/write session; `get_read_session()` yields the session used
by AI tools (read-only analytical queries).

## Dependencies direction

```
endpoints → deps/services → crud → models → database
ai/engine → ai/tools → read DB session (read-only)
```

The AI engine never imports write services; it only queries through read-only tools.

## Configuration

Pydantic Settings (`app/core/config.py`) reads `.env` and environment variables. Secrets
(`SECRET_KEY`, `DATABASE_URL`, `OPENAI_API_KEY`, etc.) must never be committed.
