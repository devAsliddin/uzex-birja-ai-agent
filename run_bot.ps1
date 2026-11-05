# Starts the "Birja reyestri" Telegram bot (bot\). Usage:  powershell -ExecutionPolicy Bypass -File .\run_bot.ps1
# Optional: -Test  -> runs smoke + stress tests instead of starting the bot.
param([switch]$Test)

$ErrorActionPreference = "Stop"
$BotDir = Join-Path $PSScriptRoot "bot"
$Py = Join-Path $BotDir ".venv\Scripts\python.exe"

if (-not (Test-Path $Py)) {
    Write-Host "Creating bot\.venv ..."
    & py -3 -m venv (Join-Path $BotDir ".venv")
    & $Py -m pip install -q -r (Join-Path $BotDir "requirements.txt")
}

Set-Location $BotDir

if ($Test) {
    & $Py -m pytest -q -s
    exit $LASTEXITCODE
}

if (-not (Test-Path (Join-Path $BotDir ".env"))) {
    Write-Host "bot\.env topilmadi. bot\.env.example dan nusxa oling va BOT_TOKEN, ALLOWED_CHAT_IDS ni to'ldiring."
    exit 2
}

& $Py -m app.main
exit $LASTEXITCODE
