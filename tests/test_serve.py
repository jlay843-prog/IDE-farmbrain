import json

from forge.log import log_turn
from forge.serve import handle_api, sse_bytes


def test_health():
    status, payload, ctype = handle_api("GET", "/api/health", {}, {})
    assert status == 200
    assert b"forge" in payload
    assert "json" in ctype


def test_desk_bootstrap():
    status, payload, _ = handle_api("GET", "/api/desk", {}, {})
    assert status == 200
    data = json.loads(payload)
    assert "recipes" in data
    assert "links" in data
    assert "log_path" in data
    assert "tree" in data
    assert "crumbs" in data["tree"]


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
