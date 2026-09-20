# Forge farm-check handoff (for Cursor)

**Date:** 2026-09-19  
**Repo:** `C:\Users\jlay\Grok\forge` (git remote / product: Forge desk — local Qwen IDE)  
**Why this note:** Canned farm status checks were added so **qwen3-coder:30b** can report PASS/FAIL boards without inventing health. If you were editing the desk UI or packaging the `.exe`, this is the CLI/skill surface that changed alongside.

---

## What we added

### 1. CLI: `forge check`

Rigid status boards for Lone Tree Acres (LAN / Meshnet).

| Command | Probes |
|---------|--------|
| `forge check list` | List check ids |
| `forge check farm` | Farm Brain `http://192.168.68.103:5000/health` + fleet online count |
| `forge check llm` | CUDA `:11434` warm `qwen3.8:27b-q4_K_M`; AMD `:11437` warm Empero + coder; **Empero must not be on CUDA** |
| `forge check temps` | **EVO 5070 Ti** + EVO CPU; **tower RTX 5090** + **5950X**; BC-250 dials |
| `forge check apps` | HTTP (html/json): dashboard, ARIA UI/API, AI-PM, ontology, Lumen, Speaches, Academy, Ray; **TCP** Blender MCP `:9876`; tower Ollama |

**Probe gotchas (fixed 2026-09-19):**
- ARIA UI (`vite preview :5173`) returns **404** if `Accept: application/json` — check uses `Accept: */*` for HTML apps.
- Blender MCP is a **raw TCP** listener on EVO `:9876`, not HTTP — check uses socket connect.
| `forge check vpn` | Same as farm+apps (practical Meshnet test = reach `.103`) |
| `forge check ray` | Ray head: GCS `:6379` TCP, dashboard `:8265`, jobs API, `ray_head_ok` / BC-250 worker modes |
| `forge check all` | farm + llm + temps + apps + ray |
| `forge check <id> --json` | Same payload as JSON |

**Board format (paste as-is):**

```
CHECK: llm
RESULT: PASS|FAIL|WARN
LINES:
- PASS cuda_warm: expect=qwen3.8:27b-q4_K_M loaded=...
- FAIL amd_empero: expect=empero-35b-a3b:q4km loaded=none
SUMMARY: N pass, N fail, N warn
INSTRUCTION: Report these lines only. Do not invent status.
```

### 2. New / updated source files

| Path | Role |
|------|------|
| `src/forge/checks.py` | **New** — canned probes + `format_board()` |
| `src/forge/cli.py` | **Updated** — `cmd_check`, `forge check` parser; recipe `shell` kind runs `forge check …` |
| `src/forge/recipes.py` | **Updated** — recipes `farm-status`, `farm-llm`, `farm-temps`, `farm-vpn`, `farm-ray` |
| `src/forge/serve.py` | **Updated** — `GET /api/check?name=all` (desk loopback API) |
| `tests/test_checks.py` | **New** — unit tests for list/unknown |
| `.agents/skills/farm-check/SKILL.md` | **New** — instructions for local coder / Cursor agent |
| `README.md` | **Updated** — CLI table + farm-check section |
| `docs/FARM-CHECK-HANDOFF.md` | **This file** |

### 3. Recipes (slash-like for desk)

```bat
forge recipe list
forge recipe run farm-status
forge recipe run farm-llm
forge recipe run farm-temps
forge recipe run farm-vpn
forge recipe run farm-ray
```

`shell` recipes call `forge check …` directly — they do **not** send a free-form prompt to the LLM for status invention.

### 4. Desk HTTP (dev / packaged loopback)

When Forge desk is up (`127.0.0.1:43180`):

```
GET http://127.0.0.1:43180/api/check?name=llm
GET http://127.0.0.1:43180/api/check?name=all
```

Uses same `run_check()` as CLI. Farm probes send `X-Farm-Local-Key` from `C:\Users\jlay\secrets\farm_operator_token.txt` when present (`forge.httputil`).

---

## Expected farm LLM layout (do not “fix” by moving Empero)

