from forge.probe import is_talk_model, picker_from_models
from forge.session import active_session
from forge.state import set_tier


def test_talk_filter_drops_embeddings():
    assert is_talk_model("qwen3-coder:30b") is True
    assert is_talk_model("qwen3.8:27b") is True
    assert is_talk_model("nomic-embed-text:latest") is False
    assert is_talk_model("mxbai-embed-large") is False


def test_picker_groups_live_tags_not_toml():
    snap = {
        "vast_active": True,
        "models": [
            {"name": "qwen3-coder:30b", "role": "code", "backend": "amd", "label": "EVO AMD", "gpu": "GTT", "loaded": True, "backend_ok": True},
            {"name": "qwen2.5:14b", "role": "code", "backend": "amd", "label": "EVO AMD", "gpu": "GTT", "loaded": False, "backend_ok": True},
            {"name": "qwen3.8:27b", "role": "chat", "backend": "cuda", "label": "EVO CUDA", "gpu": "5070", "loaded": True, "backend_ok": True},
            {"name": "nomic-embed-text:latest", "role": "chat", "backend": "cuda", "label": "EVO CUDA", "gpu": "5070", "loaded": True, "backend_ok": True},
            {"name": "aria-qwen38:27b", "role": "burst", "backend": "burst", "label": "Tower", "gpu": "5090", "loaded": False, "backend_ok": True},
        ],
    }
    picker = picker_from_models(snap)
    assert [r["name"] for r in picker["groups"]["code"]] == ["qwen3-coder:30b", "qwen2.5:14b"]
    assert [r["name"] for r in picker["groups"]["chat"]] == ["qwen3.8:27b"]
    assert picker["groups"]["burst"][0]["blocked"] is True
    assert picker["defaults"]["code"] == "qwen3-coder:30b"
    assert picker["defaults"]["chat"] == "qwen3.8:27b"


def test_ask_defaults_to_chat_edit_defaults_to_code(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    set_tier("code", "qwen3-coder:30b")
    set_tier("chat", "qwen3.8:27b")

    def fake_resolve(tier, model=None):
        return {
            "tier": tier,
            "model": model or ("qwen3-coder:30b" if tier == "code" else "qwen3.8:27b"),
            "base": "http://example",
            "blocked": False,
            "backend": {"id": tier, "label": tier, "gpu": "x", "ok": True},
        }

    monkeypatch.setattr("forge.session.resolve_session", fake_resolve)
    ask = active_session(purpose="ask")
    edit = active_session(purpose="edit")
    assert ask["tier"] == "chat"
    assert ask["model"] == "qwen3.8:27b"
    assert edit["tier"] == "code"
    assert edit["model"] == "qwen3-coder:30b"


def test_burst_blocked_when_vast(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    monkeypatch.setattr(
        "forge.session.resolve_session",
        lambda tier, model=None: {
            "tier": tier,
            "model": model or "aria-qwen38:27b",
            "base": "http://tower:11434",
            "blocked": True,
            "backend": {"id": "burst", "label": "Tower 5090", "gpu": "5090", "ok": True},
        },
    )
    try:
        active_session("burst")
        raise AssertionError("expected SessionError")
    except Exception as exc:
        assert "Vast" in str(exc)
