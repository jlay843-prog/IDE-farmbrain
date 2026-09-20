---
name: farm-check
description: >
  Canned Lone Tree Acres farm status boards for Forge / local qwen3-coder-next.
  Use when Jeff asks status, VPN, temps, LLM warm, tunnels, farm OS health,
  or types /farm-status /farm-llm /farm-temps /farm-vpn /farm-apps.
---

# Farm canned checks (Forge)

You are a **low-reasoning** local coder. **Do not invent farm status.**

## Rule

1. Run **exactly one** shell command from the table below.
2. Paste the `CHECK` / `RESULT` / `LINES` / `SUMMARY` board back to Jeff.
3. If RESULT is FAIL, list the FAIL lines only — do not guess fixes unless Jeff asks.

## Commands

| Jeff says | Run |
|-----------|-----|
| status / what's up / farm check / `/farm-status` | `forge check all` |
| LLM / models warm / Empero / coder | `forge check llm` |
| temps / thermal / 5070 / 5090 / 5950X / BC-250 | `forge check temps` |
| VPN / Meshnet / tunnels / can I reach ARIA | `forge check vpn` |
| apps / AI-PM / ontology / blender | `forge check apps` |
| flock / cams / nest / chicken run | `forge check cams` |
| Ray / ray head / GCS / dashboard :8265 | `forge check ray` |
| dashboard / fleet only | `forge check farm` |
| what checks exist | `forge check list` |

JSON (for tools): `forge check all --json`

## Expected layout (do not "fix" by moving models)

- CUDA `:11434` = `qwen3.8:27b-q4_K_M` (chat / AI-PM)
- AMD `:11437` = `empero-35b-a3b:q4km` + `qwen3-coder-next:latest`
- Empero must **never** load on the 5070 Ti

## Recipes

```bat
forge recipe list
forge recipe run farm-status
forge recipe run farm-llm
forge recipe run farm-temps
forge recipe run farm-vpn
forge recipe run farm-ray
forge recipe run farm-cams
```
