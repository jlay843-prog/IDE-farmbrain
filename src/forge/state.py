"""Session + project registry in %LOCALAPPDATA%\\Forge."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_TIER = "code"
DEFAULT_UI_MODE = "easy"
UI_MODES = frozenset({"easy", "advanced"})
PROTECTED_HINT = "farm-brain patches still go through the existing QC gate — Forge will not auto-apply."
EPHEMERAL_PROJECT_NAMES = frozenset({"forge-w7-farm-brain"})


def data_dir() -> Path:
    override = os.environ.get("FORGE_DATA")
    if override:
        path = Path(override)
    elif os.name == "nt":
        path = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Forge"
    else:
        path = Path.home() / ".local" / "share" / "forge"
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_path() -> Path:
    return data_dir() / "state.json"


def default_easy_projects_parent() -> Path:
    return Path.home() / "ForgeProjects"


def default_state() -> dict[str, Any]:
    return {
        "workspace": "",
        "tier": DEFAULT_TIER,
        "last_model": "qwen3-coder-next:latest",
        "code_model": "qwen3-coder-next:latest",
        "chat_model": "qwen3.8:27b",
        "ui_mode": DEFAULT_UI_MODE,
        "easy_projects_parent": str(default_easy_projects_parent()),
        "projects": [],
        "handoff": {"aether": {"url": "", "title": "", "at": "", "source": ""}, "lumen": {"url": "", "title": "", "at": "", "source": ""}},
    }


def resolve_ui_mode(state: dict[str, Any]) -> str:
    raw = str(state.get("ui_mode") or "").strip().lower()
    if raw in UI_MODES:
        return raw
    if not str(state.get("workspace") or "").strip():
        return DEFAULT_UI_MODE
    return "advanced"


def load_state() -> dict[str, Any]:
    path = state_path()
    if not path.is_file():
        return default_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_state()
    merged = default_state()
    merged.update(data if isinstance(data, dict) else {})
    if not isinstance(merged.get("projects"), list):
        merged["projects"] = []
    merged["ui_mode"] = resolve_ui_mode(merged)
    if not str(merged.get("easy_projects_parent") or "").strip():
        merged["easy_projects_parent"] = str(default_easy_projects_parent())
    cleaned, changed = prune_projects(merged)
    if changed:
        save_state(cleaned)
        return cleaned
    return merged


def save_state(state: dict[str, Any]) -> dict[str, Any]:
    path = state_path()
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return state


def set_ui_mode(mode: str) -> dict[str, Any]:
    chosen = str(mode or "").strip().lower()
    if chosen not in UI_MODES:
        raise ValueError("ui_mode must be easy or advanced")
    state = load_state()
    state["ui_mode"] = chosen
    return save_state(state)


def set_workspace(path: str | Path) -> dict[str, Any]:
    resolved = str(Path(path).expanduser().resolve())
    state = load_state()
    state["workspace"] = resolved
    upsert_project(state, resolved)
    return save_state(state)


def set_tier(tier: str, model: str | None = None) -> dict[str, Any]:
    state = load_state()
    state["tier"] = tier
    if model:
        state["last_model"] = model
        if tier == "code":
            state["code_model"] = model
        elif tier == "chat":
            state["chat_model"] = model
    elif tier == "code":
        state["last_model"] = state.get("code_model") or "qwen3-coder-next:latest"
    elif tier == "chat":
        state["last_model"] = state.get("chat_model") or "qwen3.8:27b"
    workspace = state.get("workspace") or ""
    if workspace:
        upsert_project(state, workspace, tier=tier, model=model or state.get("last_model"))
    return save_state(state)


def upsert_project(
    state: dict[str, Any],
    path: str,
    *,
    tier: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    resolved = str(Path(path).expanduser().resolve()) if path else ""
    if not resolved:
        return state
    projects = state.setdefault("projects", [])
    row = next((p for p in projects if p.get("path") == resolved), None)
    if row is None:
        row = {
            "path": resolved,
            "name": Path(resolved).name,
            "tier": tier or state.get("tier") or DEFAULT_TIER,
            "model": model or state.get("last_model") or "qwen3-coder-next:latest",
        }
        projects.insert(0, row)
    else:
        if tier:
            row["tier"] = tier
        if model:
            row["model"] = model
        projects.remove(row)
        projects.insert(0, row)
    state["projects"] = projects[:24]
    return state


def _is_leftover_project(path: Path, name: str) -> bool:
    if name.lower() in EPHEMERAL_PROJECT_NAMES:
        return True
    raw = str(path).lower().replace("/", "\\")
    if "forge-w7-farm-brain" in raw:
        return True
    try:
        temp = Path(os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp").resolve()
        resolved = path.resolve()
    except OSError:
        return False
    return resolved.parent == temp and resolved.name.lower() == "farm-brain"


def prune_projects(state: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Drop leftover W7 test rows and folders that no longer exist."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    original = list(state.get("projects") or [])
    changed = False
    for row in original:
        if not isinstance(row, dict):
            changed = True
            continue
        raw = str(row.get("path") or "").strip()
        name = str(row.get("name") or Path(raw).name)
        if not raw:
            changed = True
            continue
        path = Path(raw)
        if _is_leftover_project(path, name):
            changed = True
            continue
        if not path.exists():
            changed = True
            continue
        resolved = str(path.resolve())
        key = resolved.lower()
        if key in seen:
            changed = True
            continue
        seen.add(key)
        rows.append(
            {
                **row,
                "path": resolved,
                "name": Path(resolved).name,
            }
        )
    if len(rows) != len(original):
        changed = True
    state["projects"] = rows
    return state, changed


def assign_project(path: str, *, tier: str, model: str) -> dict[str, Any]:
    state = load_state()
    upsert_project(state, path, tier=tier, model=model)
    if state.get("workspace") == str(Path(path).expanduser().resolve()):
        state["tier"] = tier
        state["last_model"] = model
    return save_state(state)


def workspace_path() -> Path | None:
    raw = (load_state().get("workspace") or "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.exists() else None


def is_protected_workspace(path: Path | None = None) -> bool:
    """True only when the workspace folder itself is named farm-brain."""
    target = path or workspace_path()
    if target is None:
        return False
    return target.name.lower() == "farm-brain"
