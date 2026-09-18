import json

from forge.log import log_turn
from forge.serve import handle_api, sse_bytes


def test_health():
    status, payload, ctype = handle_api("GET", "/api/health", {}, {})
    assert status == 200
    assert b"forge" in payload
    assert "json" in ctype


def test_health_reports_monaco_vendor():
    from forge.health import MONACO_LOADER

    status, payload, _ = handle_api("GET", "/api/health", {}, {})
    data = json.loads(payload)
    assert data["monaco"]["ok"] == MONACO_LOADER.is_file()
    if MONACO_LOADER.is_file():
        assert "loader.js" in data["monaco"]["path"]


def test_desk_bootstrap():
    status, payload, _ = handle_api("GET", "/api/desk", {}, {})
    assert status == 200
    data = json.loads(payload)
    assert "recipes" in data
    assert "links" in data
    assert "log_path" in data
    assert "tree" in data
    assert "crumbs" in data["tree"]
    assert isinstance(data.get("protected"), bool)
    assert "protected_hint" in data


def test_sse_bytes_are_event_stream_frames():
    raw = sse_bytes({"delta": "Hel"})
    assert raw.startswith(b"data: ")
    assert raw.endswith(b"\n\n")
    assert json.loads(raw.decode("utf-8")[len("data: ") :].strip())["delta"] == "Hel"


def test_log_endpoint_reads_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    log_turn("ask", {"tier": "chat", "model": "qwen3.8:27b", "backend": "cuda", "gpu": "5070"}, "hello from cli")
    status, payload, _ = handle_api("GET", "/api/log", {"limit": ["20"]}, {})
    assert status == 200
    data = json.loads(payload)
    assert data["ok"] is True
    assert data["turns"][0]["prompt"] == "hello from cli"
    assert "sessions.jsonl" in data["path"]


