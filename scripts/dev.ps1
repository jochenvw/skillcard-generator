#!/usr/bin/env pwsh
# Dev startup script — builds frontend and starts the backend with uv.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Push-Location $root
try {
    # 1. Sync Python dependencies
    Write-Host "==> Syncing Python dependencies..." -ForegroundColor Cyan
    uv sync
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }

    # 2. Build React frontend
    Write-Host "==> Building frontend..." -ForegroundColor Cyan
    Push-Location frontend
    if (-not (Test-Path node_modules)) {
        npm install
        if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
    }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "frontend build failed" }
    Pop-Location

    # 3. Start the backend
    Write-Host "==> Starting Profile Agent on http://localhost:8000" -ForegroundColor Green
    uv run python -m profile_agent
}
finally {
    Pop-Location
}
