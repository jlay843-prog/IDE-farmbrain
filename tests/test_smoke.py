"""W13 smoke checks — loopback desk only, no invented remotes."""

import json
import shutil

from forge import __version__
from forge.health import health_snapshot
from forge.serve import handle_api


def test_health_snapshot_matches_api():
    snap = health_snapshot()
    status, payload, _ = handle_api("GET", "/api/health", {}, {})
    assert status == 200
    assert snap == json.loads(payload)


def test_health_reports_v1():
    status, payload, ctype = handle_api("GET", "/api/health", {}, {})
    assert status == 200
    data = json.loads(payload)
    assert data["ok"] is True
    assert data["name"] == "forge"
    assert data["version"] == __version__
    assert data["version"] == "1.3.0"
    assert "json" in ctype
    assert data["python"]["ok"] is True
    assert data["python"]["exe"]
    assert "monaco" in data
    assert isinstance(data["monaco"]["ok"], bool)


def test_desk_bootstrap_has_no_invented_remotes():
    status, payload, _ = handle_api("GET", "/api/desk", {}, {})
    assert status == 200
    data = json.loads(payload)
    assert data["ok"] is True
    git = data.get("git") or {}
    for remote in git.get("remotes") or []:
        if isinstance(remote, str):
            assert remote.strip()
            continue
        url = str(remote.get("url") or "")
        assert url, "remote rows must be real git config, not placeholders"
        assert "example.com" not in url
        assert "invented" not in url.lower()
    assert isinstance(data.get("protected"), bool)
    assert isinstance(data.get("protected_hint"), str)
    assert "term" in data
    assert data["term"]["model_tool"] is False
    names = [str(row.get("name") or "") for row in (data.get("state") or {}).get("projects") or []]
    assert "forge-w7-farm-brain" not in names
    temp_farm = [row for row in ((data.get("state") or {}).get("projects") or []) if str(row.get("name") or "") == "farm-brain" and "\\Temp\\" in str(row.get("path") or "")]
    assert temp_farm == []


def test_python_available_for_packaged_desk():
    assert shutil.which("py") or shutil.which("python") or shutil.which("python3")
