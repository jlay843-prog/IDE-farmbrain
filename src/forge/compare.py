"""Run the same ask/edit on up to 3 live models; AMD coder-next judges."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from forge.edit import change_list
from forge.probe import picker_snapshot
from forge.session import SessionError, active_session, run_ask, run_edit
from forge.state import load_state

JUDGE_TIER = "code"
JUDGE_MODEL = "qwen3-coder-next:latest"
MAX_CANDIDATES = 3
_WINNER_RE = re.compile(r"winner\s*[:=]\s*(\d+)", re.I)
_REASON_RE = re.compile(r"reason\s*[:=]\s*(.+)", re.I)


def parse_verdict(text: str, n: int) -> dict[str, Any]:
    winner = None
    reason = ""
    for line in (text or "").splitlines():
        hit = _WINNER_RE.search(line)
        if hit:
            winner = int(hit.group(1))
        why = _REASON_RE.search(line)
        if why and not reason:
            reason = why.group(1).strip()
    if winner is None or winner < 1 or winner > n:
        return {
            "winner": 1,
            "reason": reason or "Judge did not return a valid WINNER line; using the first successful answer.",
            "parsed": False,
        }
    return {"winner": winner, "reason": reason or (text or "").strip()[:400], "parsed": True}


def match_live_model(name: str, *, preferred: str | None = None, picker: dict[str, Any] | None = None) -> dict[str, Any]:
    picker = picker or picker_snapshot()
    want = (name or "").strip()
    if not want:
        raise SessionError("empty model name")
    rows: list[dict[str, Any]] = []
    for tier in ("code", "chat", "burst"):
        for row in (picker.get("groups") or {}).get(tier) or []:
            rows.append(row)
    exact = [r for r in rows if r.get("name") == want]
    prefix = want.split(":")[0]
    fuzzy = [r for r in rows if r.get("name") == want or str(r.get("name") or "").startswith(prefix)]
    pool = exact or fuzzy
    if preferred:
        ranked = [r for r in pool if r.get("tier") == preferred] or pool
    else:
        ranked = pool
    if not ranked:
        raise SessionError(f"{want} is not in live /api/tags talk inventory")
    choice = ranked[0]
    if choice.get("blocked"):
        raise SessionError("burst is blocked while Vast is active on the 5090")
    return choice


def default_candidates(kind: str, *, picker: dict[str, Any] | None = None, state: dict[str, Any] | None = None) -> list[dict[str, str]]:
    picker = picker or picker_snapshot()
    state = state if state is not None else load_state()
    seeds = [
        ("code", state.get("code_model") or "qwen3-coder-next:latest"),
        ("chat", state.get("chat_model") or "qwen3.8:27b"),
    ]
    if kind == "ask":
        seeds = list(reversed(seeds))
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for tier, name in seeds:
        try:
            row = match_live_model(name, preferred=tier, picker=picker)
        except SessionError:
            continue
        key = f"{row['tier']}:{row['name']}"
        if key in seen:
            continue
        seen.add(key)
        out.append({"tier": row["tier"], "model": row["name"]})
        if len(out) >= MAX_CANDIDATES:
            return out
    for tier in ("code", "chat"):
        for row in (picker.get("groups") or {}).get(tier) or []:
            key = f"{row['tier']}:{row['name']}"
            if key in seen or row.get("blocked"):
                continue
            seen.add(key)
            out.append({"tier": row["tier"], "model": row["name"]})
            if len(out) >= MAX_CANDIDATES:
                return out
    return out


def _run_one(kind: str, prompt: str, files: list[str], spec: dict[str, str]) -> dict[str, Any]:
    tier = spec.get("tier")
    model = spec.get("model")
    if kind == "edit":
        return run_edit(prompt, files, apply=False, tier=tier, model=model)
    return run_ask(prompt, files, tier=tier, model=model)


def _judge(kind: str, prompt: str, files: list[str], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    judge = active_session(JUDGE_TIER, JUDGE_MODEL, purpose="edit")
    parts = [
        f"You are judging {len(candidates)} {kind} result(s) for the same farm-local prompt.",
        "Pick the single best outcome. Prefer a valid unified diff for edit. Prefer a correct, concise answer for ask.",
        "Reply with exactly:",
        "WINNER: <1-based index>",
        "REASON: <one short paragraph>",
        "",
        f"PROMPT:\n{prompt[:2000]}",
    ]
    if files:
        parts.append("FILES: " + ", ".join(files))
    for row in candidates:
        body = (row.get("text") or row.get("error") or "")[:8000]
        parts.append(f"\n--- CANDIDATE {row['index']} · {row.get('model')} · {row.get('backend')} ---\n{body}")
    reply = chat(judge["base"], judge["model"], [{"role": "user", "content": "\n".join(parts)}])
    ok_n = len(candidates)
    verdict = parse_verdict(reply["text"], ok_n)
    pick = next((c for c in candidates if c["index"] == verdict["winner"] and c.get("ok")), None)
    if pick is None:
        pick = next((c for c in candidates if c.get("ok")), candidates[0])
        verdict["winner"] = pick["index"]
        if not verdict.get("reason"):
            verdict["reason"] = "Fell back to the first successful candidate."
    return {
        "model": reply.get("model") or JUDGE_MODEL,
        "tier": JUDGE_TIER,
        "backend": judge["backend"]["id"],
        "gpu": judge["backend"]["gpu"],
        "base": judge["base"],
        "text": reply["text"],
        "winner": verdict["winner"],
        "reason": verdict["reason"],
        "parsed": verdict["parsed"],
        "pick_model": pick.get("model"),
        "pick_text": pick.get("text") or "",
    }


def run_compare(
    kind: str,
    prompt: str,
    files: list[str] | None = None,
    models: list[dict[str, str]] | list[str] | None = None,
) -> dict[str, Any]:
    kind = (kind or "ask").strip().lower()
    if kind not in {"ask", "edit"}:
        raise SessionError("compare kind must be ask|edit")
    prompt = (prompt or "").strip()
    if not prompt:
        raise SessionError("compare needs a prompt")
    picker = picker_snapshot()
    specs: list[dict[str, str]] = []
    if models:
        for raw in models[:MAX_CANDIDATES]:
            if isinstance(raw, str):
                row = match_live_model(raw, picker=picker)
                specs.append({"tier": row["tier"], "model": row["name"]})
            elif isinstance(raw, dict) and raw.get("model"):
                preferred = raw.get("tier")
                row = match_live_model(str(raw["model"]), preferred=preferred, picker=picker)
                specs.append({"tier": row["tier"], "model": row["name"]})
    else:
        specs = default_candidates(kind, picker=picker)
    # unique, cap
    uniq: list[dict[str, str]] = []
    seen: set[str] = set()
    for spec in specs:
        key = f"{spec['tier']}:{spec['model']}"
        if key in seen:
            continue
        seen.add(key)
        uniq.append(spec)
        if len(uniq) >= MAX_CANDIDATES:
            break
    if len(uniq) < 2:
        raise SessionError("compare needs at least two live models (up to 3)")
    named = files or []
    by_index: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=len(uniq)) as pool:
        futs = {pool.submit(_run_one, kind, prompt, named, spec): (i, spec) for i, spec in enumerate(uniq, start=1)}
        for fut in as_completed(futs):
            i, spec = futs[fut]
            try:
                result = fut.result()
                by_index[i] = {
                    "index": i,
                    "ok": True,
                    "tier": result.get("tier"),
                    "model": result.get("model"),
                    "backend": result.get("backend"),
                    "gpu": result.get("gpu"),
                    "base": result.get("base"),
                    "text": result.get("text") or "",
                    "error": None,
                }
            except Exception as exc:  # noqa: BLE001 — one candidate may fail
                by_index[i] = {
                    "index": i,
                    "ok": False,
                    "tier": spec.get("tier"),
                    "model": spec.get("model"),
                    "backend": None,
                    "gpu": None,
                    "base": None,
                    "text": "",
                    "error": str(exc),
                }
    candidates = [by_index[i] for i in range(1, len(uniq) + 1)]
    winners = [c for c in candidates if c.get("ok")]
    if not winners:
        raise SessionError("every compare candidate failed")
    judge = _judge(kind, prompt, named, candidates)
    return {
        "ok": True,
        "kind": kind,
        "prompt": prompt,
        "files": named,
        "applied": False,
        "candidates": candidates,
        "judge": judge,
        "model": judge.get("pick_model"),
        "text": judge.get("pick_text") or "",
        "changes": change_list(judge.get("pick_text") or "") if kind == "edit" else [],
        "backend": judge.get("backend"),
        "gpu": judge.get("gpu"),
        "tier": kind,
    }
