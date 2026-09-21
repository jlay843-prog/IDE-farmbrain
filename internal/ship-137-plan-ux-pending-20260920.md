# Ship 1.3.7 — Plan stream UX + pending Accept

## Incident (Jeff)

- Forge window closed before Accept during agent `dist-win` rebuild.
- **Cause:** agent ran `Stop-Process` on `Forge`/`electron` before retrying `dist-win.ps1` (EBUSY on `dist\win-unpacked`). Not an app crash.
- **Recovery:** last edit metadata in `sessions.jsonl` (`applied: false`) but **no diff body** — pending diff was RAM-only. **Not recoverable.**

## Fix

- Stream plan tokens over SSE; banner **Planning on 5090 flash…**
- Persist pending Accept to `%LOCALAPPDATA%\Forge\pending-accept.json`
- `smoke-packaged.ps1` no longer kills a live desk when health already reports target version
