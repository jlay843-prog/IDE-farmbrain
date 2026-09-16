# Forge

Local Qwen coding desk for this farm LAN. **CLI is the product.** The Windows window is a thin visual shell around it.

Code stays on **EVO AMD `:11437` / `qwen3-coder:30b`**. Chat can use **EVO CUDA `:11434` / `qwen3.8:27b`**. The tower 5090 is burst-only and **blocked while Vast is live**. Do not port-forward Ollama.

Sibling to Aether, Lumen, Farm Brain, and AI-PM — not inside `lumen-lab-twin`.

## Windows desk

First-time setup:

```powershell
cd C:\Users\jlay\Grok\forge
npm install
.\deploy\windows\Install-Forge-Shortcut.ps1
```

That writes a Desktop / Start Menu shortcut that opens Electron with this folder as the app (so Forge does not collide with Aether).

**Double-click Forge** on the Desktop. The desk is `http://127.0.0.1:43180`.

One command (installs Electron if needed, then opens the desk; Edge app window if Electron is missing):

```powershell
.\scripts\launch-forge.ps1
```

or `.\scripts\launch-forge.cmd`. Failures append to `%LOCALAPPDATA%\Forge\launch.log`.

## CLI

`Install-Forge-Shortcut.ps1` adds this folder to your user PATH so `forge` works in new terminals.

```bat
forge
forge which
forge status
forge models -q
forge use
forge use chat --model qwen3.8:27b
forge open C:\Users\jlay\Grok\forge
forge ask "What does cli.py do?" --file src/forge/cli.py
forge edit "Add a --quiet flag to status" --file src/forge/cli.py
forge recipe list
forge launch vault
```

`forge ask` uses the **Ask** (EVO CUDA) model. `forge edit` uses the **Code** (EVO AMD) model. `forge use` with no args lists live `/api/tags` and, on a TTY, lets you pick a number. `forge models --pick` is the same picker. Burst/5090 stays blocked while Vast is live.

Bare `forge` prints the pinned session and help. Turns are appended to `%LOCALAPPDATA%\Forge\sessions.jsonl`.

`forge edit` prints a unified diff and asks `[y/N]` before writing. `farm-brain` apply is blocked unless you pass `--i-understand-qc` — the existing coder QC gate still applies.

## Routing

| Tier | Host | GPU | Default model |
|---|---|---|---|
| `code` | `192.168.68.103:11437` | Strix Halo GTT | `qwen3-coder:30b` |
| `chat` | `192.168.68.103:11434` | RTX 5070 Ti | `qwen3.8:27b` |
| `burst` | `192.168.68.106:11434` | RTX 5090 | `aria-qwen38:27b` |

Inventory is live (`/api/tags`, `/api/ps`, Farm Brain `/health`, `/api/fleet/status`, `/api/compute/dials`). Forge does not fork `llm_models.toml`.

Farm API calls send `X-Farm-Local-Key` from `FORGE_FARM_TOKEN` or `C:\Users\jlay\secrets\farm_operator_token.txt`.

## Desk panes

1. **Project** — workspace, file list, vault / Aether / Lumen / AI-PM / Farm Brain launchers
2. **Session** — ask, edit, apply/reject, Monaco file pane. Header **Code** / **Ask** dropdowns are live Ollama tags (AMD vs CUDA). Edit uses Code; Ask uses the question model.
3. **Mesh** — EVO/Tower Ollama hosts plus live **BC-250** boards from Farm Brain `/api/compute/dials` (not a static host list). Drag an EVO/Tower model onto a project to assign it. BC-250 pills are inventory only. **Ray** status + last jobs deep-link to the Ray Dashboard (`:8265`) and Farm Brain Compute; **Ontology** (`:8000`) is the SQLite world model, not a Ray job graph.

State lives in `%LOCALAPPDATA%\Forge\state.json`.
