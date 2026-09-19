from pathlib import Path

from forge.git import run_git
from forge.project import create_project, sanitize_project_name


def test_sanitize_project_name_rejects_invalid():
    try:
        sanitize_project_name("../escape")
    except ValueError:
        pass
    else:
        raise AssertionError("expected invalid name to fail")


def test_create_project_makes_folder_git_init_and_pins_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    parent = tmp_path / "ForgeProjects"
    state = create_project("my-app", parent)
    project = parent / "my-app"
    assert project.is_dir()
    assert state["workspace"] == str(project.resolve())
    code, out, _ = run_git(project, ["rev-parse", "--is-inside-work-tree"])
    assert code == 0
    assert out.strip() == "true"
    code, remotes, _ = run_git(project, ["remote"])
    assert code == 0
    assert remotes.strip() == ""


def test_create_project_rejects_existing(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    parent = tmp_path / "ForgeProjects"
    create_project("dup", parent)
    try:
        create_project("dup", parent)
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("expected duplicate project to fail")
