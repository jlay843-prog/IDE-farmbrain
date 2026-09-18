import os
import shutil
import subprocess
from pathlib import Path

from forge.python_find import bundled_python, find_python


def test_find_python_without_path(monkeypatch, tmp_path):
    monkeypatch.delenv("FORGE_PYTHON", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    found = find_python(tmp_path)
    assert found["ok"] is True
    assert Path(found["exe"]).is_file()
    assert found["source"] in {"known-path", "py-launcher", "path-py", "path", "bundled"}


def test_bundled_python_preferred(monkeypatch, tmp_path):
    real = find_python()
    assert real["ok"] is True
    bundled_dir = tmp_path / "python"
    bundled_dir.mkdir()
    shutil.copy2(real["exe"], bundled_dir / "python.exe")
    monkeypatch.delenv("FORGE_PYTHON", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    found = find_python(tmp_path)
    assert found["ok"] is True
    assert found["source"] == "bundled"
    assert Path(found["exe"]) == bundled_dir / "python.exe"
    assert bundled_python(tmp_path) == bundled_dir / "python.exe"


def test_repo_bundled_python_when_present():
    root = Path(__file__).resolve().parents[1]
    bundled = root / "python" / "python.exe"
    if not bundled.is_file():
        return
    found = find_python(root)
    assert found["ok"] is True
    assert found["source"] == "bundled"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    proc = subprocess.run(
        [found["exe"], "-m", "forge", "--help"],
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
    )
    assert proc.returncode == 0
    assert "usage:" in proc.stdout.lower()
