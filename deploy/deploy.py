"""Deploy the hackathon app (FastAPI backend + Next.js static export + aiogram bot) to the VPS.

Auth: password over paramiko, from env VPS_HOST / VPS_PASSWORD (optional VPS_USER, default root).
Nothing is hardcoded, no SSH keys are installed.

    python deploy/deploy.py push            # default: sync backend+frontend+bot code, deps, restart
    python deploy/deploy.py push --no-build # skip `npm run build`
    python deploy/deploy.py setup           # first-time: packages, user uzex, python 3.12 venv, units
    python deploy/deploy.py env             # upload backend/.env and bot/.env (rewritten for server paths)
    python deploy/deploy.py db              # upload a consistent SQLite snapshot (+ agent cache)
    python deploy/deploy.py nginx           # nginx site + certbot for DOMAIN
    python deploy/deploy.py bot-start       # enable+start server bot (stop other pollers first!)
    python deploy/deploy.py status          # service status + last logs
"""
from __future__ import annotations

import argparse
import gzip
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from remote import connect, put, run  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
APP = "/opt/uzex"
USER = "uzex"
DOMAIN = os.environ.get("DEPLOY_DOMAIN", "45-92-173-47.sslip.io")
EXCLUDE_DIRS = {".venv", "__pycache__", "tests", ".pytest_cache", ".ruff_cache", ".gstack", ".mypy_cache", "node_modules"}
EXCLUDE_SUFFIX = (".db", ".db-shm", ".db-wal", ".sqlite", ".log", ".pyc")


def _filter(ti: tarfile.TarInfo):
    name = Path(ti.name)
    parts = set(name.parts)
    if parts & EXCLUDE_DIRS or name.name in {".env"} or name.name.endswith(EXCLUDE_SUFFIX):
        return None
    if any(p.startswith("C:") for p in name.parts):  # stray Windows-path dirs
        return None
    return ti


def _tar(src: Path, arcname: str, out: Path) -> Path:
    with tarfile.open(out, "w:gz") as t:
        t.add(src, arcname=arcname, filter=_filter)
    return out


def _sh(c, cmd, check=True):
    return run(c, cmd, check=check)


UNIT_BACKEND = f"""[Unit]
Description=UZEX backend (FastAPI)
After=network.target

[Service]
User={USER}
WorkingDirectory={APP}/backend
EnvironmentFile={APP}/backend/.env
Environment=FRONTEND_DIST={APP}/frontend/out
Environment=AGENT_CACHE_PATH={APP}/data/agent_cache.sqlite
ExecStart={APP}/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
"""

