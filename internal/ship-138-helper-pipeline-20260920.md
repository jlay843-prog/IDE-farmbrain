# Ship 1.3.8 — Helper pipeline Plan → Code → Review

## Symptom

Jeff: Code + Plan + Review, crop/code prompt. Desk jumped to review with "no pending diff to review."

## Root cause

Server order was already synchronous (plan → edit → review), but:

1. Review ran even when lead edit returned **no unified diff** — Empero board said "no pending diff."
2. Desk had no explicit **coding** / **review** phase markers — after slow plan stream, review board at `done` felt like a skip.
3. Prior agent `Stop-Process` during dist (1.3.7) — not this bug.

## Fix

- `has_pending_diff()` — review/check skip Empero/flash when coder produced no diff.
- SSE `phase: coding` before `run_edit`, `phase: review` before Empero.
- Desk banners: Planning → Coding → Review; clear plan text when coding starts.
- Post-edit helpers stream over SSE as they complete.
- `dist-win.ps1` warns if desk open; never Stop-Process Forge.

## Verify

`pytest tests/test_helpers.py::test_pipeline_plan_then_edit_then_review` — order `plan`, `edit`, `review`.
