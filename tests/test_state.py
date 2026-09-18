from pathlib import Path

from forge import state as st


def test_workspace_and_assign(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    project = tmp_path / "demo"
    project.mkdir()
    saved = st.set_workspace(project)
    assert Path(saved["workspace"]) == project.resolve()
    saved = st.set_tier("chat", "qwen3.8:27b")
    assert saved["tier"] == "chat"
    assert saved["chat_model"] == "qwen3.8:27b"
    saved = st.set_tier("code", "qwen3-coder:30b")
    assert saved["code_model"] == "qwen3-coder:30b"
    assert saved["projects"][0]["model"] == "qwen3-coder:30b"
    other = tmp_path / "other"
    other.mkdir()
    assigned = st.assign_project(str(other), tier="code", model="qwen3-coder:30b")
    assert assigned["projects"][0]["path"] == str(other.resolve())
    assert assigned["projects"][0]["tier"] == "code"


def test_prunes_w7_leftover_project_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("TEMP", str(tmp_path / "Temp"))
    monkeypatch.setenv("TMP", str(tmp_path / "Temp"))
    keep = tmp_path / "keep-me"
    keep.mkdir()
    temp = tmp_path / "Temp"
    temp.mkdir()
    leftover_farm = temp / "farm-brain"
    leftover_farm.mkdir()
    leftover_w7 = temp / "forge-w7-farm-brain"
    leftover_w7.mkdir()
    missing = tmp_path / "gone"
    state = st.default_state()
    state["projects"] = [
        {"path": str(keep), "name": "keep-me", "tier": "code", "model": "qwen3-coder:30b"},
        {"path": str(leftover_farm), "name": "farm-brain", "tier": "code", "model": "qwen3-coder:30b"},
        {"path": str(leftover_w7), "name": "forge-w7-farm-brain", "tier": "code", "model": "qwen3-coder:30b"},
        {"path": str(missing), "name": "ghost", "tier": "code", "model": "qwen3-coder:30b"},
    ]
    cleaned, changed = st.prune_projects(state)
    assert changed is True
    names = [row["name"] for row in cleaned["projects"]]
    assert names == ["keep-me"]


def test_protected_name(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    farm = tmp_path / "farm-brain"
    farm.mkdir()
    st.set_workspace(farm)
    assert st.is_protected_workspace() is True
    nearby = tmp_path / "farm-brain-notes"
    nearby.mkdir()
    st.set_workspace(nearby)
    assert st.is_protected_workspace() is False
