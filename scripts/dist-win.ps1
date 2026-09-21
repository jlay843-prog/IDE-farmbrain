# Unsigned Windows build wrapper. Signing stays off until Jeff flips package.json + cert env (see docs/CODE-SIGNING.md).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

try {
  $live = Invoke-RestMethod -Uri "http://127.0.0.1:43180/api/health" -TimeoutSec 2
  if ($live.ok) {
    Write-Host 'Forge desk is open on 43180 - close it before packaging if electron-builder reports EBUSY on dist\win-unpacked.'
  }
} catch {}

$env:CSC_IDENTITY_AUTO_DISCOVERY = "false"
if (-not $env:ELECTRON_BUILDER_CACHE) {
  $env:ELECTRON_BUILDER_CACHE = Join-Path $Root ".eb-cache"
}

# When cert is ready (PFX path): set CSC_LINK and CSC_KEY_PASSWORD before running this script.
# Windows store: set package.json build.win.certificateSubjectName instead (see docs/CODE-SIGNING.md).

npm run dist:win
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Refreshing Desktop and Start Menu shortcuts..."
& (Join-Path $Root "deploy\windows\Install-Forge-Shortcut.ps1")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
