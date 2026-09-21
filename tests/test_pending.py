import json

from forge.pending import clear_pending_accept, load_pending_accept, pending_path, save_pending_accept


def test_pending_accept_roundtrip(tmp_path, monkeypatch):
    ws = tmp_path / "proj"
    ws.mkdir()
    monkeypatch.setenv("FORGE_DATA", str(tmp_path))
    monkeypatch.setattr("forge.pending.workspace_path", lambda: ws)
    row = save_pending_accept(
        prompt="add tests",
        diff="--- a/foo.py\n+++ b/foo.py\n@@\n+x=1\n",
        changes=[{"path": "foo.py", "mark": "M"}],
        hunks=[{"id": 0, "path": "foo.py", "header": "@@"}],
    )
    assert row and row["workspace"] == str(ws)
    loaded = load_pending_accept()
    assert loaded and loaded["diff"].startswith("--- a/foo.py")
    clear_pending_accept()
    assert load_pending_accept() is None
    assert not pending_path().is_file()


def test_pending_ignored_when_workspace_mismatch(tmp_path, monkeypatch):
    ws = tmp_path / "proj"
    ws.mkdir()
    monkeypatch.setenv("FORGE_DATA", str(tmp_path))
    monkeypatch.setattr("forge.pending.workspace_path", lambda: ws)
    save_pending_accept(prompt="x", diff="--- a\n+++ b\n", changes=[{"path": "a"}])
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setattr("forge.pending.workspace_path", lambda: other)
    assert load_pending_accept() is None
