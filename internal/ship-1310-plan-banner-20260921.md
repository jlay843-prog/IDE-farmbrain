# Ship 1.3.10 — Honest Plan banner

## Incident (Jeff)

Live desk v1.3.9, Code + Plan/Review/Check. UI showed **Coding** plus **inspect round 3 of 7** and never printed Plan text. Question: is Plan hiding under the Coding banner and still thinking?

## Probe (live 127.0.0.1:43180)

- `/api/health` **1.3.9** (packaged `dist\win-unpacked`). Did not stop.
- `/api/helpers` Plan **ready** (`qwen3.8-flash-next`).
- AMD `/api/ps`: `qwen3-coder-next:latest` resident (~52GB) — inspect is on AMD, not the 5090.
- `sessions.jsonl` has no helper ids (1.3.9) and no completion row for the in-flight turn. Last completed edit 2026-09-21T02:05:31Z.

## Answer

Plan is **not** still thinking once inspect round N is on screen. Helpers are sequential: flash Plan finishes (or WARNs) **before** `run_edit` / inspect. The banner lied.

## Root cause

1. **1.3.8** cleared the Plan bubble when SSE `phase: coding` arrived, so Plan text vanished as soon as coder-next started.
2. **1.3.9** `alive` heartbeats were `{alive: true, phase: "coding"}`. The desk treated those as a Plan→Code **transition**, wiping Plan again and resetting inspect every 15s. Meta could still say inspect round 3 while the banner said Coding.
3. Client `coding: useCode` was true from Go, so 20s of quiet during flash first-token showed **Coding…** while Plan was still on `:11435`.

## Fix (source 1.3.10 — not packed; desk left running)

- Heartbeats carry the **current** phase (`plan` then `coding`). Early Plan meta before flash tokens.
- `isCodingPhase` ignores `alive`. Idle/alive during Plan keep **Planning on 5090 flash…**.
- Plan tokens stay in `.plan-block` above inspect.
- `sessions.jsonl` records `helpers` / `helper_results`.
- Check still skipped when Plan used the 5090 (`skip_flash_check`).

Unsigned `dist-win` skipped: Forge is running.
