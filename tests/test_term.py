from pathlib import Path
import time

from forge import term
from forge.serve import handle_api
from forge.state import set_workspace
import json


def test_term_is_not_a_model_tool():
    src = Path(__file__).resolve().parents[1] / "src" / "forge" / "term.py"
    text = src.read_text(encoding="utf-8")
    assert "never a model tool" in text.lower() or "Not a model tool" in text or "never a model tool" in text
    snap = term.snapshot()
    assert snap["model_tool"] is False


def test_term_echo_in_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    root = tmp_path / "proj"
    root.mkdir()
    set_workspace(root)
    term.stop()
    try:
        started = term.start(root)
        assert started["ok"] is True
        assert started["running"] is True
        term.write("echo forge-term-pane")
        text = ""
        for _ in range(40):
            time.sleep(0.1)
            text = term.snapshot()["text"]
            if "forge-term-pane" in text:
                break
        assert "forge-term-pane" in text
        status, payload, _ = handle_api("GET", "/api/term", {}, {})
        assert status == 200
        data = json.loads(payload)
        assert data["running"] is True
        assert data["model_tool"] is False
    finally:
        term.stop()
