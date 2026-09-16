import json
import subprocess
from pathlib import Path

from forge.cli import main
from forge.git import commit, diff_for, snapshot
from forge.serve import handle_api
from forge.state import set_workspace


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.name", "Forge Test")
    _git(path, "config", "user.email", "forge@test.local")
    _git(path, "config", "core.autocrlf", "false")
    return path


def test_snapshot_not_a_repo(tmp_path: Path):
    root = tmp_path / "plain"
    root.mkdir()
    (root / "readme.txt").write_text("hi\n", encoding="utf-8")
    snap = snapshot(root)
    assert snap["ok"] is True
    assert snap["repo"] is False
    assert snap["remotes"] == []
    assert snap["files"] == []
    assert "Not a git repository" in snap["summary"]


def test_empty_history_lists_untracked(tmp_path: Path):
    root = _init_repo(tmp_path / "empty")
    (root / "notes.txt").write_text("hello\n", encoding="utf-8")
    snap = snapshot(root)
    assert snap["repo"] is True
    assert snap["empty"] is True
    assert snap["branch"] == "main"
    assert snap["remotes"] == []
    assert snap["head"] == ""
    assert snap["upstream"] is None
    paths = [row["path"] for row in snap["files"]]
    assert "notes.txt" in paths
    assert all(row["status"] == "untracked" for row in snap["files"] if row["path"] == "notes.txt")
    diff = diff_for(root, "notes.txt")
    assert diff["ok"] is True
    assert "new file mode" in diff["diff"]
    assert "+hello" in diff["diff"]


def test_status_diff_commit_roundtrip(tmp_path: Path):
    root = _init_repo(tmp_path / "repo")
    (root / "app.py").write_text("print(1)\n", encoding="utf-8")
    first = commit(root, "first", ["app.py"])
    assert first["committed"] is True
    assert first["empty"] is False
    assert first["files"] == []
    assert first["remotes"] == []
    (root / "app.py").write_text("print(2)\n", encoding="utf-8")
    (root / "extra.py").write_text("x = 1\n", encoding="utf-8")
    snap = snapshot(root)
    kinds = {row["path"]: row["status"] for row in snap["files"]}
    assert kinds["app.py"] == "modified"
    assert kinds["extra.py"] == "untracked"
    changed = diff_for(root, "app.py")
    assert "-print(1)" in changed["diff"]
    assert "+print(2)" in changed["diff"]
    untracked = diff_for(root, "extra.py")
    assert "+x = 1" in untracked["diff"]
    after = commit(root, "second", ["app.py", "extra.py"])
    assert after["files"] == []
    assert after["message"] == "second"


def test_commit_rejects_empty_message_and_escape(tmp_path: Path):
    root = _init_repo(tmp_path / "safe")
    (root / "a.py").write_text("a\n", encoding="utf-8")
    try:
        commit(root, "   ", ["a.py"])
        raise AssertionError("empty message should fail")
    except ValueError as exc:
        assert "empty" in str(exc).lower()
    try:
        commit(root, "nope", ["../outside.py"])
        raise AssertionError("path escape should fail")
    except ValueError as exc:
        assert "outside" in str(exc).lower()


def test_no_remote_invented(tmp_path: Path):
    root = _init_repo(tmp_path / "local")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    snap = snapshot(root)
    assert "origin" not in json.dumps(snap)
    assert snap["remotes"] == []
    assert snap["upstream"] is None


def test_api_git_status_diff_commit(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    root = _init_repo(tmp_path / "proj")
    (root / "hello.py").write_text("print('hi')\n", encoding="utf-8")
    set_workspace(root)
    status, payload, _ = handle_api("GET", "/api/git", {}, {})
    assert status == 200
    data = json.loads(payload)
    assert data["repo"] is True
    assert data["empty"] is True
    assert data["remotes"] == []
    assert any(row["path"] == "hello.py" for row in data["files"])
    status, payload, _ = handle_api("GET", "/api/git/diff", {"path": ["hello.py"]}, {})
    assert status == 200
    diff = json.loads(payload)
    assert "+print('hi')" in diff["diff"]
    status, payload, _ = handle_api(
        "POST",
        "/api/git/commit",
        {},
        {"message": "hello", "paths": ["hello.py"]},
    )
    assert status == 200
    committed = json.loads(payload)
    assert committed["committed"] is True
    assert committed["empty"] is False
    assert committed["files"] == []
    desk_status, desk_payload, _ = handle_api("GET", "/api/desk", {}, {})
    assert desk_status == 200
    desk = json.loads(desk_payload)
    assert desk["git"]["repo"] is True
    assert desk["git"]["empty"] is False


def test_api_git_nothing_to_commit(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    root = _init_repo(tmp_path / "clean")
    (root / "ok.py").write_text("1\n", encoding="utf-8")
    commit(root, "seed", ["ok.py"])
    set_workspace(root)
    status, payload, _ = handle_api("POST", "/api/git/commit", {}, {"message": "noop", "paths": []})
    assert status == 400
    data = json.loads(payload)
    assert "Nothing to commit" in data["error"]


def test_cli_git_status_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    root = _init_repo(tmp_path / "cli")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    set_workspace(root)
    assert main(["git", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["repo"] is True
    assert data["empty"] is True
    assert data["remotes"] == []
    assert any(row["path"] == "a.txt" for row in data["files"])
