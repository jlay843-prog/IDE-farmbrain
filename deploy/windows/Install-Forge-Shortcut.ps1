# Put Forge on the Start Menu, Desktop, and user PATH for this Windows login.
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$LaunchPs1 = Join-Path $Root "scripts\launch-forge.ps1"
$LaunchCmd = Join-Path $Root "scripts\launch-forge.cmd"
$IconIco = Join-Path $Root "ui\forge.ico"

function Get-RealDesktopPath {
  # Honors OneDrive Desktop redirect when Explorer uses it.
  return [Environment]::GetFolderPath("Desktop")
}

function Resolve-ForgeTarget {
  param([string]$RepoRoot)
  $Packaged = Join-Path $RepoRoot "dist\win-unpacked\Forge.exe"
  if (Test-Path $Packaged) {
    return @{ Kind = "exe"; Path = $Packaged; Args = ""; WorkDir = Split-Path $Packaged }
  }
  $Installed = Join-Path $env:LOCALAPPDATA "Programs\Forge\Forge.exe"
  if (Test-Path $Installed) {
    return @{ Kind = "exe"; Path = $Installed; Args = ""; WorkDir = Split-Path $Installed }
  }
  if (Test-Path $LaunchPs1) {
    return @{ Kind = "ps1"; Path = $LaunchPs1; Args = ""; WorkDir = $RepoRoot }
  }
  return $null
}

$target = Resolve-ForgeTarget -RepoRoot $Root
if (-not $target) {
  throw "No Forge launch target found (expected dist\win-unpacked\Forge.exe, installed Forge, or scripts\launch-forge.ps1)."
}

$ws = New-Object -ComObject WScript.Shell
$desktop = Get-RealDesktopPath
$targets = @(
  (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Forge.lnk"),
  (Join-Path $desktop "Forge.lnk")
)

foreach ($path in $targets) {
  $dir = Split-Path $path
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  $sc = $ws.CreateShortcut($path)
  if ($target.Kind -eq "exe") {
    $sc.TargetPath = $target.Path
    $sc.Arguments = $target.Args
    $sc.WorkingDirectory = $target.WorkDir
    if (Test-Path $IconIco) {
      $sc.IconLocation = "$IconIco"
    } else {
      $sc.IconLocation = "$($target.Path),0"
    }
  } else {
    $sc.TargetPath = "powershell.exe"
    $sc.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$($target.Path)`""
    $sc.WorkingDirectory = $target.WorkDir
    if (Test-Path $IconIco) {
      $sc.IconLocation = "$IconIco"
    }
  }
  $sc.Description = "Forge local Qwen coding desk (AMD coder on EVO)"
  $sc.Save()
  Write-Host "Wrote $path -> $($target.Path)"
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
