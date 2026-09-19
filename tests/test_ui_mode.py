import json
from pathlib import Path

from forge.state import default_state, load_state, resolve_ui_mode, set_ui_mode


def test_default_easy_without_workspace():
    state = default_state()
    state["workspace"] = ""
    state.pop("ui_mode", None)
    assert resolve_ui_mode(state) == "easy"


def test_existing_workspace_defaults_advanced_when_mode_missing():
    state = default_state()
    state["workspace"] = "C:\\work\\proj"
    state.pop("ui_mode", None)
    assert resolve_ui_mode(state) == "advanced"


def test_set_ui_mode_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    saved = set_ui_mode("easy")
    assert saved["ui_mode"] == "easy"
    assert load_state()["ui_mode"] == "easy"


def test_desk_bootstrap_includes_ui_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    from forge.serve import handle_api

    status, payload, _ = handle_api("GET", "/api/desk", {}, {})
    data = json.loads(payload)
    assert status == 200
    assert data["ui_mode"] in {"easy", "advanced"}
    assert "easy_defaults" in data
    assert "parent" in data["easy_defaults"]


def test_projects_create_api(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    from forge.serve import handle_api

    parent = tmp_path / "ForgeProjects"
    status, payload, _ = handle_api(
        "POST",
        "/api/projects/create",
        {},
        {"name": "desk-demo", "parent": str(parent)},
    )
    data = json.loads(payload)
    assert status == 200
    assert data["ok"] is True
    assert Path(data["state"]["workspace"]) == (parent / "desk-demo").resolve()
