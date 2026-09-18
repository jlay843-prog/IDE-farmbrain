# Smoke the built Forge.exe (W13). Seeds workspace so the first-run picker does not block headless runs.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Exe = Join-Path $Root "dist\win-unpacked\Forge.exe"
if (-not (Test-Path $Exe)) { throw "Run npm run dist:win first. Missing $Exe" }

$bind = if ($env:FORGE_BIND) { $env:FORGE_BIND } else { "127.0.0.1" }
$port = if ($env:FORGE_PORT) { $env:FORGE_PORT } else { "43180" }
$base = "http://${bind}:${port}"

$data = Join-Path $env:TEMP "forge-smoke-data"
New-Item -ItemType Directory -Force -Path $data | Out-Null
@{
  workspace = $Root
  tier = "code"
  last_model = "qwen3-coder:30b"
  code_model = "qwen3-coder:30b"
  chat_model = "qwen3.8:27b"
  projects = @()
} | ConvertTo-Json | Set-Content -Path (Join-Path $data "state.json") -Encoding utf8

$env:FORGE_DATA = $data
$env:FORGE_BIND = $bind
$env:FORGE_PORT = $port

Get-Process electron,Forge,python,py -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

$p = Start-Process -FilePath $Exe -PassThru
$ok = $false
for ($i = 0; $i -lt 90; $i++) {
  try {
    $health = Invoke-RestMethod -Uri "$base/api/health" -TimeoutSec 2
    if ($health.ok -and $health.version -eq "1.0.0") { $ok = $true; break }
  } catch {}
  if ($p.HasExited) { break }
  Start-Sleep -Milliseconds 500
}
if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force }
if (-not $ok) { throw "Packaged Forge.exe did not report v1.0.0 on $base" }
Write-Host "Packaged smoke OK: forge $($health.version) @ $base"
