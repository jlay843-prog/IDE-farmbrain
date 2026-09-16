"""Ask / edit against the pinned tier. Burst is blocked when Vast is live."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from forge.context import format_context, read_files
from forge.edit import ASK_SYSTEM, EDIT_SYSTEM, apply_diff, change_list
from forge.llm import chat, iter_chat
from forge.probe import resolve_session
from forge.state import is_protected_workspace, load_state, workspace_path


class SessionError(RuntimeError):
    pass


BeginFn = Callable[[dict[str, Any]], None]
DeltaFn = Callable[[str], None]


def active_session(tier: str | None = None, model: str | None = None, *, purpose: str | None = None) -> dict:
    state = load_state()
    if purpose == "ask":
        chosen_tier = tier or "chat"
        chosen_model = model or state.get("chat_model") or "qwen3.8:27b"
    elif purpose == "edit":
        chosen_tier = tier or "code"
        chosen_model = model or state.get("code_model") or "qwen3-coder:30b"
    else:
        chosen_tier = tier or state.get("tier") or "code"
        chosen_model = model or (None if tier else state.get("last_model"))
    resolved = resolve_session(chosen_tier, chosen_model)
    if resolved["blocked"]:
        raise SessionError("burst is blocked while Vast is active on the 5090")
    if not resolved["backend"].get("ok"):
        raise SessionError(f"{resolved['backend']['label']} is down ({resolved['backend'].get('error')})")
    return resolved


def build_messages(system: str, prompt: str, files: list[dict[str, str]]) -> list[dict[str, str]]:
    context = format_context(files)
    user = prompt if not context else f"{prompt}\n\n{context}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _generate(
    sess: dict[str, Any],
    system: str,
    prompt: str,
    named: list[dict[str, str]],
    *,
    on_begin: BeginFn | None = None,
    on_delta: DeltaFn | None = None,
) -> dict[str, Any]:
    if on_begin:
        on_begin(
            {
                "model": sess["model"],
                "backend": sess["backend"]["id"],
                "gpu": sess["backend"]["gpu"],
                "base": sess["base"],
                "tier": sess["tier"],
            }
        )
    messages = build_messages(system, prompt, named)
    if on_delta is None:
        return chat(sess["base"], sess["model"], messages)
    parts: list[str] = []
    model = sess["model"]
    raw: dict[str, Any] = {}
    for chunk in iter_chat(sess["base"], sess["model"], messages):
        delta = chunk.get("delta") or ""
        if delta:
            parts.append(delta)
            on_delta(delta)
        model = chunk.get("model") or model
        raw = chunk.get("raw") or raw
    return {"text": "".join(parts), "model": model, "done": True, "raw": raw}


def run_ask(
    prompt: str,
    files: list[str] | None = None,
    *,
    tier: str | None = None,
    model: str | None = None,
    workspace: Path | None = None,
    on_begin: BeginFn | None = None,
    on_delta: DeltaFn | None = None,
) -> dict:
    sess = active_session(tier, model, purpose="ask")
    root = workspace or workspace_path()
    named = read_files(root, files or []) if root and files else []
    reply = _generate(sess, ASK_SYSTEM, prompt, named, on_begin=on_begin, on_delta=on_delta)
    return {
        "ok": True,
        "kind": "ask",
        "tier": sess["tier"],
        "model": reply["model"],
        "backend": sess["backend"]["id"],
        "gpu": sess["backend"]["gpu"],
        "base": sess["base"],
        "text": reply["text"],
        "files": [f["path"] for f in named],
    }


def run_edit(
    prompt: str,
    files: list[str] | None = None,
    *,
    apply: bool = False,
    confirm_protected: bool = False,
    tier: str | None = None,
    model: str | None = None,
    workspace: Path | None = None,
    on_begin: BeginFn | None = None,
    on_delta: DeltaFn | None = None,
) -> dict:
    sess = active_session(tier, model, purpose="edit")
    root = workspace or workspace_path()
    if root is None:
        raise SessionError("no workspace - run forge open <path> first")
    if apply and is_protected_workspace(root) and not confirm_protected:
        raise SessionError(
            "workspace is farm-brain; apply is blocked unless you pass --i-understand-qc"
        )
    named = read_files(root, files or []) if files else []
    reply = _generate(sess, EDIT_SYSTEM, prompt, named, on_begin=on_begin, on_delta=on_delta)
    result = {
        "ok": True,
        "kind": "edit",
        "tier": sess["tier"],
        "model": reply["model"],
        "backend": sess["backend"]["id"],
        "gpu": sess["backend"]["gpu"],
        "base": sess["base"],
        "text": reply["text"],
        "files": [f["path"] for f in named],
        "changes": change_list(reply["text"]),
        "applied": False,
        "changed": [],
        "protected": is_protected_workspace(root),
    }
    if apply:
        result["changed"] = apply_diff(root, reply["text"])
        result["applied"] = True
    return result
