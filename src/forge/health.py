"""Local desk health — python finder + Monaco vendor (no HTTP server)."""

from __future__ import annotations

from pathlib import Path

from forge import __version__
from forge.python_find import find_python

UI_DIR = Path(__file__).resolve().parents[2] / "ui"
MONACO_LOADER = UI_DIR / "vendor" / "monaco-editor" / "min" / "vs" / "loader.js"


def health_snapshot() -> dict:
    py = find_python()
    monaco = MONACO_LOADER.is_file()
    return {
        "ok": True,
        "name": "forge",
        "version": __version__,
        "python": py,
        "monaco": {
            "ok": monaco,
            "path": str(MONACO_LOADER.relative_to(UI_DIR)) if monaco else "",
        },
    }
