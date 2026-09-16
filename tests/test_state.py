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
    assert saved["projects"][0]["model"] == "qwen3.8:27b"
    other = tmp_path / "other"
    other.mkdir()
    assigned = st.assign_project(str(other), tier="code", model="qwen3-coder:30b")
    assert assigned["projects"][0]["path"] == str(other.resolve())
    assert assigned["projects"][0]["tier"] == "code"


def test_protected_name(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    farm = tmp_path / "farm-brain"
    farm.mkdir()
    st.set_workspace(farm)
    assert st.is_protected_workspace() is True
