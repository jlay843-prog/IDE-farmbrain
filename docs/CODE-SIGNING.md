# Code signing (later milestone)

Forge v1 ships **unsigned** NSIS + portable builds on this PC. Personal farm IDE — do not buy or wait for a cert. SmartScreen warnings on first run are expected.

Signing is optional polish **after** the app is useful here, not a v1 blocker.

## Current config (keep until cert)

`package.json` → `build`:

- `forceCodeSigning`: `false`
- `win.signAndEditExecutable`: `false`

Unsigned builds still work locally. SmartScreen may warn on first run.

## When a cert is ready (one flip)

Always set before `npm run dist:win`:

```powershell
$env:CSC_IDENTITY_AUTO_DISCOVERY = "false"
$env:ELECTRON_BUILDER_CACHE = "$PWD\.eb-cache"
```

Pick **one** identity source:

### PFX file (`CSC_LINK`)

```powershell
$env:CSC_LINK = "C:\path\to\forge-code-sign.pfx"
$env:CSC_KEY_PASSWORD = "<pfx-password>"
```

### Windows certificate store

Install the cert in **Current User → Personal**. In `package.json` → `build.win`, set `certificateSubjectName` to the cert subject (exact string from `certmgr.msc`). Do not set `CSC_LINK` for store certs.

### Enable signing in `package.json`

Flip both flags:

- `forceCodeSigning`: `true`
- `win.signAndEditExecutable`: `true`

Then build and smoke:

```powershell
.\scripts\dist-win.ps1
npm run smoke:packaged
```

Or use `npm run dist:win` directly if the env vars above are already set.
