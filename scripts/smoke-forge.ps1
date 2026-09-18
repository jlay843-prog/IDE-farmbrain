# W13–W16 smoke — CLI health preflight, loopback desk, term pane, leftover project prune.
# Does not hit burst/5090 or auto-apply farm-brain.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$forgeCmd = Join-Path $root "forge.cmd"
if (Test-Path $forgeCmd) {
  & $forgeCmd health | Out-Host
  if ($LASTEXITCODE -gt 1) { throw "forge health failed (exit $LASTEXITCODE)" }
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

Write-Host "Smoke OK: forge $($health.version) @ $base (loopback, no burst, no auto-apply)"

if ($started -and -not $started.HasExited) {
  Stop-Process -Id $started.Id -Force
}
