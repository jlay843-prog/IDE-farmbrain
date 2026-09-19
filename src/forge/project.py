"""Create local Forge projects — folder + git init, no remotes."""

from __future__ import annotations

import re
from pathlib import Path

from forge.git import run_git
from forge.state import default_easy_projects_parent, save_state, set_workspace

_INVALID_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_project_name(name: str) -> str:
    text = (name or "").strip()
    if not text:
        raise ValueError("project name is required")
    if _INVALID_NAME.search(text):
        raise ValueError("project name has invalid characters")
    if text in {".", ".."}:
        raise ValueError("invalid project name")
    return text


def create_project(name: str, parent: str | Path | None = None) -> dict:
    """Create project folder, ``git init`` (no origin), and pin workspace."""
    clean = sanitize_project_name(name)
    parent_path = Path(parent or default_easy_projects_parent()).expanduser().resolve()
    parent_path.mkdir(parents=True, exist_ok=True)
    project_path = parent_path / clean
    if project_path.exists():
        raise ValueError(f"project already exists: {project_path}")
    project_path.mkdir()
    code, out, err = run_git(project_path, ["init"])
    if code != 0:
        try:
            project_path.rmdir()
        except OSError:
            pass
        raise RuntimeError((err or out or "git init failed").strip())
    state = set_workspace(project_path)
    state["easy_projects_parent"] = str(parent_path)
    return save_state(state)