def test_edit_endpoint_includes_change_list(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    monkeypatch.setattr(
        "forge.serve.run_edit",
        lambda prompt, files, **kwargs: {
            "ok": True,
            "kind": "edit",
            "tier": "code",
            "model": "qwen3-coder:30b",
            "backend": "amd",
            "gpu": "GTT",
            "text": "--- a/a.py\n+++ b/a.py\n@@ -1 +1,2 @@\n-a\n+b\n+c\n--- /dev/null\n+++ b/b.py\n@@ -0,0 +1 @@\n+x\n",
            "files": files or [],
            "changes": [
                {"path": "a.py", "kind": "modified", "new": False, "delete": False, "hunks": 1, "added": 2, "deleted": 1},
                {"path": "b.py", "kind": "added", "new": True, "delete": False, "hunks": 1, "added": 1, "deleted": 0},
            ],
            "applied": False,
            "changed": [],
            "protected": False,
        },
    )
    status, payload, _ = handle_api("POST", "/api/edit", {}, {"prompt": "two files", "files": ["a.py"]})
    assert status == 200
    data = json.loads(payload)
    assert [row["path"] for row in data["changes"]] == ["a.py", "b.py"]
    assert data["changes"][1]["kind"] == "added"


def test_apply_endpoint_accepts_hunk_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    from forge.state import set_workspace

    root = tmp_path / "proj"
    root.mkdir()
    (root / "hello.py").write_text('def hello():\n    return "hi"\n\ndef other():\n    return 1\n', encoding="utf-8")
    set_workspace(root)
    diff = """--- a/hello.py
+++ b/hello.py
@@ -1,2 +1,2 @@
 def hello():
-    return "hi"
+    return "hello"
@@ -4,2 +4,2 @@
 def other():
-    return 1
+    return 2
"""
    status, payload, _ = handle_api("POST", "/api/apply", {}, {"diff": diff, "hunks": [1]})
    assert status == 200
    data = json.loads(payload)
    assert data["changed"] == ["hello.py"]
    assert data["hunks"] == [1]
    text = (root / "hello.py").read_text(encoding="utf-8")
    assert 'return "hi"' in text
    assert "return 2" in text


def test_apply_farm_brain_requires_confirm(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    from forge.state import set_workspace

    root = tmp_path / "farm-brain"
    root.mkdir()
    (root / "hello.py").write_text("x = 1\n", encoding="utf-8")
    set_workspace(root)
    desk_status, desk_payload, _ = handle_api("GET", "/api/desk", {}, {})
    assert desk_status == 200
    desk = json.loads(desk_payload)
    assert desk["protected"] is True
    assert "QC gate" in desk["protected_hint"]
    diff = """--- a/hello.py
+++ b/hello.py
@@ -1 +1 @@
-x = 1
+x = 2
"""
    blocked, payload, _ = handle_api("POST", "/api/apply", {}, {"diff": diff})
    assert blocked == 409
    assert b"confirm_protected" in payload
    assert (root / "hello.py").read_text(encoding="utf-8") == "x = 1\n"
    ok, applied, _ = handle_api("POST", "/api/apply", {}, {"diff": diff, "confirm_protected": True})
    assert ok == 200
    data = json.loads(applied)
    assert data["changed"] == ["hello.py"]
    assert (root / "hello.py").read_text(encoding="utf-8") == "x = 2\n"


def test_desk_ask_appends_session_log(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    monkeypatch.setattr(
        "forge.serve.run_ask",
        lambda prompt, files, **kwargs: {
            "ok": True,
            "kind": "ask",
            "tier": "chat",
            "model": "qwen3.8:27b",
            "backend": "cuda",
            "gpu": "5070",
            "text": "hi",
            "files": [],
        },
    )
    status, payload, _ = handle_api("POST", "/api/ask", {}, {"prompt": "desk ask"})
    assert status == 200
    assert b"qwen3.8:27b" in payload
    text = (tmp_path / "data" / "sessions.jsonl").read_text(encoding="utf-8")
    assert "desk ask" in text
    assert '"kind": "ask"' in text


def test_files_listing_has_crumbs(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    from forge.state import set_workspace

    root = tmp_path / "proj"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "hello.py").write_text("x\n", encoding="utf-8")
    set_workspace(root)
    status, payload, _ = handle_api("GET", "/api/files", {"path": ["src/pkg"]}, {})
    assert status == 200
    data = json.loads(payload)
    assert data["cwd"] == "src/pkg"
    assert data["parent"] == "src"
    assert data["crumbs"][-1]["path"] == "src/pkg"
    assert data["entries"][0]["name"] == "hello.py"
    assert "text" not in data["entries"][0]


def test_file_put_writes_named_file(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    from forge.state import set_workspace

    root = tmp_path / "proj"
    root.mkdir()
    set_workspace(root)
    status, payload, _ = handle_api(
        "PUT",
        "/api/file",
        {},
        {"path": "notes.txt", "text": "saved from desk\n"},
    )
    assert status == 200
    data = json.loads(payload)
    assert data["ok"] is True
    assert (root / "notes.txt").read_text(encoding="utf-8") == "saved from desk\n"


def test_files_search_returns_paths_not_contents(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    from forge.state import set_workspace

    root = tmp_path / "proj"
    secret = "do-not-send-this-to-the-model"
    (root / "src").mkdir(parents=True)
    (root / "src" / "hello.py").write_text(secret + "\n", encoding="utf-8")
    (root / "node_modules" / "pkg").mkdir(parents=True)
    (root / "node_modules" / "pkg" / "hello.js").write_text(secret + "\n", encoding="utf-8")
    set_workspace(root)
    status, payload, _ = handle_api("GET", "/api/files/search", {"q": ["hello"]}, {})
    assert status == 200
    data = json.loads(payload)
    assert data["ok"] is True
    paths = [row["path"] for row in data["entries"]]
    assert "src/hello.py" in paths
    assert all("node_modules" not in path for path in paths)
    assert all("text" not in row for row in data["entries"])
    raw = payload.decode("utf-8")
    assert secret not in raw


def test_vault_search_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    vault = tmp_path / "FarmBrainVault"
    (vault / "01-Daily").mkdir(parents=True)
    (vault / "01-Daily" / "note.md").write_text("# hello vault search\n", encoding="utf-8")
    monkeypatch.setenv("FORGE_VAULT", str(vault))
    status, payload, _ = handle_api("GET", "/api/vault/search", {"q": ["hello vault"]}, {})
    assert status == 200
    data = json.loads(payload)
    assert data["ok"] is True
    assert data["entries"][0]["path"] == "01-Daily/note.md"
    assert "hello vault" in data["entries"][0]["snippet"]
    desk_status, desk_payload, _ = handle_api("GET", "/api/desk", {}, {})
    assert desk_status == 200
    desk = json.loads(desk_payload)
    assert desk["vault"]["exists"] is True
    assert "text" not in data["entries"][0]
    assert "handoff" in desk
    assert "aether" in desk["handoff"]
    assert "lumen" in desk["handoff"]
