# Launch Forge as local desk software on this computer.
# Qwen stays on EVO (AMD coder :11437 / CUDA chat :11434). Never port-forward Ollama.
# Pass the repo root to Electron (not the desktop entry file) so the app name is Forge, not Electron.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$env:FORGE_BIND = "127.0.0.1"
$env:FORGE_PORT = $(if ($env:FORGE_PORT) { $env:FORGE_PORT } else { "43180" })
if (-not $env:FORGE_DATA) { $env:FORGE_DATA = Join-Path $env:LOCALAPPDATA "Forge" }
$env:PYTHONPATH = (Join-Path $Root "src") + $(if ($env:PYTHONPATH) { ";" + $env:PYTHONPATH } else { "" })

New-Item -ItemType Directory -Force -Path $env:FORGE_DATA | Out-Null
$Log = Join-Path $env:FORGE_DATA "launch.log"
function Write-Forge([string]$Message) {
  $line = "$(Get-Date -Format o) $Message"
  Add-Content -Path $Log -Value $line
  Write-Host $Message
}

function Test-ForgeHealth {
  try {
    $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://127.0.0.1:$($env:FORGE_PORT)/api/health"
    return ($r.StatusCode -eq 200 -and $r.Content -match "forge")
  } catch {
    return $false
  }
}

function Start-ForgePython {
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    return Start-Process -FilePath $py.Source -ArgumentList @(
      "-3", "-m", "forge", "serve", "--host", "127.0.0.1", "--port", $env:FORGE_PORT
    ) -PassThru -WorkingDirectory $Root -WindowStyle Hidden
  }
  $python = Get-Command python -ErrorAction SilentlyContinue
  if (-not $python) { throw "Forge needs Python 3.11+ (py -3 or python on PATH)." }
  return Start-Process -FilePath $python.Source -ArgumentList @(
    "-m", "forge", "serve", "--host", "127.0.0.1", "--port", $env:FORGE_PORT
  ) -PassThru -WorkingDirectory $Root -WindowStyle Hidden
}

function Open-ForgeEdge([string]$DeskUrl) {
  $edge = @(
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
  ) | Where-Object { Test-Path $_ } | Select-Object -First 1
  $profile = Join-Path $env:FORGE_DATA "edge-profile"
  New-Item -ItemType Directory -Force -Path $profile | Out-Null
  if ($edge) {
    Start-Process $edge -ArgumentList @("--app=$DeskUrl", "--user-data-dir=$profile")
  } else {
    Start-Process $DeskUrl
  }
}

$electronExe = Join-Path $Root "node_modules\electron\dist\electron.exe"
if (-not (Test-Path $electronExe)) {
  Write-Forge "Installing Forge desktop dependencies..."
  npm install --no-fund --no-audit
}

$deskUrl = "http://127.0.0.1:$($env:FORGE_PORT)/"
$ownedServer = $null

if (Test-Path $electronExe) {
  Write-Forge "Starting Forge desktop..."
  $p = Start-Process -FilePath $electronExe -ArgumentList @($Root) -WorkingDirectory $Root -PassThru
  $ok = $false
  for ($i = 0; $i -lt 90; $i++) {
    if (Test-ForgeHealth) { $ok = $true; break }
    if ($p.HasExited) { break }
    Start-Sleep -Milliseconds 400
  }
  if (-not $ok) { $ok = Test-ForgeHealth }
  if ($ok) {
    Write-Forge "Desk ready at $deskUrl"
    if (-not $p.HasExited) { Wait-Process -Id $p.Id }
    exit 0
  }
  Write-Forge "Electron exited $($p.ExitCode) before the desk was ready; falling back to Edge."
}

Write-Forge "Using Python desk + Edge app window."
if (-not (Test-ForgeHealth)) {
  $ownedServer = Start-ForgePython
}
$ok = $false
for ($i = 0; $i -lt 90; $i++) {
  if (Test-ForgeHealth) { $ok = $true; break }
  if ($ownedServer -and $ownedServer.HasExited) { break }
  Start-Sleep -Milliseconds 400
}
if (-not $ok) {
  if ($ownedServer -and -not $ownedServer.HasExited) { Stop-Process -Id $ownedServer.Id -Force }
  throw "Forge did not become ready on 127.0.0.1:$($env:FORGE_PORT). See $Log"
}
Write-Forge "Desk ready at $deskUrl"
Open-ForgeEdge $deskUrl
if ($ownedServer) {
  Wait-Process -Id $ownedServer.Id
}
