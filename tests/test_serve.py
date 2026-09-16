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
    assert b"recipes" in payload
    assert b"links" in payload
    assert b"log_path" in payload


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
