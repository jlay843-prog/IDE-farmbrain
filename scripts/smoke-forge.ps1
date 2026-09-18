# W13–W16 smoke — CLI health preflight, loopback desk, term pane, leftover project prune.
# Does not hit burst/5090 or auto-apply farm-brain.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$forgeCmd = Join-Path $root "forge.cmd"
if (Test-Path $forgeCmd) {
  $healthJson = & $forgeCmd health --json
  if ($LASTEXITCODE -gt 1) { throw "forge health --json failed (exit $LASTEXITCODE)" }
  $healthCli = $healthJson | ConvertFrom-Json
  if (-not $healthCli.ok) { throw "forge health --json ok=false" }
  if ($healthCli.name -ne "forge") { throw "forge health --json unexpected name $($healthCli.name)" }
  if ($healthCli.version -ne "1.0.0") { throw "forge health --json expected v1.0.0, got $($healthCli.version)" }
  if (-not $healthCli.python.ok) { throw "forge health --json python finder failed: $($healthCli.python.error)" }
  if (-not $healthCli.monaco.ok) { throw "forge health --json monaco vendor missing - run npm run vendor:monaco" }
}

$bind = if ($env:FORGE_BIND) { $env:FORGE_BIND } else { "127.0.0.1" }
$port = if ($env:FORGE_PORT) { $env:FORGE_PORT } else { "43180" }
$base = "http://${bind}:${port}"
$started = $null

function Test-ForgeHealth {
  try {
    $r = Invoke-RestMethod -Uri "$base/api/health" -TimeoutSec 3
    return [bool]$r.ok
  } catch {
    return $false
  }
}

function Start-ForgeServer {
  $root = Split-Path -Parent $PSScriptRoot
  $env:PYTHONPATH = Join-Path $root "src"
  $forgeCmd = Join-Path $root "forge.cmd"
  if (Test-Path $forgeCmd) {
    return Start-Process -FilePath "cmd.exe" -ArgumentList @(
      "/c", $forgeCmd, "serve", "--host", $bind, "--port", $port
    ) -PassThru -WorkingDirectory $root -WindowStyle Hidden
  }
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    return Start-Process -FilePath $py.Source -ArgumentList @(
      "-3", "-m", "forge", "serve", "--host", $bind, "--port", $port
    ) -PassThru -WorkingDirectory $root -WindowStyle Hidden -Environment @{ PYTHONPATH = $env:PYTHONPATH }
  }
  $python = Get-Command python -ErrorAction SilentlyContinue
  if (-not $python) { throw "Python 3.11+ (py -3 or python) must be on PATH for the packaged desk." }
  return Start-Process -FilePath $python.Source -ArgumentList @(
    "-m", "forge", "serve", "--host", $bind, "--port", $port
  ) -PassThru -WorkingDirectory $root -WindowStyle Hidden -Environment @{ PYTHONPATH = $env:PYTHONPATH }
}

if (-not (Test-ForgeHealth)) {
  $started = Start-ForgeServer
  $ok = $false
  for ($i = 0; $i -lt 45; $i++) {
    if (Test-ForgeHealth) { $ok = $true; break }
    if ($started.HasExited) { break }
    Start-Sleep -Milliseconds 400
  }
  if (-not $ok) {
    if ($started -and -not $started.HasExited) { Stop-Process -Id $started.Id -Force }
    throw "Forge did not become ready on ${bind}:${port}"
  }
}

$health = Invoke-RestMethod -Uri "$base/api/health" -TimeoutSec 5
if (-not $health.ok) { throw "health ok=false" }
if ($health.name -ne "forge") { throw "unexpected health name $($health.name)" }
if ($health.version -ne "1.0.0") { throw "expected v1.0.0, got $($health.version)" }
if (-not $health.python.ok) { throw "python finder failed: $($health.python.error)" }
if (-not $health.monaco.ok) { throw "monaco vendor missing - run npm run vendor:monaco" }
if (Test-Path $forgeCmd) {
  $healthCli = (& $forgeCmd health --json | ConvertFrom-Json)
  if ($healthCli.version -ne $health.version) { throw "forge health --json version mismatch" }
  if ($healthCli.python.ok -ne $health.python.ok) { throw "forge health --json python mismatch vs /api/health" }
  if ($healthCli.monaco.ok -ne $health.monaco.ok) { throw "forge health --json monaco mismatch vs /api/health" }
}
$monacoLoader = Invoke-WebRequest -Uri "$base/vendor/monaco-editor/min/vs/loader.js" -UseBasicParsing -TimeoutSec 5
if ($monacoLoader.StatusCode -ne 200) { throw "monaco loader not served from loopback" }
if ($monacoLoader.Content -notmatch "require") { throw "monaco loader looks wrong" }

