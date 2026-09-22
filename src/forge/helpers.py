"""Forge Helpers — optional passes around lead Edit.

plan:   5090 flash plans first (Ask-only, no files) then coder-next edits.
review: Empero on AMD reviews the pending diff (Ask-only PASS/FAIL/WARN board).
assure: GATE.md scan of added lines (Ask-only; no apply, no exploits).
check:  5090 flash check after edit — skipped when plan already used the 5090.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from forge.checks import format_board
from forge.context import resolve_under
from forge.flash import FLASH_MODEL, flash_chat, probe_flash_tag
from forge.llm import chat
from forge.session import SessionError, active_session
from forge.state import workspace_path

REVIEW_MODEL = "empero-35b-a3b:q4km"
REVIEW_TIER = "code"
ASSURE_MODEL = "local"
ASSURE_TIER = "local"
DEFAULT_CODE_MODEL = "qwen3-coder-next:latest"

_DUMMY_SECRET_VALUES = {
    "changeme",
    "dummy",
    "example",
    "password",
    "placeholder",
    "secret",
    "todo",
    "token",
    "xxx",
    "your-token-here",
}
_SECRET_ASSIGN_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?key|auth[_-]?token|password|passwd|private[_-]?key|secret|token)\b"
    r".{0,40}[=:].{0,12}(['\"])([^'\"]{8,})\2"
)
_AWS_KEY_RE = re.compile(r"AKIA[0-9A-Z]{16}")
_PEM_HEADER_RE = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
_EVAL_EXEC_RE = re.compile(r"\b(?:eval|exec)\s*\(")
_TRAVERSAL_RE = re.compile(r"(?:^|[/\\])\.\.(?:[/\\]|$)")
_BIND_PUBLIC_RE = re.compile(r"0\.0\.0\.0")
_STUB_VERIFIER_RE = re.compile(
    r"(?i)return\s+true\b.{0,80}(?:placeholder|for now|assume|not a control)"
    r"|(?:placeholder|for now|assume).{0,80}return\s+true\b"
    r"|(?:function|def|const)\s+\w*(?:verify|validat|authent)\w*[^\n]{0,120}return\s+true\b"
)
_HEADER_IS_PROOF_RE = re.compile(
    r"(?i)header is proof|no further validation|verification succeeds if.{0,40}header"
    r"|assume .{0,60}(?:header|verif)"
)
_INVENTED_CRYPTO_RE = re.compile(
    r"(?i)invent.{0,40}(?:signature|cryptograph|verifier)"
    r"|(?:stub|placeholder|todo|fake)\s+(?:signature|hmac|crypto|verifier)"
)
_DEPLOY_RESTART_RE = re.compile(
    r"(?i)(?:systemctl\s+restart|Restart-Service\b|kubectl\s+apply|docker\s+compose\s+up\b|deploy\s+to\s+prod)"
)
_BLOCK_HEALTH_RE = re.compile(
    r"(?i)(?:deny|block|reject|forbid).{0,48}(?:/health\b|127\.0\.0\.1)"
    r"|(?:/health\b|127\.0\.0\.1).{0,48}(?:deny|block|reject|forbid)"
)
_GATE_PATH = Path(__file__).with_name("GATE.md")
_ASSURE_NOTE = (
    "Ask-only. Added lines only. GATE.md — not applied. No exploits. "
    "After Accept, smoke the program's existing health URL; the coder does not call the network."
)
_ASSURE_PASS = (
    "No stub verifier, header-as-proof, repeated line, secret, dynamic eval, "
    "or path that leaves the workspace"
)

PLAN_SYSTEM = (
    "You are the Forge planning model on tower 5090 flash (qwen3.8-flash-next). "
    "Reply with implementable JSON only — no markdown fence, no vibe, no unified diff, no slogans. "
    "Required keys: goal (one sentence), files (array of exact relative paths — never 'the codebase'), "
    "edits (array of objects with path and change: function/symbol and what to change), "
    "tests (array of short checks), risks (array). "
    "If the user already sketched plan JSON, fill missing paths and edits; do not replace it with vague bullets."
)

PLAN_IMPLEMENT = (
    "After inspect (read/list/grep), emit ONE unified diff (--- a/ +++ b/ @@ hunks) that performs those file edits. "
    "Do not reply with JSON, a new plan, TOOL_OK, or prose-only. "
    "Create missing files with --- /dev/null and +++ b/relative/path."
)

_PASS_RE = re.compile(r"^\s*(PASS|FAIL|WARN)\b", re.I)
_RESULT_RE = re.compile(r"^\s*RESULT\s*[:=]\s*(PASS|FAIL|WARN)\b", re.I)


def helper_catalog() -> list[dict[str, Any]]:
    flash_tag = probe_flash_tag()
    plan = {
        "id": "plan",
        "label": "Plan (5090 flash)",
        "model": flash_tag or FLASH_MODEL,
        "tier": "flash",
        "enabled": flash_tag is not None,
        "status": "ready" if flash_tag else "warn",
        "message": "" if flash_tag else "flash not reachable on :11435",
    }
    review = {
        "id": "review",
        "label": "Review (Empero)",
        "model": REVIEW_MODEL,
        "tier": REVIEW_TIER,
        "enabled": True,
        "status": "ready",
        "message": "",
    }
    assure = {
        "id": "assure",
        "label": "Assure (GATE.md)",
        "model": ASSURE_MODEL,
        "tier": ASSURE_TIER,
        "enabled": True,
        "status": "ready",
        "message": "added lines only — GATE.md",
    }
    check = {
        "id": "check",
        "label": "5090 flash check",
        "model": flash_tag or "",
        "tier": "flash",
        "enabled": flash_tag is not None,
        "status": "ready" if flash_tag else "warn",
        "message": "" if flash_tag else "flash not reachable on :11435",
    }
    return [plan, review, assure, check]


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


def run_plan_helper(
    prompt: str,
    *,
    history: list | None = None,
    on_delta: Callable[[str], None] | None = None,
    on_begin: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Ask-only plan on tower flash — no workspace files."""
    flash_tag = probe_flash_tag()
    if not flash_tag:
        board = _board(
            "plan",
            [_line("WARN", "flash", "flash not reachable on tower :11435")],
            note="5090 plan helper disabled until flash is live",
        )
        return _finalize_board(board)
    parts = [f"PROMPT:\n{prompt[:4000]}"]
    if history:
        tail = []
        for turn in history[-6:]:
            if isinstance(turn, dict) and turn.get("content"):
                role = str(turn.get("role") or "user").upper()
                tail.append(f"{role}: {str(turn['content'])[:800]}")
        if tail:
            parts.append("RECENT CHAT:\n" + "\n".join(tail))
    if on_begin:
        on_begin(
            {
                "model": flash_tag,
                "backend": "flash",
                "gpu": "RTX 5090",
                "tier": "flash",
                "phase": "plan",
            }
        )
    try:
        reply = flash_chat(
            "\n\n".join(parts),
            model=flash_tag,
            system=PLAN_SYSTEM,
            max_tokens=1800,
            on_delta=on_delta,
        )
    except RuntimeError as exc:
        board = _board("plan", [_line("WARN", "flash", str(exc))], note="5090 plan helper failed")
        return _finalize_board(board)
    text = reply.get("text") or ""
    board = {
        "helper": "plan",
        "check": "plan",
        "result": "PASS" if text.strip() else "WARN",
        "lines": [_line("PASS" if text.strip() else "WARN", "plan", (text.strip()[:240] or "empty plan") + ("…" if len(text.strip()) > 240 else ""))],
        "note": f"5090 flash plan via {flash_tag} — Ask-only, no files",
        "text": text,
        "model": reply.get("model") or flash_tag,
        "backend": reply.get("backend") or "flash",
        "gpu": reply.get("gpu") or "RTX 5090",
        "tier": "flash",
        "board": "",
    }
    if text.strip():
        board["lines"].append(_line("PASS", "via", str(reply.get("via") or "direct")))
    return _finalize_board(board)


