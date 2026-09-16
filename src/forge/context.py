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


def list_tree(workspace: Path, rel: str = "") -> list[dict]:
    root = resolve_under(workspace, rel) if rel else workspace.resolve()
    if not root.exists():
        return []
    if root.is_file():
        return [{"name": root.name, "path": str(root.relative_to(workspace)).replace("\\", "/"), "kind": "file"}]
    rows: list[dict] = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError:
        return []
    for entry in entries:
        if entry.name in SKIP_DIRS or entry.name.startswith("."):
            if entry.name != ".env.example":
                continue
        kind = "dir" if entry.is_dir() else "file"
        rel_path = str(entry.relative_to(workspace)).replace("\\", "/")
        rows.append({"name": entry.name, "path": rel_path, "kind": kind})
        if len(rows) >= MAX_TREE:
            break
    return rows
