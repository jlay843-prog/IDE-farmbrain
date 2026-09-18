# Post-install / post-build smoke for Jeff's Windows desk.
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
& (Join-Path $Root "scripts\smoke-forge.ps1")
