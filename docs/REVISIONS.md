# Forge revisions

Short trail for packaged builds Jeff can tell apart.

| Version | Notes |
|---------|--------|
| **1.3.4** | Farm check **ray** in Easy dropdown + `forge check all`. **temps** = EVO 5070 Ti + CPU, tower 5090 + 5950X, BC-250 dials; 5090 idle/blocked-for-Vast → WARN not FAIL. **apps**: ARIA UI `Accept: */*`; Blender MCP `:9876` TCP. **llm** expect tags match live `/api/ps` (`qwen3.8:27b-q4_K_M`). Empero stays off CUDA; boards CHECK/RESULT/LINES only. |
| **1.3.3** | Easy mode shows **Ask** (default, `qwen3.8:27b`) vs **Code** (`qwen3-coder:30b`) turn picker — no auto-hide. Canned **Farm check** dropdown runs `GET /api/check?name=` (farm, llm, temps, apps, vpn, all) and prints the CHECK/RESULT/LINES board (no LLM status invention). Grok-builder `checks.py`, recipes, `/api/check`, and farm-check skill ship in the package. |
| **1.3.2** | Easy Edit no longer aborts on qwen3-coder `<parameter>` tool XML: outbound chat history is sanitized before Ollama, native Ollama tools are disabled (Forge markup loop only), parser errors retry without tools, desk shows a friendly message instead of raw XML errors. |
| **1.3.1** | Easy/Ask system prompts: files are first-class (Accept/Apply writes locally); clarify CAN/CANNOT (no shell, no deploy/browser automation); Easy capability answers no longer claim “cannot touch the filesystem.” |
| **1.3.0** | Shortcuts target packaged `dist\win-unpacked\Forge.exe` (fallback: installed Setup, then `launch-forge.ps1`); Desktop uses the real Desktop path (OneDrive when redirected). `dist-win.ps1` refreshes shortcuts after build. Easy: Open control after Accept shells out to the last created/changed file; local-git note; SmartScreen first-run hint. |
| 1.2.0 | Easy vs Advanced desk toggle (default Easy when no workspace). Easy: project-name setup (`git init`, no remote), one chat with Ask/Edit routing, single Accept to apply. Advanced: full Files/Git/Vault/Farm desk. |
| 1.1.1 | Edit inspect loop parses mixed tool-call XML (`<tool>`, `<function>`, `<parameter=…>`, `</function>`, `</tool_call>`); raw tool markup never lands in the transcript. Ask mode strips tool XML and nudges Edit for file work. |
| 1.1.0 | Desk restyle + Cursor-like composer: transcript above input, Enter sends / Shift+Enter newline, bounded conversation history, prominent thinking/inspect status, Go disabled while working, version in header. |
| 1.0.0 | Initial Forge desk — CLI-first local Qwen coding desk, Electron shell, inspect-then-diff Edit, farm-brain QC gate. |

Version lives in `package.json`, `pyproject.toml`, and `src/forge/__init__.py`. Unsigned Windows builds: `.\scripts\dist-win.ps1`.
