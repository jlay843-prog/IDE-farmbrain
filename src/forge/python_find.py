"""Locate Python 3.11+ without requiring it on PATH (packaged desk)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any


def _windows_candidates() -> list[Path]:
    local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    pf = Path(os.environ.get("ProgramFiles") or r"C:\Program Files")
    pf86 = Path(os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)")
    home = Path.home()
    rows = [
        Path(os.environ["FORGE_PYTHON"]) if os.environ.get("FORGE_PYTHON") else None,
        Path(os.environ["PYTHON"]) if os.environ.get("PYTHON") else None,
        Path(r"C:\Windows\py.exe"),
        local / "Programs" / "Python" / "Launcher" / "py.exe",
        Path(r"C:\Windows\System32\py.exe"),
    ]
    for base in (
        local / "Programs" / "Python",
        pf,
        pf86,
        home / "AppData" / "Local" / "Programs" / "Python",
    ):
        if not base.is_dir():
            continue
        for child in sorted(base.glob("Python3*/python.exe"), reverse=True):
            rows.append(child)
        nested = base / "python.exe"
        if nested.is_file():
            rows.append(nested)
    return [p for p in rows if p is not None]


def _unix_candidates() -> list[Path]:
    rows = []
    for key in ("FORGE_PYTHON", "PYTHON"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            rows.append(Path(raw))
    for name in ("python3", "python"):
        rows.append(Path("/usr/bin") / name)
        rows.append(Path("/usr/local/bin") / name)
    return rows


_cached: dict[str, Any] | None = None


def bundled_python(root: Path | None = None) -> Path | None:
    env_root = (os.environ.get("FORGE_ROOT") or "").strip()
    bases = []
    if root:
        bases.append(Path(root))
    if env_root:
        bases.append(Path(env_root))
    resources = (os.environ.get("FORGE_RESOURCES") or "").strip()
    if resources:
        bases.append(Path(resources))
    seen: set[Path] = set()
    for base in bases:
        for rel in (
            base / "python" / "python.exe",
            base / "python" / "python",
            base / "python" / "bin" / "python.exe",
            base / "python" / "bin" / "python3",
        ):
            resolved = rel if rel not in seen else None
            if resolved is None:
                continue
            seen.add(rel)
            if rel.is_file():
                return rel
    return None


def version_ok(exe: Path, extra: list[str] | None = None) -> bool:
    prefix = list(extra or [])
    try:
        proc = subprocess.run(
            [str(exe), *prefix, "-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"],
            capture_output=True,
            timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def which_named(name: str) -> Path | None:
    path = (os.environ.get("PATH") or "").split(os.pathsep)
    exts = [""]
    if os.name == "nt":
        exts = os.environ.get("PATHEXT", ".EXE;.CMD;.BAT").split(";")
    for folder in path:
        if not folder:
            continue
        base = Path(folder)
        for ext in exts:
            candidate = base / f"{name}{ext}"
            if candidate.is_file():
                return candidate
    return None


def find_python(root: Path | None = None) -> dict[str, Any]:
    """Return {ok, exe, args, source} for a 3.11+ interpreter, PATH optional."""
    global _cached
    if _cached is not None and root is None:
        return _cached
    bundled = bundled_python(root)
    ordered: list[tuple[str, Path, list[str]]] = []
    if bundled:
        ordered.append(("bundled", bundled, []))
    if os.name == "nt":
        for path in _windows_candidates():
            if path.name.lower() == "py.exe":
                ordered.append(("py-launcher", path, ["-3"]))
            else:
                ordered.append(("known-path", path, []))
        py = which_named("py")
        if py:
            ordered.append(("path-py", py, ["-3"]))
        for name in ("python", "python3"):
            found = which_named(name)
            if found:
                ordered.append(("path", found, []))
    else:
        for path in _unix_candidates():
            ordered.append(("known-path", path, []))
        for name in ("python3", "python"):
            found = which_named(name)
            if found:
                ordered.append(("path", found, []))

    seen: set[str] = set()
    for source, exe, extra in ordered:
        key = str(exe).lower() + " ".join(extra)
        if key in seen:
            continue
        seen.add(key)
        if not exe.is_file():
            continue
        if version_ok(exe, extra):
            found = {
                "ok": True,
                "exe": str(exe),
                "args": extra,
                "source": source,
            }
            if root is None:
                _cached = found
            return found
    missed = {
        "ok": False,
        "exe": "",
        "args": [],
        "source": "",
        "error": "Python 3.11+ not found. Install Python or set FORGE_PYTHON, or drop python.exe next to Forge under python/.",
    }
    if root is None:
        _cached = missed
    return missed
