"""Append-only session log in %LOCALAPPDATA%\\Forge\\sessions.jsonl."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from forge.state import data_dir


def log_turn(kind: str, result: dict[str, Any], prompt: str = "") -> None:
    path = data_dir() / "sessions.jsonl"
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
