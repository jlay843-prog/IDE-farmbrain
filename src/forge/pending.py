"""Persist pending coder diffs so Easy Accept survives a desk restart."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from forge.state import data_dir, workspace_path


def pending_path() -> Path:
    return data_dir() / "pending-accept.json"


def load_pending_accept() -> dict[str, Any] | None:
    path = pending_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    diff = str(data.get("diff") or "").strip()
    if not diff:
        return None
    ws = str(data.get("workspace") or "").strip()
    active = workspace_path()
    if active is None or str(active) != ws:
        return None
    return data


def save_pending_accept(
    *,
    prompt: str,
    diff: str,
    changes: list[dict[str, Any]] | None = None,
    hunks: list[dict[str, Any]] | None = None,
    hunk_status: dict[str, str] | None = None,
    protected: bool = False,
) -> dict[str, Any] | None:
    text = (diff or "").strip()
    if not text:
        clear_pending_accept()
        return None
    root = workspace_path()
    if root is None:
        return None
    row = {
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "workspace": str(root),
        "prompt": (prompt or "")[:500],
        "diff": text,
        "changes": changes or [],
        "hunks": hunks or [],
        "hunk_status": hunk_status or {},
        "protected": bool(protected),
    }
    pending_path().write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    return row


def clear_pending_accept() -> None:
    path = pending_path()
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            pass


def maybe_save_edit_pending(prompt: str, result: dict[str, Any]) -> None:
    diff = str(result.get("text") or "").strip()
    changes = result.get("changes") or []
    if not diff or not changes:
        return
    save_pending_accept(
        prompt=prompt,
        diff=diff,
        changes=changes,
        hunks=result.get("hunks") or [],
        protected=bool(result.get("protected")),
    )
