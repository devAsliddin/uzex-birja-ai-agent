# Database documentation

## Target

PostgreSQL (asyncpg) is the production target. SQLite (`aiosqlite`) is used for local
development and tests when PostgreSQL is unavailable.

## Tables

Core (from source CSV data, original values preserved):

- `brokers` — code (PK), name, inn, region
- `participants` — inn (PK), name, region, activity, role, vat_payer
- `usd_rates` — date (PK), rate (UZS per 1 USD)
- `contracts` — contract_number (PK), product attributes, currency, dates, seller FK
- `deals` — deal_number (PK), dates, quantity, amount, FKs to contracts/participants/brokers,
  delivered_quantity

Computed deal properties (not persisted): `volume = quantity * lot_size`,
`unit_price = amount / volume`.

Backend tables:

- `users`, `api_keys` — authentication
- `conversations`, `messages` — AI chat history
- `prompt_versions` — versioned system prompt (active version used by AI engine)
- `evaluation_datasets`, `evaluation_questions`, `evaluation_runs`, `evaluation_results`
- `audit_logs` — immutable security audit trail

## Migrations

Alembic. Generate: `alembic revision --autogenerate -m "message"`. Apply:
`alembic upgrade head`.

## Indexes & constraints

- Primary keys on all tables; foreign keys with `onupdate/ondelete` defaults.
- `users.email`, `users.username` unique + indexed.
- Foreign keys: deals → contracts/participants/brokers; contracts → participants.

## AI read-only user

Production: AI tools connect via a dedicated PostgreSQL user (`uzex_ai_reader`) with
read-only grants. Configured via `AI_READ_DATABASE_URL` (falls back to `DATABASE_URL`).
