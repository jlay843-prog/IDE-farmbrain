# Vendor Monaco Editor min build for offline Forge desk (no CDN).
$ErrorActionPreference = "Stop"
$Version = if ($env:FORGE_MONACO_VERSION) { $env:FORGE_MONACO_VERSION } else { "0.52.2" }
$Root = Split-Path -Parent $PSScriptRoot
$Dest = Join-Path $Root "ui\vendor\monaco-editor"
$Marker = Join-Path $Dest ".forge-monaco-vendored"
$Loader = Join-Path $Dest "min\vs\loader.js"
$TgzUrl = "https://registry.npmjs.org/monaco-editor/-/monaco-editor-$Version.tgz"
$Tgz = Join-Path $env:TEMP "monaco-editor-$Version.tgz"
$Extract = Join-Path $env:TEMP "monaco-editor-$Version-extract"

function Test-VendoredMonaco {
  if (-not (Test-Path $Loader)) { return $false }
  if (-not (Test-Path $Marker)) { return $false }
  $stamp = Get-Content $Marker -Raw -ErrorAction SilentlyContinue
  return ($stamp -match $Version)
}

if (Test-VendoredMonaco) {
  Write-Host "Monaco Editor $Version already vendored at $Dest"
  exit 0
}

Write-Host "Downloading monaco-editor $Version..."
Invoke-WebRequest -Uri $TgzUrl -OutFile $Tgz -UseBasicParsing

if (Test-Path $Extract) { Remove-Item -Recurse -Force $Extract }
New-Item -ItemType Directory -Force -Path $Extract | Out-Null
tar -xzf $Tgz -C $Extract
Remove-Item $Tgz -Force -ErrorAction SilentlyContinue

$pkgMin = Join-Path $Extract "package\min"
if (-not (Test-Path (Join-Path $pkgMin "vs\loader.js"))) {
  throw "monaco-editor package missing min/vs/loader.js"
}

if (Test-Path $Dest) { Remove-Item -Recurse -Force $Dest }
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
Copy-Item -Recurse -Force -Path $pkgMin -Destination (Join-Path $Dest "min")
Remove-Item -Recurse -Force $Extract -ErrorAction SilentlyContinue

Set-Content -Path $Marker -Value "monaco-editor $Version vendored for Forge desk`n" -Encoding utf8
Write-Host "Monaco Editor $Version vendored to $Dest"
