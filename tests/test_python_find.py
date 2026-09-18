from pathlib import Path

from forge.python_find import find_python


def test_find_python_without_path(monkeypatch, tmp_path):
    monkeypatch.delenv("FORGE_PYTHON", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    found = find_python(tmp_path)
    assert found["ok"] is True
    assert Path(found["exe"]).is_file()
    assert found["source"] in {"known-path", "py-launcher", "path-py", "path", "bundled"}
