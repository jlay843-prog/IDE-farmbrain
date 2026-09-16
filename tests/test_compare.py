from forge.compare import default_candidates, match_live_model, parse_verdict, run_compare
from forge.session import SessionError


def test_parse_verdict_reads_winner_line():
    verdict = parse_verdict("WINNER: 2\nREASON: Cleaner diff and matches the file.", 3)
    assert verdict["winner"] == 2
    assert "Cleaner" in verdict["reason"]
    assert verdict["parsed"] is True


def test_parse_verdict_falls_back_when_missing():
    verdict = parse_verdict("I like the second one.", 2)
    assert verdict["winner"] == 1
    assert verdict["parsed"] is False


def test_match_skips_blocked_burst():
    picker = {
        "groups": {
            "code": [],
            "chat": [],
            "burst": [{"name": "aria-qwen38:27b", "tier": "burst", "blocked": True}],
        }
    }
    try:
        match_live_model("aria-qwen38:27b", picker=picker)
        raise AssertionError("expected blocked")
    except SessionError as exc:
        assert "Vast" in str(exc)


def test_default_candidates_cap_and_skip_burst():
    picker = {
        "groups": {
            "code": [
                {"name": "qwen3-coder:30b", "tier": "code", "blocked": False},
                {"name": "qwen2.5:14b", "tier": "code", "blocked": False},
            ],
            "chat": [{"name": "qwen3.8:27b", "tier": "chat", "blocked": False}],
            "burst": [{"name": "aria-qwen38:27b", "tier": "burst", "blocked": True}],
        }
    }
    state = {"code_model": "qwen3-coder:30b", "chat_model": "qwen3.8:27b"}
    rows = default_candidates("ask", picker=picker, state=state)
    assert len(rows) == 3
    assert {r["model"] for r in rows} == {"qwen3.8:27b", "qwen3-coder:30b", "qwen2.5:14b"}
    assert all(r["model"] != "aria-qwen38:27b" for r in rows)


def test_compare_needs_two_models(monkeypatch):
    monkeypatch.setattr(
        "forge.compare.picker_snapshot",
        lambda: {"groups": {"code": [{"name": "qwen3-coder:30b", "tier": "code", "blocked": False}], "chat": [], "burst": []}},
    )
    try:
        run_compare("ask", "hello", [], [{"tier": "code", "model": "qwen3-coder:30b"}])
        raise AssertionError("expected SessionError")
    except SessionError as exc:
        assert "at least two" in str(exc)


def test_compare_never_applies(monkeypatch):
    picker = {
        "groups": {
            "code": [{"name": "qwen3-coder:30b", "tier": "code", "blocked": False}],
            "chat": [{"name": "qwen3.8:27b", "tier": "chat", "blocked": False}],
            "burst": [],
        }
    }
    monkeypatch.setattr("forge.compare.picker_snapshot", lambda: picker)

    def fake_ask(prompt, files, tier=None, model=None):
        return {"ok": True, "kind": "ask", "tier": tier, "model": model, "backend": tier, "gpu": "x", "base": "http://x", "text": f"ans {model}"}

    def fake_judge(kind, prompt, files, candidates):
        return {
            "model": "qwen3-coder:30b",
            "tier": "code",
            "backend": "amd",
            "gpu": "Strix Halo GTT",
            "base": "http://192.168.68.103:11437",
            "text": "WINNER: 1\nREASON: First is enough.",
            "winner": 1,
            "reason": "First is enough.",
            "parsed": True,
            "pick_model": candidates[0]["model"],
            "pick_text": candidates[0]["text"],
        }

    monkeypatch.setattr("forge.compare.run_ask", fake_ask)
    monkeypatch.setattr("forge.compare._judge", fake_judge)
    out = run_compare("ask", "What is Forge?", [], [{"tier": "chat", "model": "qwen3.8:27b"}, {"tier": "code", "model": "qwen3-coder:30b"}])
    assert out["applied"] is False
    assert out["judge"]["pick_model"] == "qwen3.8:27b"
    assert out["text"] == "ans qwen3.8:27b"
    assert out["judge"]["model"] == "qwen3-coder:30b"
