# Ship 1.3.9 — Edit inspect SSE / thinking banner

## Symptom

Jeff on Easy Code (after Plan): desk meta showed **inspect round 3 of 7** but thinking banner vanished and body stayed empty during long coder-next load.

## Root cause

Desk treated inspect-round model tokens like normal chat: cleared inspect mode on first delta, overwrote meta during quiet gaps, and had no still-alive UI while SSE was quiet between tool rounds on the 80B model.

## Fix

- `inspectState` tracks round/max/detail; banner stays until unified diff (`---`) starts.
- Stream label: **Inspect round N of 7 — reading …** / **read|grep path**.
- Skip `ev.meta` updates while inspect active; client idle + server `alive` heartbeats.
- `dist-win.ps1`: skip shortcut refresh when desk open (warn only).

## Verify

`pytest tests/test_cli.py::test_desk_inspect_sse_keeps_thinking_banner`
