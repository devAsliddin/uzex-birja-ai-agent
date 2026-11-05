# Imports the CSV files from .\data into the local database (idempotent; safe to re-run).
param([string]$DataDir = "")
$ErrorActionPreference = "Stop"
$backend = Join-Path $PSScriptRoot "backend"
Set-Location $backend
. .\.venv\Scripts\Activate.ps1
python -m alembic upgrade head
if ($DataDir -ne "") { python -m app.cli_import --data-dir $DataDir } else { python -m app.cli_import }
