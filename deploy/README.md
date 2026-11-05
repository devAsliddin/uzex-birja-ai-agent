# Deploy to VPS

Target: `https://45-92-173-47.sslip.io/` — nginx (TLS, certbot) -> uvicorn `127.0.0.1:8000`
(FastAPI serves `/api/v1`, `/docs`, `/health` and the Next.js static export at `/`).
App lives in `/opt/uzex` (user `uzex`), Python 3.12 venv via uv (Ubuntu 22.04 ships 3.10).

Services: `uzex-backend`, `uzex-bot` (systemd, `Restart=always`), `nginx`.

## Credentials

Password auth via paramiko, read from env only (no SSH keys installed, nothing hardcoded):

```powershell
$env:VPS_HOST = "45.92.173.47"; $env:VPS_PASSWORD = "<password>"   # VPS_USER defaults to root
```

## Usual update (code changed)

```powershell
python deploy/deploy.py push             # npm run build + sync backend/bot/frontend out + pip + restart
python deploy/deploy.py push --no-build  # backend/bot only changed (fast, ~30 s)
python deploy/deploy.py status           # is-active, memory, last logs
```

`push` keeps the server `.env` files; excludes `.venv`, `.env`, `*.db`, `*.sqlite`, logs, tests, caches.
It restarts `uzex-bot` only if it is already enabled.

## First-time / rare

```powershell
python deploy/deploy.py setup      # nginx, certbot, user uzex, uv + venv, systemd units
python deploy/deploy.py env        # upload backend/.env + bot/.env (chmod 600), rewrite paths/URLs
python deploy/deploy.py db         # consistent sqlite3 backup -> gzip -> upload (+ agent_cache.sqlite)
python deploy/deploy.py nginx      # nginx site + certbot --nginx --redirect
python deploy/deploy.py bot-start  # enable + start server bot
```

**Bot:** only ONE process may poll the token. Stop the local bot (`python ... hakaton\bot`) before
`bot-start`, or Telegram returns `Conflict: terminated by other getUpdates request`.

## Rollback (ports 80/443 back to contentflow / postix.uz)

See `/root/contentflow_backup_*/ROLLBACK.md` on the server:

```bash
systemctl stop nginx && systemctl disable nginx && docker start contentflow_nginx
docker update --restart=unless-stopped contentflow_nginx
```
