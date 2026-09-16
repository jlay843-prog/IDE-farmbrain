"""Coder tools: read, list, grep. Never a shell."""

from __future__ import annotations

import json
import re
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from forge.context import (
    MAX_TREE,
    format_context,
    is_skipped,
    list_tree,
    read_files,
    resolve_under,
)

ALLOWED = ("read", "list", "grep")
MAX_ROUNDS = 6
MAX_GREP_HITS = 40
MAX_GREP_BYTES = 200_000
MAX_TOOL_CHARS = 12_000
MAX_WALK = 5_000

TOOL_XML = re.compile(
    r"<tool\s+name=[\"'](read|list|grep)[\"']\s*>(.*?)</tool>",
    re.I | re.S,
)

OLLAMA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Read one named file under the workspace. Never dump the repo.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Workspace-relative path"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list",
            "description": "List one directory under the workspace. Names and paths only, no file bytes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory relative to the workspace; empty is the root"}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Search file contents with a Python regex. No shell, no pipes, no subprocess.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Python regular expression"},
                    "path": {"type": "string", "description": "Optional subdirectory or file to search under"},
                    "glob": {"type": "string", "description": "Optional filename glob such as *.py"},
                },
                "required": ["pattern"],
            },
        },
    },
]


def _clip(text: str, limit: int = MAX_TOOL_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n/* truncated */\n"


def _args(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return {"path": text}
        return data if isinstance(data, dict) else {}
    return {}


def parse_native_tool_calls(message: dict[str, Any] | None) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for raw in (message or {}).get("tool_calls") or []:
        if not isinstance(raw, dict):
            continue
        fn = raw.get("function") if isinstance(raw.get("function"), dict) else raw
        name = str(fn.get("name") or raw.get("name") or "").strip().lower()
        args = _args(fn.get("arguments") if "arguments" in fn else raw.get("arguments"))
        if name:
            calls.append({"name": name, "args": args})
    return calls


def parse_tool_markup(text: str) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for match in TOOL_XML.finditer(text or ""):
        name = match.group(1).strip().lower()
        args = _args(match.group(2))
        if name == "grep" and "pattern" not in args and "path" in args:
            args = {"pattern": args["path"], **{k: v for k, v in args.items() if k != "path"}}
        calls.append({"name": name, "args": args})
    return calls


def tool_calls_from_reply(text: str, raw: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    message = (raw or {}).get("message") if isinstance(raw, dict) else None
    native = parse_native_tool_calls(message if isinstance(message, dict) else None)
    if native:
        return native
    return parse_tool_markup(text or "")


def run_tool(workspace: Path, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    tool = (name or "").strip().lower()
    payload = args or {}
    if tool not in ALLOWED:
        return {
            "ok": False,
            "name": tool or name,
            "error": "unknown tool — Forge allows read, list, and grep only (no shell)",
        }
    try:
        if tool == "read":
            return _read(workspace, str(payload.get("path") or ""))
        if tool == "list":
            return _list(workspace, str(payload.get("path") or ""))
        return _grep(
            workspace,
            str(payload.get("pattern") or ""),
            rel=str(payload.get("path") or ""),
            glob=str(payload.get("glob") or ""),
        )
    except (FileNotFoundError, ValueError, OSError) as exc:
        return {"ok": False, "name": tool, "error": str(exc)}


def _read(workspace: Path, rel: str) -> dict[str, Any]:
    if not (rel or "").strip():
        return {"ok": False, "name": "read", "error": "path is required"}
    files = read_files(workspace, [rel])
    text = format_context(files)
    row = files[0]
    return {
        "ok": True,
        "name": "read",
        "path": row["path"],
        "detail": row["path"],
        "preview": f"{row['path']} ({len(row['text'])} chars)",
        "text": _clip(text),
    }


def _list(workspace: Path, rel: str) -> dict[str, Any]:
    rows = list_tree(workspace, rel)
    lines = [f"{row['kind']}\t{row['path']}" for row in rows[:MAX_TREE]]
    target = (rel or "").replace("\\", "/").strip("/")
    return {
        "ok": True,
        "name": "list",
        "path": target,
        "detail": target or ".",
        "preview": f"{len(rows)} entries in {target or '.'}",
        "entries": rows,
        "text": _clip("\n".join(lines) if lines else "(empty directory)"),
    }


def _grep(workspace: Path, pattern: str, *, rel: str = "", glob: str = "") -> dict[str, Any]:
    if not pattern:
        return {"ok": False, "name": "grep", "error": "pattern is required"}
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return {"ok": False, "name": "grep", "error": f"invalid pattern: {exc}"}
    root = workspace.resolve()
    start = resolve_under(workspace, rel) if rel else root
    if not start.exists():
        raise FileNotFoundError(rel or str(start))
    hits: list[dict[str, Any]] = []
    truncated = False
    walked = 0
    files: list[Path] = []
    if start.is_file():
        files = [start]
    else:
        stack = [start]
        while stack and walked < MAX_WALK:
            current = stack.pop(0)
            try:
                kids = sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
            except OSError:
                continue
            for entry in kids:
                if is_skipped(entry.name):
                    continue
                walked += 1
                if entry.is_dir():
                    stack.append(entry)
                    continue
                if glob and not fnmatch(entry.name, glob):
                    continue
                files.append(entry)
                if walked >= MAX_WALK:
                    truncated = True
                    break
    for path in files:
        if len(hits) >= MAX_GREP_HITS:
            truncated = True
            break
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > MAX_GREP_BYTES:
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\0" in raw[:8000]:
            continue
        text = raw.decode("utf-8", errors="replace")
        rel_path = str(path.relative_to(root)).replace("\\", "/")
        for i, line in enumerate(text.splitlines(), start=1):
            if not rx.search(line):
                continue
            snippet = line if len(line) <= 200 else line[:200] + "…"
            hits.append({"path": rel_path, "line": i, "text": snippet})
            if len(hits) >= MAX_GREP_HITS:
                truncated = True
                break
    rendered = "\n".join(f"{h['path']}:{h['line']}:{h['text']}" for h in hits) or "(no matches)"
    if truncated:
        rendered += "\n/* truncated */"
    needle = pattern if len(pattern) < 40 else pattern[:37] + "..."
    return {
        "ok": True,
        "name": "grep",
        "path": (rel or "").replace("\\", "/").strip("/"),
        "detail": needle,
        "preview": f"{len(hits)} hits for {needle}",
        "hits": hits,
        "truncated": truncated,
        "text": _clip(rendered),
    }


def format_tool_result(result: dict[str, Any]) -> str:
    name = result.get("name") or "tool"
    if not result.get("ok"):
        return f"{name} error: {result.get('error') or 'failed'}"
    body = result.get("text") or ""
    header = f"{name} {result.get('detail') or result.get('path') or ''}".strip()
    return _clip(f"{header}\n{body}")
