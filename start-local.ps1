$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$venvPath = Join-Path $projectRoot ".venv"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"
$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"

if (-not (Test-Path $venvPath)) {
    Write-Host "Creating local virtual environment..."
    python -m venv .venv
}

if (-not (Test-Path $pythonExe)) {
    throw "Python executable was not found in .venv. Delete .venv and run again."
}

Write-Host "Activating local virtual environment..."
. $activateScript

Write-Host "Installing backend dependencies..."
& $pythonExe -m pip install -r requirements.txt

if (-not $env:WORKSPACE_AUTH_EMAIL) {
    $env:WORKSPACE_AUTH_EMAIL = "rajm267747@gmail.com"
}

if (-not $env:WORKSPACE_AUTH_PASSWORD) {
    $env:WORKSPACE_AUTH_PASSWORD = "WhatsAppTest"
}

if (-not $env:PUBLIC_BACKEND_URL) {
    $env:PUBLIC_BACKEND_URL = "http://127.0.0.1:5050"
}

Write-Host ""
Write-Host "Local backend starting at http://127.0.0.1:5050"
Write-Host "Login: $env:WORKSPACE_AUTH_EMAIL / $env:WORKSPACE_AUTH_PASSWORD"
Write-Host ""

& $pythonExe dashboard.py
