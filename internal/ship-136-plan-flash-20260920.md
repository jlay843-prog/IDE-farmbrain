# Ship 1.3.6 — Plan helper (5090 flash) + coder-next lead

- **Branch:** cursor/forge-helpers-135-2bcb
- **Version:** 1.3.6

## Probe (live)

| Backend | Tags / loaded | Notes |
|---------|---------------|-------|
| CUDA `:11434` | `qwen3.8:27b-q4_K_M` loaded (~14GB VRAM) | Normal Ask unchanged |
| AMD `:11437` | `qwen3-coder-next:latest` + `empero-35b-a3b:q4km` loaded | Lead Code + Review |
| Tower `:11434` Ollama | Q8 control tags; `/api/ps` empty | Not flash home |
| Tower `:11435` llama.cpp | **`qwen3.8-flash-next`** via EVO SSH (`forge check llm` PASS) | ~16 t/s per Jeff; direct from Legion times out |

## Helpers

- **plan**: 5090 flash Ask-only (no files) → augments prompt → lead **Code** `qwen3-coder-next:latest`
- **review**: Empero sequential after edit (unchanged)
- **check**: 5090 flash after edit; skipped when plan already used 5090
- Desk: Plan / Review / Check ticks; CLI `--helper plan|review|check`

## Links (`/api/links`)

- Farm Brain http://192.168.68.103:5000
- Ray http://192.168.68.103:8265
- Lumen http://192.168.68.103:8100
- Vault `C:\Users\jlay\Documents\FarmBrainVault`
- Aether handoff via `%LOCALAPPDATA%\Aether\data\forge-handoff.json`

## Mesh

- `vast_active: false` (5090 not blocked)