| Backend | URL | Keep warm |
|---------|-----|-----------|
| CUDA (5070 Ti 16GB) | `http://192.168.68.103:11434` | `qwen3.8:27b-q4_K_M` (chat / AI-PM) |
| AMD GTT (unified) | `http://192.168.68.103:11437` | `empero-35b-a3b:q4km` + `qwen3-coder:30b` |

**Empero does not fit the 16GB 5070 Ti.** If `forge check llm` reports Empero on CUDA → FAIL.

---

## Rule for qwen3-coder:30b / Cursor agent in this repo

From `.agents/skills/farm-check/SKILL.md`:

1. Jeff asks status / VPN / temps / LLM warm → run **exactly** `forge check <id>`.
2. Paste the board. Do not invent hosts or flip PASS/FAIL.
3. Only propose fixes if Jeff asks after a FAIL board.

Triggers: “farm status”, “vpn”, “temps”, “is Empero up”, `/farm-status`, `/farm-llm`, `/farm-temps`, `/farm-vpn`, `/farm-apps`.

---

## Impact on packaged `.exe` / dist

| Artifact | Impact |
|----------|--------|
| **Dev tree** (`py -3 -m forge` / PATH `forge`) | Picks up changes immediately via `src/forge/` |
| **Packaged desk** `dist\win-unpacked\Forge.exe` / `Forge-Setup-*.exe` | Embeds `resources\src\forge\` at **build time** — **does not** include these changes until you rebuild |

To ship checks inside the next `.exe`:

```powershell
cd C:\Users\jlay\Grok\forge
npm install
$env:CSC_IDENTITY_AUTO_DISCOVERY = "false"
$env:ELECTRON_BUILDER_CACHE = "$PWD\.eb-cache"
# Ensure farm-check skill is copied into package resources if your packer includes .agents/
# (verify dist script includes src\forge\checks.py — it should via normal src bundle)
.\scripts\dist-win.ps1
npm run smoke
npm run smoke:packaged
```

**Minimum verify before tagging a release:**

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3 -m pytest tests/test_checks.py -q
py -3 -m forge check list
py -3 -m forge check farm
py -3 -m forge check llm
```

If the packaged app shells out to `forge` on PATH, ensure Install-Forge-Shortcut still points at this repo (or the installed `resources` tree includes updated `checks.py`).

---

## How Cursor should continue

1. **Read** this file + `.agents/skills/farm-check/SKILL.md`.
2. **Do not** rewrite farm status as free-form LLM prose — wire UI buttons to:
   - `forge check all` / `forge recipe run farm-status`, or
   - `GET /api/check?name=all`.
3. If adding a desk UI “Farm status” button: show `format_board` text or JSON `lines[]` as a monospace board.
4. Keep Empero off CUDA in any “warm models” UX copy.
5. Rebuild `.exe` only after CLI smokes pass on the live LAN.

---

## Related farm context (not in this PR, but status checks depend on it)

- Farm Brain dashboard: `http://192.168.68.103:5000`
- AI-PM now defaults to Ollama **`qwen3.8:27b-q4_K_M`** on CUDA (`agilent-roadmap` `packages/llm.py`)
- Blender MCP: EVO `192.168.68.103:9876` (Grok `~/.grok/config.toml` `[mcp_servers.blender]`)
- Operator token (Legion): `C:\Users\jlay\secrets\farm_operator_token.txt`

---

## Quick copy for Cursor chat

```
Forge canned farm checks (updated 2026-09-19). Use:
  forge check all|farm|llm|temps|apps|vpn|ray
  forge recipe run farm-status|farm-llm|farm-temps|farm-vpn|farm-ray
  GET http://127.0.0.1:43180/api/check?name=ray
temps = EVO 5070 Ti + CPU, tower 5090 + 5950X, BC-250 dials
ray = GCS :6379 + dashboard :8265 + jobs API + worker modes
apps: ARIA UI uses Accept */* (not JSON); Blender MCP is TCP :9876 not HTTP
Skill: .agents/skills/farm-check/SKILL.md
Docs: docs/FARM-CHECK-HANDOFF.md
Local coder must paste the CHECK/RESULT/LINES board only — no invented status.
Packaged .exe needs dist-win.ps1 rebuild to include checks.py.
```
