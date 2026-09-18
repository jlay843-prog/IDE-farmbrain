# Unsigned Windows build wrapper. Signing stays off until Jeff flips package.json + cert env (see docs/CODE-SIGNING.md).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$env:CSC_IDENTITY_AUTO_DISCOVERY = "false"
if (-not $env:ELECTRON_BUILDER_CACHE) {
  $env:ELECTRON_BUILDER_CACHE = Join-Path $Root ".eb-cache"
}

# When cert is ready (PFX path): set CSC_LINK and CSC_KEY_PASSWORD before running this script.
# Windows store: set package.json build.win.certificateSubjectName instead (see docs/CODE-SIGNING.md).

npm run dist:win
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
