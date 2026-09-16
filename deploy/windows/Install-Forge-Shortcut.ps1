# Put Forge on the Start Menu, Desktop, and user PATH for this Windows login.
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$LaunchPs1 = Join-Path $Root "scripts\launch-forge.ps1"
$LaunchCmd = Join-Path $Root "scripts\launch-forge.cmd"
$ElectronExe = Join-Path $Root "node_modules\electron\dist\electron.exe"

if (-not (Test-Path $ElectronExe)) {
  Write-Host "Installing Forge desktop dependencies..."
  Push-Location $Root
  try { npm install --no-fund --no-audit } finally { Pop-Location }
}

$ws = New-Object -ComObject WScript.Shell
$targets = @(
  (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Forge.lnk"),
  (Join-Path $env:USERPROFILE "Desktop\Forge.lnk")
)

foreach ($path in $targets) {
  $dir = Split-Path $path
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  $sc = $ws.CreateShortcut($path)
  if (Test-Path $ElectronExe) {
    # App path must be the repo root so package.json name "forge-desk" is used.
    $sc.TargetPath = "$ElectronExe"
    $sc.Arguments = "`"$Root`""
    $sc.WorkingDirectory = "$Root"
    $sc.IconLocation = "$ElectronExe,0"
  } else {
    $sc.TargetPath = "powershell.exe"
    $sc.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$LaunchPs1`""
    $sc.WorkingDirectory = "$Root"
  }
  $sc.Description = "Forge local Qwen coding desk (AMD coder on EVO)"
  $sc.Save()
  Write-Host "Wrote $path"
}

$cmd = Join-Path $Root "forge.cmd"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$Root*") {
  [Environment]::SetEnvironmentVariable("Path", "$userPath;$Root", "User")
  Write-Host "Added $Root to user PATH (new terminals pick this up)."
}

Write-Host "Double-click Forge. Code stays on EVO AMD :11437 (qwen3-coder:30b)."
Write-Host "One command: $LaunchCmd"
Write-Host "CLI: $cmd"
