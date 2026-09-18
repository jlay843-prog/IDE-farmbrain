# W19 — verify sibling Aether reads forge-handoff.json (loopback only).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$AetherRoot = "C:\Users\jlay\Grok\aether"
$AetherBind = if ($env:AETHER_BIND) { $env:AETHER_BIND } else { "127.0.0.1" }
$AetherPort = if ($env:AETHER_PORT) { $env:AETHER_PORT } else { "43127" }
$AetherBase = "http://${AetherBind}:${AetherPort}"
$TestUrl = "https://ispe.org/news"

$data = Join-Path $env:LOCALAPPDATA "Aether\data"
New-Item -ItemType Directory -Force -Path $data | Out-Null
$handoffFile = Join-Path $data "forge-handoff.json"
$consumedFile = Join-Path $data "forge-handoff.consumed.json"
if (Test-Path $consumedFile) { Remove-Item $consumedFile -Force }

function Get-AetherToken {
  if ($env:AETHER_TOKEN) { return $env:AETHER_TOKEN }
  $secret = "C:\Users\jlay\secrets\aether_token.txt"
  if (Test-Path $secret) { return (Get-Content $secret -Raw).Trim() }
  return ""
}

function Test-AetherHealth {
  try {
    $r = Invoke-RestMethod -Uri "$AetherBase/api/health" -TimeoutSec 3
    return ($r.app -eq "aether")
  } catch {
    return $false
  }
}

$aetherProc = $null
if (-not (Test-AetherHealth)) {
  if (-not (Test-Path (Join-Path $AetherRoot "desktop\start-server.cjs"))) {
    throw "Aether tree missing at $AetherRoot"
  }
  Write-Host "Starting Aether server for handoff smoke..."
  $aetherProc = Start-Process -FilePath "node" -ArgumentList @(
    (Join-Path $AetherRoot "desktop\start-server.cjs")
  ) -WorkingDirectory $AetherRoot -PassThru -WindowStyle Hidden
  $ok = $false
  for ($i = 0; $i -lt 90; $i++) {
    if (Test-AetherHealth) { $ok = $true; break }
    if ($aetherProc.HasExited) { break }
    Start-Sleep -Milliseconds 500
  }
  if (-not $ok) {
    if ($aetherProc -and -not $aetherProc.HasExited) { Stop-Process -Id $aetherProc.Id -Force }
    throw "Aether did not become ready on $AetherBase"
  }
}

Push-Location $Root
$env:PYTHONPATH = Join-Path $Root "src"
$launch = & py -3 -c @"
from forge.launch import launch
import json
print(json.dumps(launch('aether', url='$TestUrl')))
"@
Pop-Location
$result = $launch | ConvertFrom-Json
if (-not $result.ok) { throw "forge launch aether failed: $($launch)" }
if (-not (Test-Path $handoffFile)) { throw "forge-handoff.json not written at $handoffFile" }
$payload = Get-Content $handoffFile -Raw | ConvertFrom-Json
if ($payload.url -ne $TestUrl) { throw "handoff url mismatch: $($payload.url)" }
if ($payload.from -ne "forge") { throw "handoff from must be forge" }

$headers = @{ Accept = "application/json" }
$token = Get-AetherToken
if ($token) { $headers["x-aether-token"] = $token }
$api = Invoke-RestMethod -Uri "$AetherBase/api/forge-handoff" -Headers $headers -TimeoutSec 8
if (-not $api.url) { throw "Aether forge-handoff API returned empty url" }
if ($api.url -ne $TestUrl) { throw "Aether API url mismatch: $($api.url)" }
if (-not $api.pending) { throw "Aether handoff should be pending before consume" }

Write-Host "Aether handoff smoke OK: pending $($api.url) at $($api.path)"

if ($aetherProc -and -not $aetherProc.HasExited) {
  Stop-Process -Id $aetherProc.Id -Force
}
