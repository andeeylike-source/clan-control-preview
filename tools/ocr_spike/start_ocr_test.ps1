$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..\..")
Set-Location $repoRoot

$env:OCR_SPACE_API_KEY = "K83212585088957"
$env:OCR_BACKEND_PORT = "8787"

$htmlUri = "http://localhost:8787/ocr_backend_test.html"

Write-Host "Starting local OCR proxy on http://localhost:8787/ocr-read"
Write-Host "Opening OCR backend test page..."
Start-Sleep -Milliseconds 500
Start-Process $htmlUri

node "tools\ocr_spike\ocr_backend_proxy.js"
