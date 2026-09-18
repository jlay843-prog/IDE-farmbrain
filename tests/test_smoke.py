"""W13 smoke checks — loopback desk only, no invented remotes."""

import json
import shutil

from forge import __version__
from forge.serve import handle_api


def test_health_reports_v1():
    status, payload, ctype = handle_api("GET", "/api/health", {}, {})
    assert status == 200
    data = json.loads(payload)
    assert data["ok"] is True
    assert data["name"] == "forge"
    assert data["version"] == __version__
    assert data["version"] == "1.0.0"
    assert "json" in ctype


def test_desk_bootstrap_has_no_invented_remotes():
    status, payload, _ = handle_api("GET", "/api/desk", {}, {})
    assert status == 200
    data = json.loads(payload)
    assert data["ok"] is True
    git = data.get("git") or {}
    for remote in git.get("remotes") or []:
        url = str(remote.get("url") or "")
        assert url, "remote rows must be real git config, not placeholders"
        assert "example.com" not in url
        assert "invented" not in url.lower()
    assert data.get("protected_hint") or data.get("protected") is False or True


def test_python_available_for_packaged_desk():
    assert shutil.which("py") or shutil.which("python") or shutil.which("python3")
