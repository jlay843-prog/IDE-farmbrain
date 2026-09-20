# Forge

Local Qwen coding desk for this farm LAN. **CLI is the product.** The Windows window is a thin visual shell around it.

Code stays on **EVO AMD `:11437` / `qwen3-coder-next:latest`**. Chat can use **EVO CUDA `:11434` / `qwen3.8:27b`**. The tower 5090 is burst-only and **blocked while Vast is live**. Do not port-forward Ollama. Optional **Helpers** after Edit: **Review** (Empero on AMD) and **Check** (5090 flash when pulled).

Sibling to Aether, Lumen, Farm Brain, and AI-PM — not inside `lumen-lab-twin`.

## Windows desk

First-time setup:

```powershell
cd C:\Users\jlay\Grok\forge
npm install
.\deploy\windows\Install-Forge-Shortcut.ps1
```

That writes a Desktop / Start Menu shortcut that opens Electron with this folder as the app (so Forge does not collide with Aether).

Windows v1 desk (W12–W13 — custom icon, NSIS uninstaller, first-run workspace picker, smoke):

```powershell
cd C:\Users\jlay\Grok\forge
npm install
$env:CSC_IDENTITY_AUTO_DISCOVERY = "false"
$env:ELECTRON_BUILDER_CACHE = "$PWD\.eb-cache"
.\scripts\dist-win.ps1
npm run smoke
npm run smoke:handoff
npm run smoke:packaged
npm run smoke:all
```

That writes:

- `dist\Forge-Setup-1.0.0.exe` — NSIS installer with **Uninstall Forge** in Settings → Apps
- `dist\Forge-1.0.0.exe` — portable build (same icon)
- `dist\win-unpacked\Forge.exe`

Code signing is **blocked** (no cert). See [docs/CODE-SIGNING.md](docs/CODE-SIGNING.md). Git remote is Jeff-configured only — see [docs/GIT-REMOTE.md](docs/GIT-REMOTE.md) (`origin` → `IDE-farmbrain`).

Packaged builds bundle CPython embeddable (`npm run bundle:python` before `dist:win`). The desk prefers `resources\python\python.exe` and does not need system Python on PATH. Dev trees still use `py -3`, `%LOCALAPPDATA%\Programs\Python\…`, `FORGE_PYTHON`, or a local `python\` folder. First launch of the packaged desk opens a native **Choose your Forge workspace** folder picker when `%LOCALAPPDATA%\Forge\state.json` has no workspace yet. Loopback only (`127.0.0.1:43180`). No burst/5090 while Vast is live; farm-brain apply still needs desk QC confirm.

The File tab keeps an in-memory Monaco buffer (vendored locally — no CDN). Run `npm run vendor:monaco` once per dev tree; `dist:win` vendors automatically. **Save** or Ctrl+S writes via `PUT /api/file`. Switching files with unsaved edits asks before discarding.

**Double-click Forge** on the Desktop. The desk is `http://127.0.0.1:43180`.

One command (installs Electron if needed, then opens the desk; Edge app window if Electron is missing):

```powershell
.\scripts\launch-forge.ps1
```

or `.\scripts\launch-forge.cmd`. Failures append to `%LOCALAPPDATA%\Forge\launch.log`.

## Canned farm checks (for local coder)

The local coder should **not invent** farm status. Use rigid boards:

| Command | What it probes |
|---------|----------------|
| `forge check farm` | Dashboard `/health` + fleet online |
| `forge check llm` | CUDA 3.8 + AMD Empero + coder warm; Empero not on CUDA |
| `forge check temps` | EVO 5070 Ti + CPU, tower 5090 + 5950X, BC-250 dials (5090 blocked-for-Vast → WARN) |
| `forge check apps` | ARIA, AI-PM, ontology, Ray, Blender `:9876`, tower Ollama |
| `forge check vpn` | Same as farm+apps (Meshnet = reach `.103` off-LAN) |
| `forge check ray` | Ray head GCS `:6379` + dashboard `:8265` + jobs API + worker modes |
| `forge check all` | Combined board |

Skill for the desk agent: `.agents/skills/farm-check/SKILL.md`.

## CLI

`Install-Forge-Shortcut.ps1` adds this folder to your user PATH so `forge` works in new terminals.

```bat
forge
forge which
forge health
forge log
forge status
forge status --json
forge check list
forge check all
forge check farm
forge check llm
forge check temps
forge check apps
forge check vpn
forge check ray
forge check cams
forge check all --json
forge models -q
forge use
forge use chat --model qwen3.8:27b
forge open C:\Users\jlay\Grok\forge
forge ask "What does cli.py do?" --file src/forge/cli.py
forge edit "Add a --quiet flag to status" --file src/forge/cli.py
forge edit "Add a --quiet flag to status" --file src/forge/cli.py --helper review
forge compare ask "What does cli.py do?" --file src/forge/cli.py
forge compare edit "Add a --quiet flag" --file src/forge/cli.py --model qwen3-coder:30b --model qwen3.8:27b
forge recipe list
forge recipe run farm-status
forge launch vault
forge launch aether --url https://example.org/page
forge launch lumen --url /compliance/deviation
forge vault "agentrx"
forge vault "agentrx"
forge vault --open 01-Daily/Agent-Readout.md
forge git
forge git diff src/forge/cli.py
forge git commit -m "message"
forge telegram --probe
forge telegram --text "/forge status"
```

`forge ask` uses the **Ask** (EVO CUDA) model. `forge edit` uses the **Code** (EVO AMD) model. `forge use` with no args lists live `/api/tags` and, on a TTY, lets you pick a number. `forge models --pick` is the same picker. Burst/5090 stays blocked while Vast is live.

