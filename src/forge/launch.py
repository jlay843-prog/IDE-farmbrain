"""Deep links to vault, Aether, Lumen, AI-PM, Farm Brain. No new agent OS."""

from __future__ import annotations

import os
import subprocess
import webbrowser
from pathlib import Path

from forge.hosts import LINKS


def launch(target: str, note: str = "") -> dict:
    key = (target or "").strip().lower()
    if key in {"vault", "obsidian"}:
        vault = Path(LINKS["vault"])
        if note:
            candidate = vault / note
            if candidate.exists():
                return _open_path(candidate)
        uri = "obsidian://open?vault=FarmBrainVault"
        if note:
            uri += f"&file={note.replace(' ', '%20')}"
        try:
            os.startfile(uri)  # type: ignore[attr-defined]
            return {"ok": True, "target": "obsidian", "url": uri}
        except OSError:
            return _open_path(vault)
    if key == "aether":
        script = Path(LINKS["aether_launch"])
        if script.is_file():
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                cwd=str(script.parent.parent),
            )
            return {"ok": True, "target": "aether", "path": str(script)}
        return {"ok": False, "error": f"Aether launch script missing: {script}"}
    urls = {
        "lumen": LINKS["lumen"],
        "aipm": LINKS["aipm"],
        "farm": LINKS["farm"],
        "compute": LINKS["farm_compute"],
        "coder": LINKS["farm_coder"],
        "ontology": LINKS["ontology"],
        "ray": LINKS["ray"],
        "raydash": LINKS["ray"],
    }
    if key in urls:
        webbrowser.open(urls[key])
        return {"ok": True, "target": key, "url": urls[key]}
    if key.startswith("http://") or key.startswith("https://"):
        webbrowser.open(key)
        return {"ok": True, "target": "url", "url": key}
    return {"ok": False, "error": f"unknown launch target {target!r}"}


def _open_path(path: Path) -> dict:
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        webbrowser.open(path.as_uri())
    return {"ok": True, "target": "path", "path": str(path)}


def link_catalog() -> list[dict]:
    return [
        {"id": "vault", "label": "Obsidian vault", "detail": LINKS["vault"]},
        {"id": "aether", "label": "Aether", "detail": "Local AI browser"},
        {"id": "lumen", "label": "Lumen", "detail": LINKS["lumen"]},
        {"id": "aipm", "label": "AI-PM", "detail": LINKS["aipm"]},
        {"id": "farm", "label": "Farm Brain", "detail": LINKS["farm"]},
        {"id": "compute", "label": "Compute tab", "detail": LINKS["farm_compute"]},
        {"id": "coder", "label": "Farm /coder UI", "detail": LINKS["farm_coder"]},
        {"id": "ontology", "label": "Ontology API", "detail": LINKS["ontology"]},
        {"id": "ray", "label": "Ray Dashboard", "detail": LINKS["ray"]},
    ]
