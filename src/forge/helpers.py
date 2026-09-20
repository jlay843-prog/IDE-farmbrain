"""Forge Helpers — optional sequential second-pass after lead Edit.

review: Empero on AMD reviews the pending diff (Ask-only PASS/FAIL/WARN board).
check: 5090 flash model slot — WARN until a live tower tag is pulled.
"""

from __future__ import annotations

import re
from typing import Any

from forge.checks import format_board
from forge.llm import chat
from forge.probe import probe_backend
from forge.session import SessionError, active_session

REVIEW_MODEL = "empero-35b-a3b:q4km"
REVIEW_TIER = "code"
DEFAULT_CODE_MODEL = "qwen3-coder-next:latest"

_PASS_RE = re.compile(r"^\s*(PASS|FAIL|WARN)\b", re.I)
_RESULT_RE = re.compile(r"^\s*RESULT\s*[:=]\s*(PASS|FAIL|WARN)\b", re.I)


def probe_flash_tag() -> str | None:
    """Return a live tower tag name for 5090 flash — never invent one."""
    be = probe_backend("burst")
    if not be.get("ok"):
        return None
    names = [str(t.get("name") or "") for t in (be.get("tags") or []) if t.get("name")]
    # Prefer qwen3.8/next + flash style tags when several match.
    ranked: list[tuple[int, str]] = []
    for name in names:
        low = name.lower()
        if "flash" not in low:
            continue
        score = 0
        if "next" in low:
            score += 3
        if "qwen3" in low or "qwen3.8" in low:
            score += 2
        if "3.8" in low:
            score += 1
        ranked.append((score, name))
    if not ranked:
        return None
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return ranked[0][1]


def helper_catalog() -> list[dict[str, Any]]:
    flash_tag = probe_flash_tag()
    review = {
        "id": "review",
        "label": "Review (Empero)",
        "model": REVIEW_MODEL,
        "tier": REVIEW_TIER,
        "enabled": True,
        "status": "ready",
        "message": "",
    }
    check = {
        "id": "check",
        "label": "5090 flash check",
        "model": flash_tag or "",
        "tier": "burst",
        "enabled": flash_tag is not None,
        "status": "ready" if flash_tag else "warn",
        "message": "" if flash_tag else "flash not pulled",
    }
    return [review, check]


def _line(mark: str, label: str, detail: str) -> dict[str, str]:
    return {"mark": mark.upper(), "label": label, "detail": detail}


def _board(name: str, lines: list[dict[str, str]], *, note: str = "") -> dict[str, Any]:
    fails = sum(1 for row in lines if row["mark"] == "FAIL")
    warns = sum(1 for row in lines if row["mark"] == "WARN")
    if fails:
        result = "FAIL"
    elif warns:
        result = "WARN"
    else:
        result = "PASS"
    return {
        "helper": name,
        "check": name,
        "result": result,
        "lines": lines,
        "note": note,
        "board": "",
        "instruction_for_model": "Report these lines only. Do not invent PASS/FAIL.",
    }


def _finalize_board(board: dict[str, Any]) -> dict[str, Any]:
    board["board"] = format_board(board)
    return board


def parse_review_board(text: str) -> dict[str, Any]:
    lines: list[dict[str, str]] = []
    result = "WARN"
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        hit = _RESULT_RE.match(line) or _PASS_RE.match(line)
        if hit:
            result = hit.group(1).upper()
            label = "verdict"
            detail = line
        elif line.upper().startswith("SUMMARY:"):
            label = "summary"
            detail = line.split(":", 1)[-1].strip()
            result = result or "WARN"
        else:
            label = "note"
            detail = line
        lines.append(_line(result if label == "verdict" else "PASS", label, detail))
    if not lines:
        lines.append(_line("WARN", "review", "Empero did not return a PASS/FAIL/WARN board"))
        result = "WARN"
    board = _board("review", lines, note="Ask-only review of pending diff — not applied")
    board["result"] = result
    board["text"] = text or ""
    return _finalize_board(board)


