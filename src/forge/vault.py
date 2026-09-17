"""Obsidian vault search + open note. Named notes only; not workspace context."""

from __future__ import annotations

import os
from pathlib import Path

from forge.hosts import LINKS

SKIP_DIRS = {
    ".git",
    ".obsidian",
    ".trash",
    ".smart-env",
    "node_modules",
    "__pycache__",
}
NOTE_SUFFIXES = {".md", ".canvas"}
MAX_HITS = 40
MAX_WALK = 8_000
MAX_FILE_BYTES = 200_000
SNIPPET = 140


def vault_root() -> Path:
    override = (os.environ.get("FORGE_VAULT") or "").strip()
    return Path(override).expanduser() if override else Path(LINKS["vault"])


def vault_info() -> dict:
    root = vault_root()
    return {
        "ok": True,
        "path": str(root),
        "exists": root.is_dir(),
        "name": root.name or "FarmBrainVault",
    }


def _rel(root: Path, path: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _skipped(name: str) -> bool:
    if name in SKIP_DIRS:
        return True
    if name.startswith(".") and name not in {".env.example"}:
        return True
    return False


def _snippet(text: str, needle: str) -> str:
    lower = text.lower()
    idx = lower.find(needle)
    if idx < 0:
        line = text.strip().splitlines()[0] if text.strip() else ""
        return line[:SNIPPET]
    start = max(0, idx - 40)
    chunk = text[start : start + SNIPPET].replace("\n", " ").strip()
    if start:
        chunk = "…" + chunk
    if start + SNIPPET < len(text):
        chunk = chunk + "…"
    return chunk


def search_vault(query: str) -> dict:
    """Match vault note paths and markdown contents. Does not dump whole notes."""
    needle = (query or "").strip().lower()
    root = vault_root()
    info = vault_info()
    if not needle:
        return {**info, "query": query or "", "entries": [], "truncated": False}
    if not root.is_dir():
        return {**info, "query": query, "entries": [], "truncated": False, "error": "vault missing"}
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
            if _skipped(entry.name):
                continue
            walked += 1
            if entry.is_dir():
                descend.append(entry)
            elif entry.suffix.lower() in NOTE_SUFFIXES:
                rel = _rel(root, entry)
                hit = needle in rel.lower() or needle in entry.name.lower()
                snippet = ""
                if entry.suffix.lower() == ".md":
                    try:
                        if entry.stat().st_size <= MAX_FILE_BYTES:
                            text = entry.read_text(encoding="utf-8", errors="replace")
                            if needle in text.lower():
                                hit = True
                                snippet = _snippet(text, needle)
                    except OSError:
                        pass
                if hit:
                    if not snippet:
                        snippet = rel
                    entries.append(
                        {
                            "name": entry.stem,
                            "path": rel,
                            "kind": "note",
                            "snippet": snippet,
                        }
                    )
                    if len(entries) >= MAX_HITS:
                        truncated = True
                        return {**info, "query": query, "entries": entries, "truncated": truncated}
            if walked >= MAX_WALK:
                truncated = True
                return {**info, "query": query, "entries": entries, "truncated": truncated}
        stack.extend(descend)
    return {**info, "query": query, "entries": entries, "truncated": truncated}


def resolve_note(rel: str) -> Path:
    root = vault_root().resolve()
    raw = (rel or "").replace("\\", "/").lstrip("/")
    if not raw:
        raise ValueError("note path required")
    target = (root / raw).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{target} is outside the vault") from exc
    if target.suffix.lower() not in NOTE_SUFFIXES and not target.exists():
        md = target.with_suffix(".md")
        if md.is_file():
            return md
    if not target.exists():
        raise FileNotFoundError(raw)
    if target.suffix.lower() not in NOTE_SUFFIXES:
        raise ValueError("only vault notes (.md / .canvas) can be opened")
    return target