_PLAN_JSON_RE = re.compile(r"\{[\s\S]*\}")


def parse_plan_files(text: str) -> list[str]:
    """Relative paths from plan JSON files[] / edits[].path. Drops abs, drive, and .. paths."""
    blob = (text or "").strip()
    if not blob:
        return []
    data: Any = None
    candidate = blob
    if "```" in candidate:
        for chunk in candidate.split("```"):
            body = chunk.strip()
            if body.lower().startswith("json"):
                body = body[4:].lstrip()
            if body.startswith("{"):
                candidate = body
                break
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        hit = _PLAN_JSON_RE.search(blob)
        if hit:
            try:
                data = json.loads(hit.group(0))
            except json.JSONDecodeError:
                data = None
    paths: list[str] = []
    if isinstance(data, dict):
        files = data.get("files") or []
        if isinstance(files, str):
            files = [files]
        if isinstance(files, list):
            for item in files:
                if isinstance(item, str) and item.strip():
                    paths.append(item.strip())
                elif isinstance(item, dict) and item.get("path"):
                    paths.append(str(item["path"]).strip())
        edits = data.get("edits") or []
        if isinstance(edits, list):
            for item in edits:
                if isinstance(item, dict) and item.get("path"):
                    paths.append(str(item["path"]).strip())
    else:
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("FILES:"):
                rest = stripped.split(":", 1)[-1]
                for part in rest.split(","):
                    token = part.strip().strip("- ")
                    if token:
                        paths.append(token)
    out: list[str] = []
    for raw in paths:
        rel = raw.replace("\\", "/").strip()
        while rel.startswith("./"):
            rel = rel[2:]
        rel = rel.strip("/")
        if not rel or rel.startswith("/") or ":" in rel:
            continue
        parts = [part for part in rel.split("/") if part not in {"", "."}]
        if not parts or any(part == ".." for part in parts):
            continue
        rel = "/".join(parts)
        if rel not in out:
            out.append(rel)
    return out


