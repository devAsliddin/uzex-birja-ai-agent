# Starts the Birja Reyestri API on http://127.0.0.1:8000 (local SQLite, no Docker).
$ErrorActionPreference = "Stop"
$backend = Join-Path $PSScriptRoot "backend"
Set-Location $backend
if (-not (Test-Path ".venv\Scripts\Activate.ps1")) {
    Write-Host "Creating .venv and installing dependencies..."
    python -m venv .venv
    & .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt
}
. .\.venv\Scripts\Activate.ps1
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env"; Write-Host "Created .env from .env.example - set SECRET_KEY and ADMIN_PASSWORD." }
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
