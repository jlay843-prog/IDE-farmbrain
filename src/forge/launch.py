"""Deep links to vault, Aether, Lumen, AI-PM, Farm Brain. No new agent OS."""

from __future__ import annotations

import os
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import quote

from forge import handoff as ho
from forge.hosts import LINKS
from forge.vault import resolve_note, vault_root


def launch(target: str, note: str = "", url: str = "") -> dict:
    key = (target or "").strip().lower()
    if key in {"vault", "obsidian"}:
        vault = vault_root()
        rel = (note or "").strip()
        if rel:
            try:
                candidate = resolve_note(rel)
            except (FileNotFoundError, ValueError) as exc:
                return {"ok": False, "target": "obsidian", "error": str(exc)}
            uri = "obsidian://open?vault=FarmBrainVault&file=" + quote(rel, safe="/")
            try:
                os.startfile(uri)  # type: ignore[attr-defined]
                return {"ok": True, "target": "obsidian", "url": uri, "path": str(candidate), "note": rel}
            except OSError:
                return _open_path(candidate)
        uri = "obsidian://open?vault=FarmBrainVault"
        try:
            os.startfile(uri)  # type: ignore[attr-defined]
            return {"ok": True, "target": "obsidian", "url": uri}
        except OSError:
            return _open_path(vault)
    if key == "aether":
        try:
            resolved = ho.resolve_launch_url("aether", url)
        except ValueError as exc:
            return {"ok": False, "target": "aether", "error": str(exc)}
        dest = resolved.get("url") or ""
        script = Path(LINKS["aether_launch"])
        if not script.is_file():
            return {"ok": False, "error": f"Aether launch script missing: {script}"}
        live = ho.aether_status()
        launched = False
        if not live.get("ok"):
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                cwd=str(script.parent.parent),
            )
            launched = True
        browse = ho.aether_browse(dest) if dest and live.get("ok") else None
        if browse and browse.get("ok") and browse.get("title"):
            ho.remember("aether", dest, title=browse["title"], source="aether-browse")
        return {
            "ok": True,
            "target": "aether",
            "path": str(script),
            "url": dest or ho.AETHER_DESK,
            "desk": ho.AETHER_DESK,
            "launched": launched,
            "live": bool(live.get("ok")),
            "browse": browse,
            "source": resolved.get("source"),
        }
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
    if key == "lumen":
        try:
            resolved = ho.resolve_launch_url("lumen", url)
        except ValueError as exc:
            return {"ok": False, "target": "lumen", "error": str(exc)}
        dest = resolved["url"]
        webbrowser.open(dest)
        return {"ok": True, "target": "lumen", "url": dest, "source": resolved.get("source")}
    if key in urls:
        webbrowser.open(urls[key])
        return {"ok": True, "target": key, "url": urls[key]}
    if key.startswith("http://") or key.startswith("https://"):
        webbrowser.open(key)
        return {"ok": True, "target": "url", "url": key}
    return {"ok": False, "error": f"unknown launch target {target!r}"}


def open_path(path: Path) -> dict:
    if not path.exists():
        return {"ok": False, "error": f"not found: {path}"}
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        webbrowser.open(path.as_uri())
    return {"ok": True, "target": "path", "path": str(path)}


def _open_path(path: Path) -> dict:
    return open_path(path)


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
