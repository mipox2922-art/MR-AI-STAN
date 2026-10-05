$ErrorActionPreference = "Stop"

Write-Host "MR AI STAN Local Device Bridge"
Write-Host "============================="

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python is required."
}

if (-not (Get-Command adb -ErrorAction SilentlyContinue)) {
  Write-Warning "adb not found on PATH. Install Android SDK Platform Tools."
}

if (-not (Get-Command fastboot -ErrorAction SilentlyContinue)) {
  Write-Warning "fastboot not found on PATH. Install Android SDK Platform Tools."
}

Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
  python -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install -r requirements.txt

if (-not $env:MR_AI_BRIDGE_TOKEN) {
  $bytes = New-Object byte[] 32
  [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
  $env:MR_AI_BRIDGE_TOKEN = [Convert]::ToBase64String($bytes)
}

if (-not $env:MR_AI_WEB_ORIGIN) {
  $env:MR_AI_WEB_ORIGIN = "http://localhost:5173"
}

Write-Host ""
Write-Host "MR_AI_BRIDGE_TOKEN=$env:MR_AI_BRIDGE_TOKEN"
Write-Host "MR_AI_WEB_ORIGIN=$env:MR_AI_WEB_ORIGIN"
Write-Host "Bridge: http://127.0.0.1:8765"
Write-Host ""

& .\.venv\Scripts\python.exe bridge.py