def run_review_helper(
    diff: str,
    prompt: str,
    files: list[str] | None = None,
    *,
    changes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Sequential Ask on Empero — never runs in parallel with lead Edit."""
    if not (diff or "").strip():
        board = _board(
            "review",
            [_line("WARN", "review", "No pending diff to review")],
            note="Ask-only review — not applied",
        )
        return _finalize_board(board)
    sess = active_session(REVIEW_TIER, REVIEW_MODEL, purpose="ask")
    parts = [
        "You are reviewing a pending unified diff before Jeff applies it.",
        "Reply with a rigid board only — no prose outside these lines:",
        "RESULT: PASS|FAIL|WARN",
        "SUMMARY: <one short line>",
        "Then optional detail lines prefixed PASS, FAIL, or WARN.",
        "",
        f"PROMPT:\n{prompt[:2000]}",
    ]
    if files:
        parts.append("FILES: " + ", ".join(files))
    if changes:
        parts.append("CHANGE LIST: " + ", ".join(f"{c.get('mark', '?')} {c.get('path', '?')}" for c in changes))
    parts.append(f"\nPENDING DIFF:\n{diff[:12000]}")
    reply = chat(sess["base"], sess["model"], [{"role": "user", "content": "\n".join(parts)}])
    board = parse_review_board(reply.get("text") or "")
    board["model"] = reply.get("model") or REVIEW_MODEL
    board["backend"] = sess["backend"]["id"]
    board["gpu"] = sess["backend"]["gpu"]
    board["tier"] = REVIEW_TIER
    return board


def run_check_helper(
    diff: str,
    prompt: str,
    files: list[str] | None = None,
    *,
    changes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    flash_tag = probe_flash_tag()
    if not flash_tag:
        board = _board(
            "check",
            [_line("WARN", "flash", "flash not pulled on tower :11434")],
            note="5090 flash helper disabled until tag exists",
        )
        return _finalize_board(board)
    try:
        sess = active_session("burst", flash_tag, purpose="ask")
    except SessionError as exc:
        board = _board(
            "check",
            [_line("WARN", "flash", str(exc))],
            note="5090 flash helper could not reach tower model",
        )
        return _finalize_board(board)
    parts = [
        "You are a fast 5090 flash check on a pending unified diff.",
        "Reply with a rigid board only:",
        "RESULT: PASS|FAIL|WARN",
        "SUMMARY: <one short line>",
        "",
        f"PROMPT:\n{prompt[:1500]}",
    ]
    if files:
        parts.append("FILES: " + ", ".join(files))
    parts.append(f"\nPENDING DIFF:\n{diff[:8000]}")
    reply = chat(sess["base"], sess["model"], [{"role": "user", "content": "\n".join(parts)}])
    board = parse_review_board(reply.get("text") or "")
    board["helper"] = "check"
    board["check"] = "check"
    board["model"] = reply.get("model") or flash_tag
    board["backend"] = sess["backend"]["id"]
    board["gpu"] = sess["backend"]["gpu"]
    board["tier"] = "burst"
    board["note"] = f"5090 flash check via {flash_tag} — not applied"
    return _finalize_board(board)


def run_helpers(
    helper_ids: list[str],
    edit_result: dict[str, Any],
    prompt: str,
    files: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Run helpers sequentially after lead Edit completes."""
    ordered = []
    for hid in ("review", "check"):
        if hid in helper_ids:
            ordered.append(hid)
    for hid in helper_ids:
        if hid not in ordered:
            ordered.append(hid)
    diff = edit_result.get("text") or ""
    changes = edit_result.get("changes") or []
    out: list[dict[str, Any]] = []
    for hid in ordered:
        if hid == "review":
            out.append(run_review_helper(diff, prompt, files, changes=changes))
        elif hid == "check":
            out.append(run_check_helper(diff, prompt, files, changes=changes))
    return out