def named_files_for_plan(
    files: list[str] | None,
    plan_board: dict[str, Any],
    *,
    workspace: Path | None = None,
) -> list[str]:
    """Keep Jeff's named files; add plan paths that already exist under the workspace."""
    out = [item for item in (files or []) if item]
    root = workspace if workspace is not None else workspace_path()
    if root is None:
        return out
    for rel in parse_plan_files(str(plan_board.get("text") or "")):
        if rel in out:
            continue
        try:
            path = resolve_under(root, rel)
        except ValueError:
            continue
        if path.is_file():
            out.append(rel)
    return out


def augment_prompt_with_plan(prompt: str, plan_board: dict[str, Any]) -> str:
    plan_text = (plan_board.get("text") or "").strip()
    if not plan_text:
        return prompt
    return (
        f"{prompt}\n\n"
        "PLAN (5090 flash — implement this; do not reprint the plan):\n"
        f"{plan_text[:8000]}\n\n"
        f"{PLAN_IMPLEMENT}"
    )


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
            [_line("WARN", "flash", "flash not reachable on tower :11435")],
            note="5090 flash helper disabled until tag exists",
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
    try:
        reply = flash_chat("\n\n".join(parts), model=flash_tag, max_tokens=900, temperature=0.1)
    except RuntimeError as exc:
        board = _board("check", [_line("WARN", "flash", str(exc))], note="5090 flash check failed")
        return _finalize_board(board)
    board = parse_review_board(reply.get("text") or "")
    board["helper"] = "check"
    board["check"] = "check"
    board["model"] = reply.get("model") or flash_tag
    board["backend"] = reply.get("backend") or "flash"
    board["gpu"] = reply.get("gpu") or "RTX 5090"
    board["tier"] = "flash"
    board["note"] = f"5090 flash check via {flash_tag} — not applied"
    return _finalize_board(board)


def _redact_secret(value: str) -> str:
    text = (value or "").strip().strip("\"'")
    if len(text) <= 4:
        return "***"
    return f"{text[:2]}***{text[-1]}"


def _added_diff_lines(diff: str) -> list[tuple[str, str]]:
    """(path, added_line) for unified-diff plus lines. Ignores +++ headers."""
    path = ""
    out: list[tuple[str, str]] = []
    for raw in (diff or "").splitlines():
        if raw.startswith("+++ "):
            rest = raw[4:].strip()
            if rest.startswith("b/"):
                rest = rest[2:]
            path = rest
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            out.append((path, raw[1:]))
    return out


def _diff_new_paths(diff: str) -> list[str]:
    paths: list[str] = []
    for raw in (diff or "").splitlines():
        if not raw.startswith("+++ "):
            continue
        rest = raw[4:].strip()
        if rest.startswith("b/"):
            rest = rest[2:]
        if rest and rest != "/dev/null" and rest not in paths:
            paths.append(rest)
    return paths