UNIT_BOT = f"""[Unit]
Description=UZEX Telegram bot (@tiu_uzex_ai)
After=network.target uzex-backend.service

[Service]
User={USER}
WorkingDirectory={APP}/bot
EnvironmentFile={APP}/bot/.env
Environment=BACKEND_URL=http://127.0.0.1:8000/api/v1
Environment=WEBAPP_URL=https://{DOMAIN}/
Environment=WEBAPP_URL_FILE={APP}/run/webapp_url.txt
ExecStart={APP}/venv/bin/python -m app.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

NGINX_SITE = f"""server {{
    listen 80;
    listen [::]:80;
    server_name {DOMAIN};
    client_max_body_size 20m;
    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml;
    location / {{
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }}
}}
"""


def write_remote(c, path: str, content: str, mode: str = "644", owner: str = "root") -> None:
    with tempfile.NamedTemporaryFile("w", delete=False, newline="\n", encoding="utf-8") as f:
        f.write(content)
    try:
        put(c, f.name, path)
    finally:
        os.unlink(f.name)
    _sh(c, f"chmod {mode} {path} && chown {owner}:{owner} {path}")


def setup(c) -> None:
    _sh(c, "export DEBIAN_FRONTEND=noninteractive; "
           # policy-rc.d: don't auto-start nginx on install (ports may still be busy)
           "printf '#!/bin/sh\\nexit 101\\n' > /usr/sbin/policy-rc.d && chmod +x /usr/sbin/policy-rc.d; "
           "apt-get update -qq && apt-get install -y -qq nginx certbot python3-certbot-nginx curl rsync >/dev/null; "
           "rm -f /usr/sbin/policy-rc.d; rm -f /etc/nginx/sites-enabled/default")
    _sh(c, f"id {USER} >/dev/null 2>&1 || useradd --system --create-home --home-dir {APP} --shell /usr/sbin/nologin {USER}; "
           f"mkdir -p {APP}/backend {APP}/bot {APP}/frontend {APP}/data {APP}/run && chown -R {USER}:{USER} {APP}")
    # Python >=3.12 is required; Ubuntu 22.04 ships 3.10 -> use uv-managed CPython 3.12.
    _sh(c, f"test -x /usr/local/bin/uv || (curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin INSTALLER_NO_MODIFY_PATH=1 sh >/dev/null); "
           f"cd {APP}; test -x {APP}/venv/bin/python || sudo -u {USER} env HOME={APP} UV_PYTHON_INSTALL_DIR={APP}/.python /usr/local/bin/uv venv --python 3.12 {APP}/venv; "
           f"{APP}/venv/bin/python --version")
    write_remote(c, "/etc/systemd/system/uzex-backend.service", UNIT_BACKEND)
    write_remote(c, "/etc/systemd/system/uzex-bot.service", UNIT_BOT)
    _sh(c, "systemctl daemon-reload")


def push_env(c) -> None:
    for comp in ("backend", "bot"):
        put(c, str(ROOT / comp / ".env"), f"{APP}/{comp}/.env")
        _sh(c, f"chown {USER}:{USER} {APP}/{comp}/.env && chmod 600 {APP}/{comp}/.env")
    db = f"sqlite+aiosqlite:///{APP}/data/birja.db"
    seds = [
        f"s#^DATABASE_URL=.*#DATABASE_URL={db}#",
        "s#^APP_ENV=.*#APP_ENV=production#",
        f"s#^BACKEND_CORS_ORIGINS=.*#BACKEND_CORS_ORIGINS=https://{DOMAIN}#",
        f"s#^DATA_DIR=.*#DATA_DIR={APP}/data#",
        "s#^HOST=.*#HOST=127.0.0.1#",
    ]
    _sh(c, "sed -i " + " ".join(f"-e '{s}'" for s in seds) + f" {APP}/backend/.env")
    _sh(c, f"sed -i -e 's#^BACKEND_URL=.*#BACKEND_URL=http://127.0.0.1:8000/api/v1#' {APP}/bot/.env; "
           f"grep -q '^WEBAPP_URL=' {APP}/bot/.env && sed -i 's#^WEBAPP_URL=.*#WEBAPP_URL=https://{DOMAIN}/#' {APP}/bot/.env || echo 'WEBAPP_URL=https://{DOMAIN}/' >> {APP}/bot/.env")


def push_db(c) -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        url = next(l.split("=", 1)[1].strip() for l in (ROOT / "backend/.env").read_text().splitlines() if l.startswith("DATABASE_URL="))
        src_path = (ROOT / "backend" / url.split("///", 1)[1]).resolve()
        for name, src in (("birja.db", src_path), ("agent_cache.sqlite", ROOT / "backend/agent_cache.sqlite")):
            if not src.exists():
                continue
            s, d = sqlite3.connect(src), sqlite3.connect(tmp / name)
            s.backup(d); d.close(); s.close()
            with open(tmp / name, "rb") as i, gzip.open(tmp / f"{name}.gz", "wb", 6) as o:
                shutil.copyfileobj(i, o)
            put(c, str(tmp / f"{name}.gz"), f"/tmp/{name}.gz")
            _sh(c, f"systemctl stop uzex-backend 2>/dev/null; gunzip -c /tmp/{name}.gz > {APP}/data/{name} && rm -f /tmp/{name}.gz "
                   f"{APP}/data/{name}-wal {APP}/data/{name}-shm && chown {USER}:{USER} {APP}/data/{name}")
            print(f"uploaded {name}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def push(c, build: bool = True) -> None:
    if build:
        subprocess.run("npm run build", cwd=ROOT / "frontend", shell=True, check=True)
    tmp = Path(tempfile.mkdtemp())
    try:
        for comp, src in (("backend", ROOT / "backend"), ("bot", ROOT / "bot"), ("out", ROOT / "frontend" / "out")):
            tgz = _tar(src, comp, tmp / f"{comp}.tgz")
            put(c, str(tgz), f"/tmp/uzex_{comp}.tgz")
        # replace code but keep .env; frontend/out swapped atomically
        _sh(c, f"set -e; cd /tmp; for comp in backend bot; do rm -rf /tmp/uzex_$comp && mkdir /tmp/uzex_$comp && tar xzf uzex_$comp.tgz -C /tmp/uzex_$comp; "
               f"rsync -a --delete --exclude .env /tmp/uzex_$comp/$comp/ {APP}/$comp/; done; "
               f"rm -rf {APP}/frontend/out.new && mkdir -p {APP}/frontend/out.new && tar xzf uzex_out.tgz -C {APP}/frontend/out.new --strip-components=1; "
               f"rm -rf {APP}/frontend/out.old; [ -d {APP}/frontend/out ] && mv {APP}/frontend/out {APP}/frontend/out.old || true; mv {APP}/frontend/out.new {APP}/frontend/out; rm -rf {APP}/frontend/out.old; "
               f"rm -rf /tmp/uzex_*; chown -R {USER}:{USER} {APP}/backend {APP}/bot {APP}/frontend")
        _sh(c, f"cd {APP} && sudo -u {USER} env HOME={APP} /usr/local/bin/uv pip install -q --python {APP}/venv/bin/python -r {APP}/backend/requirements.txt aiogram'>=3.13,<4' 'httpx>=0.27' python-dotenv")
        # The bot is (re)started only if it was already enabled: only ONE process may poll the token (see `bot-start`).
        _sh(c, "systemctl enable -q uzex-backend; systemctl restart uzex-backend; sleep 8; "
               "if systemctl is-enabled -q uzex-bot; then systemctl restart uzex-bot; fi; sleep 3; "
               "systemctl is-active uzex-backend uzex-bot; curl -s -m10 -o /dev/null -w 'health %{http_code}\\n' http://127.0.0.1:8000/health", check=False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def nginx(c) -> None:
    write_remote(c, f"/etc/nginx/sites-available/uzex", NGINX_SITE)
    _sh(c, "ln -sf /etc/nginx/sites-available/uzex /etc/nginx/sites-enabled/uzex && nginx -t && systemctl enable -q nginx && (systemctl reload nginx || systemctl restart nginx)")
    _sh(c, f"certbot --nginx -d {DOMAIN} --non-interactive --agree-tos --register-unsafely-without-email --redirect && nginx -t && systemctl reload nginx")


def bot_start(c) -> None:
    """Enable + start the server bot. Stop any other poller (e.g. the local PC bot) FIRST."""
    _sh(c, "systemctl enable -q uzex-bot && systemctl restart uzex-bot; sleep 8; systemctl is-active uzex-bot; "
           "journalctl -u uzex-bot -n 20 --no-pager", check=False)


def status(c) -> None:
    _sh(c, "systemctl is-active nginx uzex-backend uzex-bot; free -m; journalctl -u uzex-backend -n 15 --no-pager; journalctl -u uzex-bot -n 15 --no-pager", check=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="push", choices=["setup", "env", "db", "push", "nginx", "bot-start", "status"])
    ap.add_argument("--no-build", action="store_true")
    a = ap.parse_args()
    c = connect()
    try:
        {"setup": setup, "env": push_env, "db": push_db, "nginx": nginx, "bot-start": bot_start, "status": status}.get(a.cmd, lambda c: push(c, not a.no_build))(c)
    finally:
        c.close()


if __name__ == "__main__":
    main()
