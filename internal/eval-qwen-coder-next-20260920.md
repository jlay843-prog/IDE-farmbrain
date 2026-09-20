# Eval: Jeff model stack change (2026-09-20)

Evaluate-only. No version bump, no dist-win, no Ollama keep-warm edits.

## Live Ollama tags

| Tag | Host | Port | Loaded (`/api/ps`) | Notes |
|---|---|---|---|---|
| `qwen3-coder-next:latest` | EVO AMD | 11437 | **yes** | 79.7B Q4_K_M; ~52.1 GiB VRAM; ctx 16384 |
| `empero-35b-a3b:q4km` | EVO AMD | 11437 | **yes** | ~19.8 GiB VRAM; ctx 8192 |
| `qwen3-coder:30b` | EVO AMD | 11437 | no | Still in `/api/tags`; not warm |
| `qwen3.8:27b-q4_K_M` | EVO CUDA | 11434 | no (was warm earlier) | Chat default variant |
| `nomic-embed-text:latest` | EVO CUDA | 11434 | yes | Embed only |
| `empero-35b-a3b:q4km` | EVO CUDA | 11434 | **no** | Tag present; **not loaded** — placement OK |
| `qwen3.8:27b-q8_0` | Tower 5090 | 11434 | no | Tower idle |
| `aria-qwen38:27b` | Tower 5090 | 11434 | no | Burst default in Forge |
| **No `*next*flash*` tag** | Tower | 11434 | — | Jeff's desired 3.8 next flash **not pulled** |

Tower host per Forge Mesh: `192.168.68.106:11434` (not `.104`).

## Empero placement

- **AMD :11437** — loaded with coder-next (both warm).
- **CUDA :11434** — tag exists in inventory only; `/api/ps` empty for Empero.
- `forge check llm` → `PASS empero_placement`.

## Memory pressure (AMD dual warm)

From `/api/ps` size_vram sums:

- Empero: ~21.3 GB
- coder-next: ~52.1 GB
- **Combined ~73.4 GB** on Strix Halo GTT

Both models coexist without unloading each other. Context windows reduced vs single-model (Empero 8192, coder-next 16384).

## Forge defaults vs Jeff pins

| Source | Code default | Chat default | Burst |
|---|---|---|---|
| `state.py` / `hosts.py` / `probe.PICKER_DEFAULTS` | `qwen3-coder:30b` | `qwen3.8:27b` | `aria-qwen38:27b` |
| `checks.EXPECT_AMD_CODER` | `qwen3-coder:30b` (hard-coded; `_has_model` requires `"30b"`) | — | — |
| `%LOCALAPPDATA%\Forge\state.json` (after trial) | `qwen3-coder-next:latest` | `qwen3.8:27b` | — |

Jeff can point Code at `qwen3-coder-next:latest` via `forge use` / desk picker **without** unloading Empero. Forge repo defaults still pin 30b until updated.

Project registry: `forge` project still `qwen3-coder:30b`; `docs` project updated to coder-next during trial.

## Picker (`forge models --pick` / picker_snapshot)

- **code**: `qwen3-coder-next:latest` (loaded, first), `empero-35b-a3b:q4km` (loaded), `qwen3-coder:30b`, cross-host extras (`aria-qwen38:27b`, `deepseek-r1:14b`, `qwen2.5:14b`, `qwen3.8:27b`).
- **chat**: CUDA qwen3.8 variants + others on EVO.
- **burst**: tower tags including `qwen3.8:27b-q8_0`, `aria-qwen38:27b`, etc. — **no next-flash tag**.

Picker default label still shows `qwen3-coder:30b` even though coder-next sorts first when loaded.

## Vast / 5090 gate

- `forge status` / mesh: `vast_active: false`
- `forge check all`: `tower_5090 … vast=False`; burst not blocked
- Tower Ollama up; nothing loaded

## Checks

```
forge check llm → FAIL (amd_coder expects qwen3-coder:30b; loaded coder-next)
forge check all → FAIL (amd_coder + transient cuda_warm during embed load)
```

Desk `127.0.0.1:43180` not running — `/api/check` and `/api/models` unreachable.

## Trial (CLI)

1. `forge use code --model qwen3-coder-next:latest` — OK, reachable AMD.
2. `forge ask … --tier code --model qwen3-coder-next:latest` — streamed on AMD; model **replied `qwen3-coder:30b`** (wrong self-ID, but no HTTP/tool-XML error).
3. `forge edit … --file FARM-CHECK-HANDOFF.md` — markup tool path worked (`TOOL_OK`, multiple `read` calls); no Ollama `<parameter>` XML choke. Exit 1 from non-TTY apply prompt only.

Forge disables native Ollama tools for all coders (`native_ollama_tools` → `None`); markup parsing path intact for 80b.

## Gaps for Jeff's target stack

1. **Forge constants** still default/check against `qwen3-coder:30b`.
2. **Tower 3.8 next flash** — tag not present on `192.168.68.106:11434`.
3. **project-context.md** routing table still lists `qwen3-coder:30b` for code tier.

No repo/Ollama changes made in this eval.