def load_gate_text() -> str:
    """GATE.md beside this module — SSOT for Edit prompts and Assure rules."""
    try:
        return _GATE_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _leaves_workspace(path: str) -> bool:
    rel = (path or "").replace("\\", "/").strip()
    return bool(_TRAVERSAL_RE.search(rel) or rel.startswith("/") or (len(rel) >= 2 and rel[1] == ":"))


def scan_pending_diff(diff: str) -> list[dict[str, str]]:
    """GATE.md: added lines only. Never returns exploits or payloads."""
    findings: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def add(mark: str, label: str, detail: str) -> None:
        key = (mark, label, detail)
        if key in seen:
            return
        seen.add(key)
        findings.append(_line(mark, label, detail))

    for path in _diff_new_paths(diff):
        if _leaves_workspace(path):
            add("FAIL", "path", f"{path}: path that leaves the workspace")

    for path, line in _added_diff_lines(diff):
        loc = path or "diff"
        if _PEM_HEADER_RE.search(line):
            add("FAIL", "secrets", f"{loc}: a secret (private key, redacted)")
            continue
        aws = _AWS_KEY_RE.search(line)
        if aws:
            add("FAIL", "secrets", f"{loc}: a secret {_redact_secret(aws.group(0))}")
        assign = _SECRET_ASSIGN_RE.search(line)
        if assign:
            value = assign.group(3)
            if value.strip().lower() not in _DUMMY_SECRET_VALUES:
                add("FAIL", "secrets", f"{loc}: a secret {assign.group(1)}={_redact_secret(value)}")
        if _EVAL_EXEC_RE.search(line):
            add("FAIL", "eval", f"{loc}: dynamic eval")
        if _TRAVERSAL_RE.search(line.replace("\\", "/")):
            add("FAIL", "path", f"{loc}: path that leaves the workspace")
        if _STUB_VERIFIER_RE.search(line):
            add("FAIL", "stub", f"{loc}: stub verifier")
        if _HEADER_IS_PROOF_RE.search(line):
            add("FAIL", "proof", f"{loc}: a comment that a header is proof")
        if _INVENTED_CRYPTO_RE.search(line):
            add("FAIL", "crypto", f"{loc}: invented signature check, cryptography, or verifier")
        if _BIND_PUBLIC_RE.search(line):
            add("FAIL", "bind", f"{loc}: bind a new public address")
        if _DEPLOY_RESTART_RE.search(line):
            add("FAIL", "deploy", f"{loc}: deploy or restart a service")
        if _BLOCK_HEALTH_RE.search(line):
            add("FAIL", "health", f"{loc}: existing health route or 127.0.0.1 must stay open")
    repeats: dict[str, int] = {}
    for _path, line in _added_diff_lines(diff):
        text = line.strip()
        if len(text) < 24:
            continue
        repeats[text] = repeats.get(text, 0) + 1
    for _text, count in repeats.items():
        if count >= 2:
            add("FAIL", "repeat", f"same added line repeated {count} times")
            break
    return findings


