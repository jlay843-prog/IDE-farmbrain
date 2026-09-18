# W13 smoke — loopback desk health, desk bootstrap, Python on PATH.
# Does not hit burst/5090 or auto-apply farm-brain.
$ErrorActionPreference = "Stop"
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
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    return Start-Process -FilePath $py.Source -ArgumentList @(
      "-3", "-m", "forge", "serve", "--host", $bind, "--port", $port
    ) -PassThru -WorkingDirectory $root -WindowStyle Hidden
  }
  $python = Get-Command python -ErrorAction SilentlyContinue
  if (-not $python) { throw "Python 3.11+ (py -3 or python) must be on PATH for the packaged desk." }
  return Start-Process -FilePath $python.Source -ArgumentList @(
    "-m", "forge", "serve", "--host", $bind, "--port", $port
  ) -PassThru -WorkingDirectory $root -WindowStyle Hidden
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

$desk = Invoke-RestMethod -Uri "$base/api/desk" -TimeoutSec 5
if (-not $desk.ok) { throw "desk bootstrap failed" }
if (-not $desk.recipes) { throw "desk missing recipes" }
foreach ($remote in @($desk.git.remotes)) {
  $url = [string]$remote.url
  if ($url -match "example\.com|invented") {
    throw "invented remote in git snapshot: $url"
  }
}

Write-Host "Smoke OK: forge $($health.version) @ $base (loopback, no burst, no auto-apply)"

if ($started -and -not $started.HasExited) {
  Stop-Process -Id $started.Id -Force
}
