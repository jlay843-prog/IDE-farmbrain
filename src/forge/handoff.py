"""Aether / Lumen last-URL handoff. Sibling tools stay sibling tools."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from forge.hosts import EVO, LINKS
from forge.httputil import request_json
from forge.state import load_state, save_state

AETHER_DESK = "http://127.0.0.1:43127"
AETHER_HEALTH = f"{AETHER_DESK}/api/health"
AETHER_BROWSE = f"{AETHER_DESK}/api/browse"

LUMEN_HOSTS = {
    (EVO, 8100),
    ("127.0.0.1", 8100),
    ("localhost", 8100),
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def aether_data_dir() -> Path:
    override = (os.environ.get("AETHER_DATA") or "").strip()
    if override:
        return Path(override)
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Aether" / "data"
    return Path.home() / ".local" / "share" / "aether" / "data"


def empty_slot() -> dict:
    return {"url": "", "title": "", "at": "", "source": ""}


def default_handoff() -> dict:
    return {"aether": empty_slot(), "lumen": empty_slot()}


def _slot(raw) -> dict:
    row = empty_slot()
    if isinstance(raw, dict):
        row["url"] = str(raw.get("url") or "")
        row["title"] = str(raw.get("title") or "")
        row["at"] = str(raw.get("at") or "")
        row["source"] = str(raw.get("source") or "")
    return row


def stored_handoff() -> dict:
    state = load_state()
    raw = state.get("handoff") if isinstance(state.get("handoff"), dict) else {}
    return {"aether": _slot(raw.get("aether")), "lumen": _slot(raw.get("lumen"))}


def remember(target: str, url: str, *, title: str = "", source: str = "forge") -> dict:
    key = (target or "").strip().lower()
    if key not in {"aether", "lumen"}:
        raise ValueError("handoff target must be aether or lumen")
    cleaned = normalize_url(key, url)
    state = load_state()
    handoff = stored_handoff()
    handoff[key] = {
        "url": cleaned,
        "title": (title or "").strip(),
        "at": _now(),
        "source": source,
    }
    state["handoff"] = handoff
    save_state(state)
    if key == "aether":
        write_aether_handoff_file(cleaned, title=title)
    return handoff


def normalize_url(target: str, url: str) -> str:
    key = (target or "").strip().lower()
    raw = (url or "").strip()
    if key == "lumen":
        return _lumen_url(raw)
    if key == "aether":
        return _aether_url(raw)
    raise ValueError(f"unknown handoff target {target!r}")


def _lumen_url(raw: str) -> str:
    home = LINKS["lumen"].rstrip("/")
    if not raw:
        return home
    if raw.startswith("/") or not raw.lower().startswith("http"):
        return home + (raw if raw.startswith("/") else "/" + raw.lstrip("/"))
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if parsed.scheme not in {"http", "https"} or (host, port) not in LUMEN_HOSTS:
        raise ValueError("Lumen handoff stays on the Lumen origin (:8100)")
    path = parsed.path or "/"
    return urlunparse(("http", parsed.netloc, path, "", parsed.query, parsed.fragment))


def _aether_url(raw: str) -> str:
    if not raw:
        raise ValueError("Aether handoff needs an http(s) URL")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Aether handoff needs an http(s) URL")
    return raw


def read_aether_last_url() -> dict:
    audit = aether_data_dir() / "audit.jsonl"
    if not audit.is_file():
        return empty_slot()
    try:
        lines = audit.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return empty_slot()
    for line in reversed(lines[-400:]):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        url = str(row.get("url") or "").strip()
        if not url:
            continue
        try:
            cleaned = _aether_url(url)
        except ValueError:
            continue
        return {
            "url": cleaned,
            "title": str(row.get("title") or ""),
            "at": str(row.get("at") or ""),
            "source": "aether-audit",
        }
    return empty_slot()


def write_aether_handoff_file(url: str, title: str = "") -> Path | None:
    root = aether_data_dir()
    try:
        root.mkdir(parents=True, exist_ok=True)
        path = root / "forge-handoff.json"
        path.write_text(
            json.dumps({"url": url, "title": title, "at": _now(), "from": "forge"}, indent=2) + "\n",
            encoding="utf-8",
        )
        return path
    except OSError:
        return None


def aether_status() -> dict:
    code, body = request_json(AETHER_HEALTH, timeout=1.5)
    ok = code == 200 and isinstance(body, dict) and body.get("app") == "aether"
    return {"ok": ok, "status": code, "body": body if isinstance(body, dict) else {}}


def aether_browse(url: str) -> dict:
    code, body = request_json(AETHER_BROWSE, method="POST", body={"url": url}, timeout=8.0)
    page = body.get("page") if isinstance(body, dict) else None
    ok = code == 200 and isinstance(page, dict)
    return {
        "ok": ok,
        "status": code,
        "title": (page or {}).get("title") if ok else "",
        "url": (page or {}).get("finalUrl") if ok else url,
        "error": None if ok else (body.get("error") if isinstance(body, dict) else f"HTTP {code}"),
    }


def snapshot() -> dict:
    stored = stored_handoff()
    audit = read_aether_last_url()
    aether = stored["aether"] if stored["aether"].get("url") else audit
    lumen = stored["lumen"] if stored["lumen"].get("url") else {
        "url": LINKS["lumen"],
        "title": "Lumen",
        "at": "",
        "source": "default",
    }
    live = aether_status()
    return {
        "ok": True,
        "aether": {
            **aether,
            "desk": AETHER_DESK,
            "live": live["ok"],
        },
        "lumen": {
            **lumen,
            "home": LINKS["lumen"],
        },
    }


def resolve_launch_url(target: str, url: str = "") -> dict:
    key = (target or "").strip().lower()
    raw = (url or "").strip()
    if raw:
        cleaned = normalize_url(key, raw)
        handoff = remember(key, cleaned, source="forge")
        return {"url": cleaned, "source": "given", "handoff": handoff}
    snap = snapshot()
    slot = snap[key]
    cleaned = slot.get("url") or ""
    if key == "aether" and not cleaned:
        return {"url": "", "source": "none", "handoff": stored_handoff()}
    if cleaned:
        handoff = remember(key, cleaned, title=slot.get("title") or "", source=slot.get("source") or "last")
        return {"url": cleaned, "source": slot.get("source") or "last", "handoff": handoff}
    return {"url": "", "source": "none", "handoff": stored_handoff()}
