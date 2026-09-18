# Full v1 smoke chain: pytest, loopback desk, Aether handoff, packaged exe (when built).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$forgeCmd = Join-Path $Root "forge.cmd"
if (Test-Path $forgeCmd) {
  $healthJson = & $forgeCmd health --json
  if ($LASTEXITCODE -gt 1) { throw "forge health --json failed (exit $LASTEXITCODE)" }
  $healthCli = $healthJson | ConvertFrom-Json
  if (-not $healthCli.python.ok) { throw "forge health --json: python missing" }
  if (-not $healthCli.monaco.ok) { throw "forge health --json: monaco missing — run npm run vendor:monaco" }
}

& py -3 -m pytest tests/test_smoke.py -q
& (Join-Path $PSScriptRoot "smoke-forge.ps1")
& (Join-Path $PSScriptRoot "smoke-aether-handoff.ps1")

$packaged = Join-Path $Root "dist\win-unpacked\Forge.exe"
if (Test-Path $packaged) {
  & (Join-Path $PSScriptRoot "smoke-packaged.ps1")
} else {
  Write-Host "Skipping packaged smoke (no dist\win-unpacked\Forge.exe — run npm run dist:win first)."
}

Write-Host "Smoke all OK: pytest + loopback + handoff$(if (Test-Path $packaged) { ' + packaged' } else { '' })"
