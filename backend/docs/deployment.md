# Deployment documentation

## Production checklist

1. Install PostgreSQL and Redis.
2. Copy `.env.example` to `.env` and set real values:
   - `DATABASE_URL=postgresql+asyncpg://USER:PASS@HOST:PORT/DB`
   - `ALEMBIC_DATABASE_URL=postgresql+psycopg2://USER:PASS@HOST:PORT/DB`
   - `REDIS_URL=redis://HOST:PORT/0`
   - `SECRET_KEY=<strong random>`
   - `AI_PROVIDER=openai|anthropic|ollama` (or `mock` for offline)
   - Provider API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`)
   - `ADMIN_EMAIL`, `ADMIN_PASSWORD`
3. `pip install -r requirements.txt`
4. `python -m alembic upgrade head`
5. Start: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
   (use a process manager / systemd or Docker in production).

## Security

- Never commit `.env` with real secrets.
- JWT `SECRET_KEY` must be strong and random.
- Admin endpoints require `admin` role / superuser.
- AI tools use read-only DB access (`AI_READ_DATABASE_URL`, dedicated reader user).
- Rate limiting, CORS, and audit logging are configured.

## Running behind a proxy

Terminate TLS at the reverse proxy (nginx/ALB). Set `backend_cors_origins` to your
allowed origins. The app itself serves OpenAPI at `/docs` and `/api/v1/openapi.json`.