`forge compare ask|edit` runs the same prompt on up to 3 live models, then **qwen3-coder-next:latest** on EVO AMD `:11437` picks a winner. Desk: check models under the composer, then **Compare ask** / **Compare edit**. The winner line is shown (not applied). **Helpers** (Review/Check) are separate from Compare — optional ticks under Go after Edit. farm-brain Apply still needs the desk QC confirm (CLI: `--i-understand-qc`).

Bare `forge` prints the pinned session and help. `forge health` checks the local Python finder and Monaco vendor without starting the desk. `forge log` tails `%LOCALAPPDATA%\Forge\sessions.jsonl` (newest first; `--json` for scripts). Turns are appended from **both** the CLI and the desk (Ask / Edit / recipes). The desk **Log** tab lists the same file.

`forge ask` and `forge edit` **stream tokens** as they arrive (`stream: true` to Ollama). The desk Chat pane does the same over `/api/ask/stream` and `/api/edit/stream`. `--json` still waits for the full object.

`forge git` prints local status (branch, changed paths, remotes if any). `forge git diff [path]` prints a unified diff, including untracked files. `forge git commit -m "message"` commits locally. There is **no push, no PR, and no remote is invented**. Ghost Project rows (missing folders, leftover `forge-w7-farm-brain`, `%TEMP%\farm-brain`) are dropped on load.

`forge telegram` is a **Legion-only** `/forge` alias. It shells `forge.cmd` on this PC. Do not add it to Farm Brain (`/coder` stays on EVO). Token: `FORGE_TELEGRAM_TOKEN` or `C:\Users\jlay\secrets\forge_telegram_token.txt`. Allowlist: `FORGE_TELEGRAM_ALLOW` or `forge_telegram_allow.txt`. Probe with `forge telegram --probe`. Live poll needs the token file — without it, use the desk or CLI on Legion. Poll with `forge telegram` or `scripts\forge-telegram.cmd`. Burst/edit/apply are refused.

`forge edit` may call **read / list / grep** on the workspace first (no shell). It then prints a unified diff, a **change list**, and numbered **hunks**. `[y/N]` applies the whole reply; `--hunk 0 --hunk 2` writes only those hunks. `farm-brain` apply is blocked unless you pass `--i-understand-qc` — the existing coder QC gate still applies. Check multiple files in the desk (or pass `--file` more than once) so one edit can name several paths.

## Routing

| Tier | Host | GPU | Default model |
|---|---|---|---|
| `code` | `192.168.68.103:11437` | Strix Halo GTT | `qwen3-coder-next:latest` |
| `chat` | `192.168.68.103:11434` | RTX 5070 Ti | `qwen3.8:27b` |
| `burst` | `192.168.68.106:11434` | RTX 5090 | `aria-qwen38:27b` |

Inventory is live (`/api/tags`, `/api/ps`, Farm Brain `/health`, `/api/fleet/status`, `/api/compute/dials`). Forge does not fork `llm_models.toml`.

Farm API calls send `X-Farm-Local-Key` from `FORGE_FARM_TOKEN` or `C:\Users\jlay\secrets\farm_operator_token.txt`.

## Desk panes

1. **Project** — workspace, file tree with breadcrumbs and `..`, path search, checkboxes to **name multiple files** for Ask/Edit, thin **Git** status / diff / local commit, **Vault** search of `C:\Users\jlay\Documents\FarmBrainVault` (named notes + open in Obsidian), vault / Aether / Lumen / AI-PM / Farm Brain launchers. Search and the tree return paths only; Ask/Edit still send only the named files you check, never the whole repo. Vault search is notes in the Obsidian vault — it does not add those notes to Ask/Edit. Electron **Open workspace** uses the native folder picker (browser/prompt fallback). Git is local only: no push, no PR flow, no invented remotes. Untracked files and empty history are shown; Commit writes a local commit from the listed paths.
2. **Session** — Chat streams ask/edit tokens live. **Ask** is Q&A only — it will not create files and should not suggest shell commands (`touch`, `bash`, etc.). To create or change files, use **Edit** with named files checked, then **Apply hunk** (or Apply remaining). **Log** is `%LOCALAPPDATA%\Forge\sessions.jsonl` (CLI + desk). **Term** is a local `cmd` pane in the workspace for Jeff — the model cannot see it and still has no shell tool. **Edit** can call read/list/grep (no shell) and shows those tool lines in the bubble. After **Edit**, the Diff tab lists every file and each **hunk** with Apply hunk / Reject hunk. **Apply remaining** writes pending hunks; Reject drops the reply. Git diffs stay review-only. A **farm-brain** workspace shows the QC banner and a desk confirm (checkbox + Confirm apply) before any write — Forge will not auto-apply; `window.confirm` is not the gate. CLI still needs `--i-understand-qc`. Header **Code** / **Ask** dropdowns are live Ollama tags (AMD vs CUDA). Edit uses Code; Ask uses the question model.
3. **Mesh** — live pulse every 20s (timestamp + pulsing dot). **Aether / Lumen last-URL handoff** (sibling tools — Forge does not embed them). EVO/Tower Ollama hosts plus live **BC-250** boards from Farm Brain `/api/compute/dials` (not a static host list). Drag an EVO/Tower model onto a project to assign it. BC-250 pills are inventory only. Tower **5090** shows a **blocked** badge and cannot be assigned while Vast is live. **Ray** status + last jobs deep-link to the Ray Dashboard (`:8265`) and Farm Brain Compute; **Ontology** (`:8000`) is the SQLite world model, not a Ray job graph.

State lives in `%LOCALAPPDATA%\Forge\state.json`.
