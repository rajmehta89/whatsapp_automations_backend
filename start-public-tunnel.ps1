$ErrorActionPreference = "Stop"

$cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cloudflared) {
    throw "cloudflared is not installed or not on PATH. Install it first, then run this script again."
}

Write-Host "Starting Cloudflare tunnel for http://127.0.0.1:5050 ..."
cloudflared tunnel --url http://127.0.0.1:5050
