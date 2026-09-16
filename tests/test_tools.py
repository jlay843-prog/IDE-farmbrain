from pathlib import Path

from forge.session import run_edit
from forge.state import set_workspace
from forge.tools import ALLOWED, OLLAMA_TOOLS, parse_tool_markup, run_tool, tool_calls_from_reply


def _proj(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "hello.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")
    (root / "README.md").write_text("proj\nhello mentioned\n", encoding="utf-8")
    skipped = root / "node_modules" / "pkg"
    skipped.mkdir(parents=True)
    (skipped / "secret.py").write_text("TOKEN = 'do-not-grep'\n", encoding="utf-8")
    return root


def test_tools_are_read_list_grep_only():
    assert ALLOWED == ("read", "list", "grep")
    names = [row["function"]["name"] for row in OLLAMA_TOOLS]
    assert names == ["read", "list", "grep"]
    src = Path(__file__).resolve().parents[1] / "src" / "forge" / "tools.py"
    text = src.read_text(encoding="utf-8")
    assert "import subprocess" not in text
    assert "os.system" not in text
    assert "shell" in text.lower()


def test_read_list_grep_and_reject_shell(tmp_path: Path):
    root = _proj(tmp_path)
    read = run_tool(root, "read", {"path": "src/hello.py"})
    assert read["ok"] is True
    assert "return 'hi'" in read["text"]
    listed = run_tool(root, "list", {"path": "src"})
    assert listed["ok"] is True
    assert any(row["path"] == "src/hello.py" for row in listed["entries"])
    assert all("text" not in row for row in listed["entries"])
    hits = run_tool(root, "grep", {"pattern": "hello", "glob": "*.py"})
    assert hits["ok"] is True
    paths = [h["path"] for h in hits["hits"]]
    assert "src/hello.py" in paths
    assert all("node_modules" not in p for p in paths)
    secret = run_tool(root, "grep", {"pattern": "do-not-grep"})
    assert secret["hits"] == []
    blocked = run_tool(root, "shell", {"cmd": "dir"})
    assert blocked["ok"] is False
    assert "no shell" in blocked["error"]
    outside = run_tool(root, "read", {"path": "../escape.txt"})
    assert outside["ok"] is False


def test_parse_tool_markup_and_native_calls():
    xml = '<tool name="grep">{"pattern": "apply_diff", "path": "src"}</tool>'
    calls = parse_tool_markup(xml)
    assert calls == [{"name": "grep", "args": {"pattern": "apply_diff", "path": "src"}}]
    native = tool_calls_from_reply(
        "",
        {"message": {"tool_calls": [{"function": {"name": "list", "arguments": {"path": "src"}}}]}},
    )
    assert native[0]["name"] == "list"
    assert native[0]["args"]["path"] == "src"


def test_edit_tool_loop_then_diff(tmp_path: Path, monkeypatch):
    root = _proj(tmp_path)
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    set_workspace(root)
    seen = {"n": 0}

    def fake_chat(base, model, messages, tools=None, **kwargs):
        seen["n"] += 1
        if seen["n"] == 1:
            assert tools is not None
            return {
                "text": '<tool name="read">{"path": "src/hello.py"}</tool>',
                "model": model,
                "done": True,
                "raw": {},
                "tool_calls": [],
            }
        user = messages[-1]["content"]
        assert "hello.py" in user
        assert "return 'hi'" in user
        return {
            "text": "--- a/src/hello.py\n+++ b/src/hello.py\n@@ -1,2 +1,2 @@\n def hello():\n-    return 'hi'\n+    return 'hello'\n",
            "model": model,
            "done": True,
            "raw": {},
            "tool_calls": [],
        }

    monkeypatch.setattr(
        "forge.session.active_session",
        lambda *a, **k: {
            "tier": "code",
            "model": "qwen3-coder:30b",
            "base": "http://127.0.0.1:9",
            "blocked": False,
            "backend": {"id": "amd", "label": "EVO AMD", "gpu": "GTT", "ok": True},
        },
    )
    monkeypatch.setattr("forge.session.chat", fake_chat)
    out = run_edit("rename greeting", ["src/hello.py"], workspace=root)
    assert [t["name"] for t in out["tools"]] == ["read"]
    assert out["tools"][0]["ok"] is True
    assert [row["path"] for row in out["changes"]] == ["src/hello.py"]
    assert "return 'hello'" in out["text"]
