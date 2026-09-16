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
forge compare ask "What does cli.py do?" --file src/forge/cli.py
forge compare edit "Add a --quiet flag" --file src/forge/cli.py --model qwen3-coder:30b --model qwen3.8:27b
forge recipe list
forge launch vault
forge git
forge git diff src/forge/cli.py
forge git commit -m "message"
```

`forge ask` uses the **Ask** (EVO CUDA) model. `forge edit` uses the **Code** (EVO AMD) model. `forge use` with no args lists live `/api/tags` and, on a TTY, lets you pick a number. `forge models --pick` is the same picker. Burst/5090 stays blocked while Vast is live.

`forge compare ask|edit` runs the same prompt on up to 3 live models, then **qwen3-coder:30b** on EVO AMD `:11437` picks a winner. Desk: check models under the composer, then **Compare ask** / **Compare edit**. The 30B pick is the WINNER line (not applied). farm-brain still needs QC confirm before Apply.

Bare `forge` prints the pinned session and help. Turns are appended to `%LOCALAPPDATA%\Forge\sessions.jsonl` from **both** the CLI and the desk (Ask / Edit / recipes). The desk **Log** tab lists recent turns from that file.

`forge ask` and `forge edit` **stream tokens** as they arrive (`stream: true` to Ollama). The desk Chat pane does the same over `/api/ask/stream` and `/api/edit/stream`. `--json` still waits for the full object.

`forge git` prints local status (branch, changed paths, remotes if any). `forge git diff [path]` prints a unified diff, including untracked files. `forge git commit -m "message"` commits locally. There is **no push, no PR, and no remote is invented**.

`forge edit` prints a unified diff, then a **change list** of every file in that reply (`M`/`A`/`D`, +/−, hunk counts), and asks `[y/N]` before writing. `farm-brain` apply is blocked unless you pass `--i-understand-qc` — the existing coder QC gate still applies. Check multiple files in the desk (or pass `--file` more than once) so one edit can name several paths.

## Routing

| Tier | Host | GPU | Default model |
|---|---|---|---|
| `code` | `192.168.68.103:11437` | Strix Halo GTT | `qwen3-coder:30b` |
| `chat` | `192.168.68.103:11434` | RTX 5070 Ti | `qwen3.8:27b` |
| `burst` | `192.168.68.106:11434` | RTX 5090 | `aria-qwen38:27b` |

Inventory is live (`/api/tags`, `/api/ps`, Farm Brain `/health`, `/api/fleet/status`, `/api/compute/dials`). Forge does not fork `llm_models.toml`.

Farm API calls send `X-Farm-Local-Key` from `FORGE_FARM_TOKEN` or `C:\Users\jlay\secrets\farm_operator_token.txt`.

## Desk panes

1. **Project** — workspace, file tree with breadcrumbs and `..`, path search, checkboxes to **name multiple files** for Ask/Edit, thin **Git** status / diff / local commit, vault / Aether / Lumen / AI-PM / Farm Brain launchers. Search and the tree return paths only; Ask/Edit still send only the named files you check, never the whole repo. Electron **Open workspace** uses the native folder picker (browser/prompt fallback). Git is local only: no push, no PR flow, no invented remotes. Untracked files and empty history are shown; Commit writes a local commit from the listed paths.
2. **Session** — Chat streams ask/edit tokens live. **Log** is `%LOCALAPPDATA%\Forge\sessions.jsonl` (CLI + desk). After **Edit**, the Diff tab lists every file in that one reply (`M`/`A`/`D`, +/− counts). Click a path to jump to that file’s hunks, then Apply or Reject the whole diff. Coder diffs still use Apply; git diffs are review-only in the Diff tab. Header **Code** / **Ask** dropdowns are live Ollama tags (AMD vs CUDA). Edit uses Code; Ask uses the question model.
3. **Mesh** — EVO/Tower Ollama hosts plus live **BC-250** boards from Farm Brain `/api/compute/dials` (not a static host list). Drag an EVO/Tower model onto a project to assign it. BC-250 pills are inventory only. **Ray** status + last jobs deep-link to the Ray Dashboard (`:8265`) and Farm Brain Compute; **Ontology** (`:8000`) is the SQLite world model, not a Ray job graph.

State lives in `%LOCALAPPDATA%\Forge\state.json`.
