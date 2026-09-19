import json
from io import BytesIO

from forge.httputil import iter_ndjson
from forge.llm import chat, iter_chat, ollama_tool_xml_error


class FakeResp:
    def __init__(self, payload: bytes, status: int = 200):
        self.status = status
        self._buf = BytesIO(payload)

    def readline(self):
        return self._buf.readline()

    def read(self, n: int = -1):
        return self._buf.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_chat_sends_stream_true_and_joins_deltas(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResp(
            b'{"message":{"content":"Hel"},"done":false}\n'
            b'{"message":{"content":"lo"},"done":false}\n'
            b'{"message":{"content":""},"done":true,"model":"qwen3.8:27b"}\n'
        )

    monkeypatch.setattr("forge.httputil.urllib.request.urlopen", fake_urlopen)
    out = chat("http://192.168.68.103:11434", "qwen3.8:27b", [{"role": "user", "content": "hi"}])
    assert seen["url"].endswith("/api/chat")
    assert seen["body"]["stream"] is True
    assert out["text"] == "Hello"
    assert out["model"] == "qwen3.8:27b"


def test_iter_chat_passes_tools(monkeypatch):
    seen = {"calls": 0}

    def fake_urlopen(req, timeout=None):
        seen["calls"] += 1
        body = json.loads(req.data.decode("utf-8"))
        if seen["calls"] == 1:
            assert "tools" in body
            raise RuntimeError(
                "Ollama http://x returned error: expected element type <function> but have <parameter>"
            )
        assert "tools" not in body
        return FakeResp(b'{"message":{"content":"ok"},"done":true}\n')

    monkeypatch.setattr("forge.httputil.urllib.request.urlopen", fake_urlopen)
    chunks = list(
        iter_chat(
            "http://x",
            "m",
            [{"role": "assistant", "content": "<parameter=path>src</parameter>"}],
            tools=[{"type": "function", "function": {"name": "list"}}],
        )
    )
    assert seen["calls"] == 2
    assert chunks[-1]["delta"] == "ok"


def test_ollama_tool_xml_error_matches_parser_message():
    err = RuntimeError("expected element type <function> but have <parameter>")
    assert ollama_tool_xml_error(err) is True


def test_iter_chat_streams_without_tools(monkeypatch):
    def fake_urlopen(req, timeout=None):
        return FakeResp(b'{"message":{"content":"A"},"done":false}\n{"message":{"content":"B"},"done":true}\n')

    monkeypatch.setattr("forge.httputil.urllib.request.urlopen", fake_urlopen)
    chunks = list(iter_chat("http://x", "m", [{"role": "user", "content": "hi"}]))
    assert [c["delta"] for c in chunks] == ["A", "B"]
    assert chunks[-1]["done"] is True


def test_iter_ndjson_reads_lines(monkeypatch):
    def fake_urlopen(req, timeout=None):
        return FakeResp(b'{"a":1}\n\n{"b":2}\n')

    monkeypatch.setattr("forge.httputil.urllib.request.urlopen", fake_urlopen)
    rows = list(iter_ndjson("http://x", body={"stream": True}))
    assert rows == [{"a": 1}, {"b": 2}]
