"""Ask / edit against the pinned tier. Burst is blocked when Vast is live."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from forge.context import format_context, read_files
from forge.edit import (
    ASK_SYSTEM,
    EASY_ASK_SYSTEM,
    EASY_EDIT_PREFIX,
    EDIT_SYSTEM,
    apply_diff,
    change_list,
    hunk_list,
)
from forge.llm import chat, iter_chat
from forge.probe import resolve_session
from forge.state import is_protected_workspace, load_state, workspace_path
from forge.tools import (
    MAX_ROUNDS,
    format_tool_result,
    native_ollama_tools,
    parse_tool_markup,
    run_tool,
    strip_tool_markup,
    tool_calls_from_reply,
)

ASK_TOOL_NUDGE = (
    "Ask mode can't read or search files. Switch to Edit on the desk, "
    "check the target file(s) as named context, send your prompt, then review and Apply hunk."
)
EASY_ASK_TOOL_NUDGE = (
    "This chat turn is for questions and planning. Describe what to create or change "
    "and Forge will return a diff for you to Accept."
)


class SessionError(RuntimeError):
    pass


BeginFn = Callable[[dict[str, Any]], None]
DeltaFn = Callable[[str], None]
ToolFn = Callable[[dict[str, Any]], None]


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


MAX_HISTORY_TURNS = 24


def normalize_history(history: list | None) -> list[dict[str, str]]:
    if not history:
        return []
    out: list[dict[str, str]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = strip_tool_markup(str(item.get("content") or "")).strip()
        if role in {"user", "assistant"} and content:
            out.append({"role": role, "content": content})
    return out[-MAX_HISTORY_TURNS:]


def build_messages(
    system: str,
    prompt: str,
    files: list[dict[str, str]],
    history: list | None = None,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for turn in normalize_history(history):
        messages.append({"role": turn["role"], "content": turn["content"]})
    context = format_context(files)
    user = prompt if not context else f"{prompt}\n\n{context}"
    messages.append({"role": "user", "content": user})
    return messages


def sanitize_ask_reply(text: str, *, easy: bool = False) -> str:
    raw = text or ""
    if not parse_tool_markup(raw):
        return raw
    cleaned = strip_tool_markup(raw).strip()
    fallback = EASY_ASK_TOOL_NUDGE if easy else ASK_TOOL_NUDGE
    return cleaned or fallback


def _emit_begin(sess: dict[str, Any], on_begin: BeginFn | None) -> None:
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


def _one_turn(
    sess: dict[str, Any],
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    on_delta: DeltaFn | None = None,
) -> dict[str, Any]:
    if on_delta is None:
        return chat(sess["base"], sess["model"], messages, tools=tools)
    parts: list[str] = []
    model = sess["model"]
    raw: dict[str, Any] = {}
    tool_calls: list[Any] = []
    for chunk in iter_chat(sess["base"], sess["model"], messages, tools=tools):
        delta = chunk.get("delta") or ""
        if delta:
            parts.append(delta)
            on_delta(delta)
        model = chunk.get("model") or model
        raw = chunk.get("raw") or raw
        if chunk.get("tool_calls"):
            tool_calls = chunk["tool_calls"]
    if tool_calls:
        message = raw.get("message") if isinstance(raw, dict) else None
        base_msg = message if isinstance(message, dict) else {}
        raw = {**(raw if isinstance(raw, dict) else {}), "message": {**base_msg, "tool_calls": tool_calls}}
    return {"text": "".join(parts), "model": model, "done": True, "raw": raw, "tool_calls": tool_calls}


def _generate(
    sess: dict[str, Any],
    system: str,
    prompt: str,
    named: list[dict[str, str]],
    *,
    workspace: Path | None = None,
    use_tools: bool = False,
    history: list | None = None,
    on_begin: BeginFn | None = None,
    on_delta: DeltaFn | None = None,
    on_tool: ToolFn | None = None,
) -> dict[str, Any]:
    _emit_begin(sess, on_begin)
    messages = build_messages(system, prompt, named, history)
    traces: list[dict[str, Any]] = []
    tool_rounds = 0
    last: dict[str, Any] = {"text": "", "model": sess["model"], "done": True, "raw": {}, "tools": []}
    rounds = MAX_ROUNDS if use_tools and workspace is not None else 0
    for step in range(rounds + 1):
        inspecting = use_tools and step < rounds
        offer = native_ollama_tools(sess.get("model")) if inspecting else None
        if on_tool and inspecting:
            on_tool({"phase": "round", "round": step + 1, "max": rounds + 1})
        last = _one_turn(sess, messages, tools=offer, on_delta=on_delta)
        reply_text = last.get("text") or ""
        calls = tool_calls_from_reply(reply_text, last.get("raw")) if inspecting else []
        if inspecting and calls and not change_list(reply_text):
            cleaned = strip_tool_markup(reply_text).strip()
            messages.append({"role": "assistant", "content": cleaned or "(tool inspection)"})
            blobs: list[str] = []
            for call in calls:
                args = call.get("args") if isinstance(call.get("args"), dict) else {}
                if on_tool:
                    on_tool({"phase": "call", "name": call.get("name"), "args": args})
                result = run_tool(workspace, str(call.get("name") or ""), args)
                trace = {
                    "name": result.get("name") or call.get("name"),
                    "ok": bool(result.get("ok")),
                    "detail": result.get("detail") or result.get("path") or "",
                    "preview": result.get("preview") or result.get("error") or "",
                }
                traces.append(trace)
                if on_tool:
                    on_tool({"phase": "result", **trace})
                blobs.append(format_tool_result(result))
            tool_rounds += 1
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Tool results (read/list/grep only; there is no shell). "
                        "Return a unified diff, or another read/list/grep call.\n\n"
                        + "\n\n".join(blobs)
                    ),
                }
            )
            continue
        if inspecting and not change_list(reply_text) and step < rounds:
            cleaned = strip_tool_markup(reply_text).strip()
            messages.append({"role": "assistant", "content": cleaned or reply_text})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Do not ask Jeff to click Edit again or say you will check files later. "
                        "This Edit session already includes inspection — call read, list, or grep now, "
                        "or return the unified diff in this reply."
                    ),
                }
            )
            continue
        if use_tools:
            last["text"] = strip_tool_markup(last.get("text") or "")
        last["tools"] = traces
        last["tool_rounds"] = tool_rounds
        return last
    if use_tools:
        last["text"] = strip_tool_markup(last.get("text") or "")
    last["tools"] = traces
    last["tool_rounds"] = tool_rounds
    return last


def run_ask(
    prompt: str,
    files: list[str] | None = None,
    *,
    tier: str | None = None,
    model: str | None = None,
    workspace: Path | None = None,
    history: list | None = None,
    easy: bool = False,
    on_begin: BeginFn | None = None,
    on_delta: DeltaFn | None = None,
) -> dict:
    sess = active_session(tier, model, purpose="ask")
    root = workspace or workspace_path()
    named = read_files(root, files or []) if root and files else []
    system = EASY_ASK_SYSTEM if easy else ASK_SYSTEM
    reply = _generate(sess, system, prompt, named, history=history, on_begin=on_begin, on_delta=on_delta)
    return {
        "ok": True,
        "kind": "ask",
        "tier": sess["tier"],
        "model": reply["model"],
        "backend": sess["backend"]["id"],
        "gpu": sess["backend"]["gpu"],
        "base": sess["base"],
        "text": sanitize_ask_reply(reply["text"], easy=easy),
        "files": [f["path"] for f in named],
        "easy": easy,
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
    history: list | None = None,
    easy: bool = False,
    on_begin: BeginFn | None = None,
    on_delta: DeltaFn | None = None,
    on_tool: ToolFn | None = None,
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
    system = f"{EASY_EDIT_PREFIX}{EDIT_SYSTEM}" if easy else EDIT_SYSTEM
    reply = _generate(
        sess,
        system,
        prompt,
        named,
        workspace=root,
        use_tools=True,
        history=history,
        on_begin=on_begin,
        on_delta=on_delta,
        on_tool=on_tool,
    )
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
        "hunks": hunk_list(reply["text"]),
        "tools": reply.get("tools") or [],
        "tool_rounds": int(reply.get("tool_rounds") or 0),
        "applied": False,
        "changed": [],
        "protected": is_protected_workspace(root),
        "easy": easy,
    }
    if apply:
        result["changed"] = apply_diff(root, reply["text"])
        result["applied"] = True
    return result
