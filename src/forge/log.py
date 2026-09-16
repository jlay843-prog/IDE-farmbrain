"""Append-only session log in %LOCALAPPDATA%\\Forge\\sessions.jsonl."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from forge.state import data_dir


def log_path() -> Path:
    return data_dir() / "sessions.jsonl"


def log_turn(kind: str, result: dict[str, Any], prompt: str = "") -> None:
    path = log_path()
    row = {
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kind": kind,
        "tier": result.get("tier"),
        "model": result.get("model"),
        "backend": result.get("backend"),
        "gpu": result.get("gpu"),
        "files": result.get("files") or [],
        "applied": result.get("applied"),
        "changed": result.get("changed") or [],
        "prompt": (prompt or "")[:240],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, default=str) + "\n")


def read_turns(limit: int = 80) -> list[dict[str, Any]]:
    path = log_path()
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    cap = max(1, min(int(limit), 500))
    rows: list[dict[str, Any]] = []
    for line in lines[-cap:]:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    rows.reverse()
    return rows
