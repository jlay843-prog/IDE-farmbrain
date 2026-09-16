"""Named file context for ask/edit. Never dump a whole repo."""

from __future__ import annotations

from pathlib import Path

SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    ".next",
    ".pytest_cache",
}
MAX_FILE_CHARS = 24_000
MAX_TREE = 400
MAX_SEARCH = 80
MAX_WALK = 5_000


def resolve_under(workspace: Path, rel: str | Path) -> Path:
    raw = Path(rel)
    path = raw if raw.is_absolute() else (workspace / raw)
    resolved = path.resolve()
    try:
        resolved.relative_to(workspace.resolve())
    except ValueError as exc:
        raise ValueError(f"{resolved} is outside workspace {workspace}") from exc
    return resolved


def read_files(workspace: Path, rels: list[str]) -> list[dict[str, str]]:
    out = []
    for rel in rels:
        if not rel:
            continue
        path = resolve_under(workspace, rel)
        if not path.is_file():
            raise FileNotFoundError(str(path))
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > MAX_FILE_CHARS:
            text = text[:MAX_FILE_CHARS] + "\n\n/* truncated */\n"
        out.append({"path": str(path.relative_to(workspace)).replace("\\", "/"), "text": text})
    return out


def format_context(files: list[dict[str, str]]) -> str:
    if not files:
        return ""
    parts = ["Workspace files:"]
    for item in files:
        parts.append(f"\n===== {item['path']} =====\n{item['text']}")
    return "\n".join(parts)


def is_skipped(name: str) -> bool:
    if name in SKIP_DIRS:
        return True
    if name.startswith(".") and name != ".env.example":
        return True
    return False


def _rel(workspace: Path, path: Path) -> str:
    return str(path.relative_to(workspace.resolve())).replace("\\", "/")


def _entry(workspace: Path, path: Path) -> dict[str, str]:
    return {
        "name": path.name,
        "path": _rel(workspace, path),
        "kind": "dir" if path.is_dir() else "file",
    }


def _norm_rel(rel: str) -> str:
    text = (rel or "").replace("\\", "/").strip("/")
    if text in {"", "."}:
        return ""
    return text


def list_tree(workspace: Path, rel: str = "") -> list[dict]:
    root = resolve_under(workspace, rel) if rel else workspace.resolve()
    if not root.exists():
        return []
    if root.is_file():
        return [_entry(workspace, root)]
    rows: list[dict] = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError:
        return []
    for entry in entries:
        if is_skipped(entry.name):
            continue
        rows.append(_entry(workspace, entry))
        if len(rows) >= MAX_TREE:
            break
    return rows


def tree_listing(workspace: Path, rel: str = "") -> dict:
    root = workspace.resolve()
    cwd = _norm_rel(rel)
    crumbs = [{"name": root.name, "path": ""}]
    parent = None
    if cwd:
        parts = cwd.split("/")
        acc: list[str] = []
        for part in parts:
            acc.append(part)
            crumbs.append({"name": part, "path": "/".join(acc)})
        parent = "/".join(parts[:-1])
    return {
        "cwd": cwd,
        "parent": parent,
        "crumbs": crumbs,
        "entries": list_tree(workspace, cwd),
    }


def search_paths(workspace: Path, query: str) -> dict:
    """Match relative paths only. Never reads file contents."""
    needle = _norm_rel(query).lower()
    root = workspace.resolve()
    if not needle:
        return {"query": query or "", "entries": [], "truncated": False}
    entries: list[dict] = []
    truncated = False
    walked = 0
    stack = [root]
    while stack:
        current = stack.pop(0)
        try:
            kids = sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            continue
        descend: list[Path] = []
        for entry in kids:
            if is_skipped(entry.name):
                continue
            walked += 1
            rel_path = _rel(workspace, entry)
            if needle in rel_path.lower() or needle in entry.name.lower():
                entries.append(_entry(workspace, entry))
                if len(entries) >= MAX_SEARCH:
                    truncated = True
                    return {"query": query, "entries": entries, "truncated": truncated}
            if entry.is_dir():
                descend.append(entry)
            if walked >= MAX_WALK:
                truncated = True
                return {"query": query, "entries": entries, "truncated": truncated}
        stack.extend(descend)
    return {"query": query, "entries": entries, "truncated": truncated}