def run_assure_helper(
    diff: str,
    prompt: str,
    files: list[str] | None = None,
    *,
    changes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Local defensive scan — Ask-only board, no apply, no attack procedures."""
    if not (diff or "").strip():
        board = _board(
            "assure",
            [_line("WARN", "assure", "No pending diff to assure")],
            note=_ASSURE_NOTE,
        )
        board["model"] = ASSURE_MODEL
        board["tier"] = ASSURE_TIER
        return _finalize_board(board)
    lines = scan_pending_diff(diff)
    extra_paths = [str(item) for item in (files or []) if item]
    extra_paths.extend(str(c.get("path") or "") for c in (changes or []) if c.get("path"))
    for path in extra_paths:
        if _leaves_workspace(path):
            lines.append(_line("FAIL", "path", f"{path}: path that leaves the workspace"))
    if not lines:
        lines = [_line("PASS", "assure", _ASSURE_PASS)]
    board = _board(
        "assure",
        lines,
        note=_ASSURE_NOTE,
    )
    board["model"] = ASSURE_MODEL
    board["backend"] = "local"
    board["gpu"] = ""
    board["tier"] = ASSURE_TIER
    return _finalize_board(board)


def has_pending_diff(edit_result: dict[str, Any]) -> bool:
    """True when lead Edit returned a unified diff Jeff can review or apply."""
    text = str(edit_result.get("text") or "").strip()
    if not text:
        return False
    changes = edit_result.get("changes") or []
    if changes:
        return True
    return "---" in text and "+++" in text


def run_helpers(
    helper_ids: list[str],
    edit_result: dict[str, Any],
    prompt: str,
    files: list[str] | None = None,
    *,
    skip_flash_check: bool = False,
    on_phase: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    """Run post-edit helpers sequentially after lead Edit completes."""
    ordered: list[str] = []
    for hid in ("review", "assure", "check"):
        if hid in helper_ids:
            ordered.append(hid)
    for hid in helper_ids:
        if hid not in ordered and hid != "plan":
            ordered.append(hid)
    diff = edit_result.get("text") or ""
    changes = edit_result.get("changes") or []
    out: list[dict[str, Any]] = []
    if not has_pending_diff(edit_result):
        for hid in ordered:
            if hid == "review":
                out.append(
                    _finalize_board(
                        _board(
                            "review",
                            [_line("WARN", "review", "Skipped — lead edit produced no pending diff")],
                            note="Plan → code → review; review waits for coder diff",
                        )
                    )
                )
            elif hid == "assure":
                out.append(
                    _finalize_board(
                        _board(
                            "assure",
                            [_line("WARN", "assure", "Skipped — lead edit produced no pending diff")],
                            note="Plan → code → assure; assure waits for coder diff",
                        )
                    )
                )
            elif hid == "check":
                out.append(
                    _finalize_board(
                        _board(
                            "check",
                            [_line("WARN", "flash", "Skipped — lead edit produced no pending diff")],
                            note="Plan → code → check; check waits for coder diff",
                        )
                    )
                )
        return out
    for hid in ordered:
        if hid == "check" and skip_flash_check:
            out.append(
                _finalize_board(
                    _board(
                        "check",
                        [_line("WARN", "flash", "skipped — plan already used 5090 flash")],
                        note="Sequential on one GPU",
                    )
                )
            )
            continue
        if hid == "review":
            if on_phase:
                on_phase({"phase": "review", "model": REVIEW_MODEL, "tier": REVIEW_TIER})
            out.append(run_review_helper(diff, prompt, files, changes=changes))
        elif hid == "assure":
            if on_phase:
                on_phase({"phase": "assure", "model": ASSURE_MODEL, "tier": ASSURE_TIER})
            out.append(run_assure_helper(diff, prompt, files, changes=changes))
        elif hid == "check":
            if on_phase:
                on_phase({"phase": "check", "model": probe_flash_tag() or FLASH_MODEL, "tier": "flash"})
            out.append(run_check_helper(diff, prompt, files, changes=changes))
    return out


def run_edit_helpers(
    helper_ids: list[str],
    prompt: str,
    files: list[str] | None = None,
    *,
    history: list | None = None,
    on_plan_delta: Callable[[str], None] | None = None,
    on_plan_begin: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[str, list[dict[str, Any]], bool]:
    """Pre/post helper orchestration for Edit. Returns (edit_prompt, helper_boards, plan_used_flash)."""
    ids = [h for h in helper_ids if h]
    boards: list[dict[str, Any]] = []
    edit_prompt = prompt
    plan_used_flash = False
    if "plan" in ids:
        plan_board = run_plan_helper(
            prompt,
            history=history,
            on_delta=on_plan_delta,
            on_begin=on_plan_begin,
        )
        boards.append(plan_board)
        plan_used_flash = plan_board.get("result") == "PASS" and bool((plan_board.get("text") or "").strip())
        if plan_used_flash:
            edit_prompt = augment_prompt_with_plan(prompt, plan_board)
    return edit_prompt, boards, plan_used_flash


def attach_post_edit_helpers(
    helper_ids: list[str],
    edit_result: dict[str, Any],
    prompt: str,
    files: list[str] | None,
    pre_boards: list[dict[str, Any]],
    *,
    plan_used_flash: bool = False,
    on_phase: Callable[[dict[str, Any]], None] | None = None,
    on_helper: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    post_ids = [h for h in helper_ids if h and h != "plan"]
    boards = list(pre_boards)
    if post_ids:
        for board in run_helpers(
            post_ids,
            edit_result,
            prompt,
            files,
            skip_flash_check=plan_used_flash,
            on_phase=on_phase,
        ):
            boards.append(board)
            if on_helper:
                on_helper(board)
    if boards:
        edit_result["helpers"] = boards
    return edit_result
