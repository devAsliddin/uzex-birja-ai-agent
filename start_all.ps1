# Idempotently starts the Birja Reyestri stack as hidden background processes:
#   - backend (FastAPI + static dashboard) on http://127.0.0.1:8000  -> run\backend.log / run\backend.err.log
#   - Telegram bot (bot\)                                             -> run\bot.log / run\bot.err.log
# Safe to run repeatedly: nothing is started twice. Binds to 127.0.0.1 only; no tunnel is opened.
# Never touches C:\Users\f1n\claude-remote-bot.
# Usage:  powershell -ExecutionPolicy Bypass -File .\start_all.ps1
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$RunDir = Join-Path $Root "run"
New-Item -ItemType Directory -Force $RunDir | Out-Null

# Single-instance guard (two concurrent start_all runs must not both start things).
$mutex = New-Object System.Threading.Mutex($false, "Global\BirjaReyestriStartAll")
if (-not $mutex.WaitOne(0)) { Write-Host "start_all.ps1 is already running - exiting."; exit 0 }

function Test-Backend {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "http://127.0.0.1:8000/health"
        return $r.StatusCode -eq 200
    } catch { return $false }
}

function Get-ProjectProcess([string]$pattern) {
    Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='powershell.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine -like $pattern -and $_.CommandLine -notlike "*claude-remote-bot*" }
}

function Start-Hidden([string]$script, [string]$name) {
    $out = Join-Path $RunDir "$name.log"
    $err = Join-Path $RunDir "$name.err.log"
    $p = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -PassThru `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$(Join-Path $Root $script)`"") `
        -WorkingDirectory $Root -RedirectStandardOutput $out -RedirectStandardError $err
    Set-Content -Path (Join-Path $RunDir "$name.pid") -Value $p.Id
    Write-Host "$name started (pid $($p.Id)), logs: run\$name.log"
}

try {
    # ---- Backend ---------------------------------------------------------------------------
    $backendDir = Join-Path $Root "backend"
    if (Test-Backend) {
        Write-Host "backend: already answering on 127.0.0.1:8000/health - skip"
    } elseif (Get-ProjectProcess "*$backendDir*uvicorn*app.main:app*") {
        Write-Host "backend: uvicorn process exists but /health not answering yet (starting?) - skip"
    } elseif (Get-ProjectProcess "*run_backend.ps1*") {
        Write-Host "backend: run_backend.ps1 already running (migrations?) - skip"
    } else {
        Start-Hidden "run_backend.ps1" "backend"
        for ($i = 0; $i -lt 30 -and -not (Test-Backend); $i++) { Start-Sleep -Seconds 1 }
        if (Test-Backend) { Write-Host "backend: healthy" } else { Write-Host "backend: not healthy yet - see run\backend.err.log" }
    }

    # ---- Telegram bot ----------------------------------------------------------------------
    $botDir = Join-Path $Root "bot"
    if (Get-ProjectProcess "*$botDir\.venv*app.main*") {
        Write-Host "bot: already running - skip"
    } elseif (Get-ProjectProcess "*run_bot.ps1*") {
        Write-Host "bot: run_bot.ps1 already running - skip"
    } elseif (-not (Test-Path (Join-Path $botDir ".env"))) {
        Write-Host "bot: bot\.env missing - not started"
    } else {
        Start-Hidden "run_bot.ps1" "bot"
    }

    # ---- Tunnel (PLACEHOLDER - intentionally NOT executed) ---------------------------------
    # Exposing 127.0.0.1:8000 publicly (e.g. for the Telegram Mini App HTTPS URL) requires the
    # user's explicit decision. Nothing below runs. If approved, add ONE command here, e.g.:
    #   # cloudflared tunnel --url http://127.0.0.1:8000  > run\tunnel.log 2>&1
    # and keep the same "already running? -> skip" check as above.
    # -----------------------------------------------------------------------------------------
} finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
