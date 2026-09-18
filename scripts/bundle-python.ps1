# Bundle CPython embeddable amd64 for packaged Forge (no system Python on PATH).
$ErrorActionPreference = "Stop"
$Version = if ($env:FORGE_PYTHON_VERSION) { $env:FORGE_PYTHON_VERSION } else { "3.12.10" }
$Root = Split-Path -Parent $PSScriptRoot
$Dest = Join-Path $Root "python"
$Marker = Join-Path $Dest ".forge-bundled"
$ZipName = "python-$Version-embed-amd64.zip"
$ZipUrl = "https://www.python.org/ftp/python/$Version/$ZipName"
$Zip = Join-Path $env:TEMP $ZipName

function Test-BundledPython {
  $exe = Join-Path $Dest "python.exe"
  if (-not (Test-Path $exe)) { return $false }
  if (-not (Test-Path $Marker)) { return $false }
  $stamp = Get-Content $Marker -Raw -ErrorAction SilentlyContinue
  if ($stamp -notmatch $Version) { return $false }
  $probe = & $exe -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
  return $LASTEXITCODE -eq 0
}

if (Test-BundledPython) {
  Write-Host "Bundled Python $Version already present at $Dest"
  exit 0
}

Write-Host "Downloading Python $Version embeddable..."
Invoke-WebRequest -Uri $ZipUrl -OutFile $Zip -UseBasicParsing

if (Test-Path $Dest) { Remove-Item -Recurse -Force $Dest }
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
Expand-Archive -Path $Zip -DestinationPath $Dest -Force
Remove-Item $Zip -Force -ErrorAction SilentlyContinue

$pth = Get-ChildItem -Path $Dest -Filter "python*._pth" | Select-Object -First 1
if ($pth) {
  $lines = Get-Content $pth.FullName
  $out = @()
  $hasSite = $false
  foreach ($line in $lines) {
    if ($line -match '^\s*#\s*import site') {
      $out += "import site"
      $hasSite = $true
      continue
    }
    if ($line -match '^\s*import site') { $hasSite = $true }
    $out += $line
  }
  if (-not $hasSite) { $out += "import site" }
  if ($out -notcontains "..\src") { $out += "..\src" }
  Set-Content -Path $pth.FullName -Value $out -Encoding ascii
}

Set-Content -Path $Marker -Value "forge-bundled $Version $(Get-Date -Format o)" -Encoding utf8
$exe = Join-Path $Dest "python.exe"
if (-not (Test-Path $exe)) { throw "python.exe missing after extract" }
& $exe -c "import sys; print(sys.version)"
if ($LASTEXITCODE -ne 0) { throw "Bundled python failed version probe" }
Write-Host "Bundled Python $Version ready at $Dest"