$desk = Invoke-RestMethod -Uri "$base/api/desk" -TimeoutSec 5
if (-not $desk.ok) { throw "desk bootstrap failed" }
if (-not $desk.recipes) { throw "desk missing recipes" }
if (-not $desk.term) { throw "desk missing term snapshot" }
if ($desk.term.model_tool) { throw "terminal must not be a model tool" }
foreach ($row in @($desk.state.projects)) {
  if ($row.name -eq "forge-w7-farm-brain") { throw "leftover W7 project row still in desk" }
  if ($row.name -eq "farm-brain" -and $row.path -match '\\Temp\\') { throw "leftover Temp farm-brain project row still in desk" }
}
foreach ($remote in @($desk.git.remotes)) {
  $url = [string]$remote.url
  if ($url -match "example\.com|invented") {
    throw "invented remote in git snapshot: $url"
  }
}

$term = Invoke-RestMethod -Uri "$base/api/term" -Method POST -ContentType "application/json" -Body '{"action":"start"}' -TimeoutSec 8
if (-not $term.ok) { throw "term start failed" }
$termWrite = Invoke-RestMethod -Uri "$base/api/term" -Method POST -ContentType "application/json" -Body '{"action":"write","text":"echo forge-smoke-term"}' -TimeoutSec 8
if (-not $termWrite.ok) { throw "term write failed" }
Start-Sleep -Milliseconds 400
$termSnap = Invoke-RestMethod -Uri "$base/api/term" -TimeoutSec 5
if ($termSnap.text -notmatch "forge-smoke-term") { throw "term pane did not echo" }
Invoke-RestMethod -Uri "$base/api/term" -Method POST -ContentType "application/json" -Body '{"action":"stop"}' -TimeoutSec 8 | Out-Null

$log = Invoke-RestMethod -Uri "$base/api/log?limit=5" -TimeoutSec 5
if (-not $log.ok) { throw "log endpoint failed" }
if (-not $log.path) { throw "log endpoint missing path" }
if ($null -eq $log.turns) { throw "log endpoint missing turns" }

if (Test-Path $forgeCmd) {
  $logJson = & $forgeCmd log --json --limit 5
  if ($LASTEXITCODE -ne 0) { throw "forge log --json failed (exit $LASTEXITCODE)" }
  $logCli = $logJson | ConvertFrom-Json
  if (-not $logCli.ok) { throw "forge log --json ok=false" }
  if (-not $logCli.path) { throw "forge log --json missing path" }
  if ($null -eq $logCli.turns) { throw "forge log --json missing turns" }

  $gitJson = & $forgeCmd git --json
  if ($LASTEXITCODE -ne 0) { throw "forge git --json failed (exit $LASTEXITCODE)" }
  $gitCli = $gitJson | ConvertFrom-Json
  if (-not $gitCli.ok) { throw "forge git --json ok=false" }
  foreach ($remote in @($gitCli.remotes)) {
    $url = [string]$remote.url
    if ($url -match "example\.com|invented") {
      throw "invented remote in forge git --json: $url"
    }
  }

  $whichJson = & $forgeCmd which --json
  if ($LASTEXITCODE -ne 0) { throw "forge which --json failed (exit $LASTEXITCODE)" }
  $whichCli = $whichJson | ConvertFrom-Json
  if (-not $whichCli.workspace) { throw "forge which --json missing workspace" }
  if (-not $whichCli.tier) { throw "forge which --json missing tier" }
  if (-not ($whichCli.resolved_model -or $whichCli.model)) { throw "forge which --json missing model" }
  if ($null -eq $whichCli.reachable) { throw "forge which --json missing reachable" }

  $statusApi = Invoke-RestMethod -Uri "$base/api/status" -TimeoutSec 8
  if (-not $statusApi.name) { throw "/api/status missing name" }
  if ($null -eq $statusApi.vast_active) { throw "/api/status missing vast_active" }
  if (-not $statusApi.backends) { throw "/api/status missing backends" }

  $statusJson = & $forgeCmd status --json
  if ($LASTEXITCODE -ne 0) { throw "forge status --json failed (exit $LASTEXITCODE)" }
  $statusCli = $statusJson | ConvertFrom-Json
  if ($statusCli.name -ne "forge") { throw "forge status --json unexpected name $($statusCli.name)" }
  if ($statusCli.vast_active -ne $statusApi.vast_active) { throw "forge status --json vast_active mismatch vs /api/status" }
  if ($statusCli.farm.ok -ne $statusApi.farm.ok) { throw "forge status --json farm.ok mismatch vs /api/status" }
  if ($statusCli.backends.amd.ok -ne $statusApi.backends.amd.ok) { throw "forge status --json backends.amd mismatch vs /api/status" }

  $probeJson = & $forgeCmd telegram --probe --json
  if ($LASTEXITCODE -ne 0) { throw "forge telegram --probe failed (exit $LASTEXITCODE)" }
  $probe = $probeJson | ConvertFrom-Json
  if (-not $probe.legion) { throw "forge telegram probe: legion=false (Legion-only)" }
  if ($probe.farm_brain) { throw "forge telegram probe: farm_brain must be false" }
}

Write-Host "Smoke OK: forge $($health.version) @ $base (loopback, no burst, no auto-apply)"

if ($started -and -not $started.HasExited) {
  Stop-Process -Id $started.Id -Force
}
