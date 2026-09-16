"""Ask / edit against the pinned tier. Burst is blocked when Vast is live."""

from __future__ import annotations

from pathlib import Path

from forge.context import format_context, read_files
from forge.edit import ASK_SYSTEM, EDIT_SYSTEM, apply_diff
from forge.llm import chat
from forge.probe import resolve_session
from forge.state import is_protected_workspace, load_state, workspace_path


class SessionError(RuntimeError):
    pass


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


def run_ask(
    prompt: str,
    files: list[str] | None = None,
    *,
    tier: str | None = None,
    model: str | None = None,
    workspace: Path | None = None,
) -> dict:
    sess = active_session(tier, model, purpose="ask")
    root = workspace or workspace_path()
    named = read_files(root, files or []) if root and files else []
    reply = chat(sess["base"], sess["model"], build_messages(ASK_SYSTEM, prompt, named))
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
    reply = chat(sess["base"], sess["model"], build_messages(EDIT_SYSTEM, prompt, named))
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
        "applied": False,
        "changed": [],
        "protected": is_protected_workspace(root),
    }
    if apply:
        result["changed"] = apply_diff(root, reply["text"])
        result["applied"] = True
    return result
