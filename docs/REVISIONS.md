# Forge revisions

Short trail for packaged builds Jeff can tell apart.

| Version | Notes |
|---------|--------|
| **1.3.0** | Shortcuts target packaged `dist\win-unpacked\Forge.exe` (fallback: installed Setup, then `launch-forge.ps1`); Desktop uses the real Desktop path (OneDrive when redirected). `dist-win.ps1` refreshes shortcuts after build. Easy: Open control after Accept shells out to the last created/changed file; local-git note; SmartScreen first-run hint. |
| 1.2.0 | Easy vs Advanced desk toggle (default Easy when no workspace). Easy: project-name setup (`git init`, no remote), one chat with Ask/Edit routing, single Accept to apply. Advanced: full Files/Git/Vault/Farm desk. |
| 1.1.1 | Edit inspect loop parses mixed tool-call XML (`<tool>`, `<function>`, `<parameter=…>`, `</function>`, `</tool_call>`); raw tool markup never lands in the transcript. Ask mode strips tool XML and nudges Edit for file work. |
| 1.1.0 | Desk restyle + Cursor-like composer: transcript above input, Enter sends / Shift+Enter newline, bounded conversation history, prominent thinking/inspect status, Go disabled while working, version in header. |
| 1.0.0 | Initial Forge desk — CLI-first local Qwen coding desk, Electron shell, inspect-then-diff Edit, farm-brain QC gate. |

Version lives in `package.json`, `pyproject.toml`, and `src/forge/__init__.py`. Unsigned Windows builds: `.\scripts\dist-win.ps1`.
