from forge.probe import (
    _code_extra_rows,
    farm_model_rows,
    is_deepseek_model,
    is_talk_model,
    picker_from_models,
    resolve_session,
)
from forge.session import active_session
from forge.state import set_tier


def test_talk_filter_drops_embeddings():
    assert is_talk_model("qwen3-coder:30b") is True
    assert is_talk_model("qwen3.8:27b") is True
    assert is_talk_model("nomic-embed-text:latest") is False
    assert is_talk_model("mxbai-embed-large") is False


def test_code_extras_deepseek_cuda_tower():
    rows = [
        {
            "name": "deepseek-r1:14b",
            "role": "farm",
            "backend": "bc250-06",
            "label": "BC-250 06",
            "gpu": "GFX1013",
            "loaded": True,
            "backend_ok": True,
            "base": "http://192.168.68.133:11434",
        },
        {
            "name": "qwen3.8:27b",
            "role": "chat",
            "backend": "cuda",
            "label": "EVO CUDA",
            "gpu": "RTX 5070 Ti",
            "loaded": False,
            "backend_ok": True,
            "base": "http://192.168.68.103:11434",
        },
        {
            "name": "aria-qwen38:27b",
            "role": "burst",
            "backend": "burst",
            "label": "Tower 5090",
            "gpu": "RTX 5090",
            "loaded": False,
            "backend_ok": True,
            "base": "http://192.168.68.106:11434",
        },
    ]
    extras = _code_extra_rows(rows, vast=True)
    assert {r["name"] for r in extras} == {"deepseek-r1:14b", "qwen3.8:27b", "aria-qwen38:27b"}
    tower = next(r for r in extras if r["name"] == "aria-qwen38:27b")
    assert tower["blocked"] is True
    assert is_deepseek_model("deepseek-r1:14b")


def test_picker_code_includes_farm_deepseek_and_cross_host():
    snap = {
        "vast_active": False,
        "models": [
            {"name": "qwen3-coder:30b", "role": "code", "backend": "amd", "label": "EVO AMD", "gpu": "GTT", "loaded": True, "backend_ok": True, "base": "http://192.168.68.103:11437"},
            {"name": "empero-35b-a3b:q4km", "role": "code", "backend": "amd", "label": "EVO AMD", "gpu": "GTT", "loaded": True, "backend_ok": True, "base": "http://192.168.68.103:11437"},
            {"name": "deepseek-r1:14b", "role": "farm", "backend": "bc250-06", "label": "BC-250 06", "gpu": "GFX1013", "loaded": True, "backend_ok": True, "base": "http://192.168.68.133:11434"},
            {"name": "qwen3.8:27b", "role": "chat", "backend": "cuda", "label": "EVO CUDA", "gpu": "5070", "loaded": True, "backend_ok": True, "base": "http://192.168.68.103:11434"},
            {"name": "aria-qwen38:27b", "role": "burst", "backend": "burst", "label": "Tower", "gpu": "5090", "loaded": False, "backend_ok": True, "base": "http://192.168.68.106:11434"},
        ],
    }
    picker = picker_from_models(snap)
    code_names = [r["name"] for r in picker["groups"]["code"]]
    assert "qwen3-coder:30b" in code_names
    assert "empero-35b-a3b:q4km" in code_names
    assert "deepseek-r1:14b" in code_names
    assert "qwen3.8:27b" in code_names
    assert "aria-qwen38:27b" in code_names


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
    code_names = [r["name"] for r in picker["groups"]["code"]]
    assert code_names[0] == "qwen3-coder:30b"
    assert {"qwen2.5:14b", "qwen3.8:27b", "aria-qwen38:27b"}.issubset(set(code_names))
    tower = next(r for r in picker["groups"]["code"] if r["name"] == "aria-qwen38:27b")
    assert tower["blocked"] is True
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


def test_farm_model_rows_from_dials_only(monkeypatch):
    dials = {
        "body": {
            "hosts": {
                "bc250": {
                    "gpu_name": "GFX1013",
                    "nodes": [
                        {
                            "id": "bc250-06",
                            "lan_ip": "192.168.68.133",
                            "online": True,
                            "model": "deepseek-r1:14b",
                            "ollama": True,
                        }
                    ],
                }
            }
        }
    }
    monkeypatch.setattr(
        "forge.probe.probe_farm_host",
        lambda node: {**node, "ok": True, "models": node.get("models") or [{"name": "deepseek-r1:14b"}], "running": []},
    )
    rows = farm_model_rows(dials)
    assert len(rows) == 1
    assert rows[0]["name"] == "deepseek-r1:14b"
    assert rows[0]["backend"] == "bc250-06"
    assert rows[0]["role"] == "farm"


def test_resolve_session_routes_deepseek_to_bc250(monkeypatch):
    status = {
        "vast_active": False,
        "backends": {
            "amd": {
                "id": "amd",
                "label": "EVO AMD",
                "host_id": "evo",
                "gpu": "GTT",
                "base": "http://192.168.68.103:11437",
                "role": "code",
                "ok": True,
                "models": [{"name": "qwen3-coder:30b"}],
                "running": [],
            },
            "cuda": {"id": "cuda", "role": "chat", "ok": True, "models": [], "running": [], "label": "cuda", "gpu": "5070", "host_id": "evo", "base": "http://192.168.68.103:11434"},
            "burst": {"id": "burst", "role": "burst", "ok": True, "models": [], "running": [], "label": "tower", "gpu": "5090", "host_id": "tower", "base": "http://192.168.68.106:11434"},
        },
        "dials": {
            "body": {
                "hosts": {
                    "bc250": {
                        "nodes": [
                            {"id": "bc250-06", "lan_ip": "192.168.68.133", "online": True, "model": "deepseek-r1:14b", "ollama": True}
                        ]
                    }
                }
            }
        },
    }
    monkeypatch.setattr("forge.probe.status_snapshot", lambda **kw: status)
    monkeypatch.setattr(
        "forge.probe.probe_farm_host",
        lambda node: {**node, "ok": True, "models": [{"name": "deepseek-r1:14b"}], "running": [{"name": "deepseek-r1:14b"}]},
    )
    monkeypatch.setattr(
        "forge.probe.probe_backend",
        lambda bid: status["backends"][bid],
    )
    sess = resolve_session("code", "deepseek-r1:14b")
    assert sess["model"] == "deepseek-r1:14b"
    assert sess["base"] == "http://192.168.68.133:11434"
    assert sess["backend"]["id"] == "bc250-06"
    assert sess["blocked"] is False


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
