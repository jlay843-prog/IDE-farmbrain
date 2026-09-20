from forge.checks import (
    _has_model,
    _http_code,
    _tcp_open,
    _tower_5090_mark,
    format_board,
    list_checks,
    run_check,
)


def test_list_checks():
    rows = list_checks()
    ids = {r["id"] for r in rows}
    assert "farm" in ids and "llm" in ids and "ray" in ids and "all" in ids


def test_run_check_list():
    board = run_check("list")
    assert board["check"] == "list"
    assert board["result"] == "PASS"
    text = format_board(board)
    assert "forge check" in text


def test_unknown_check():
    board = run_check("not-a-real-check")
    assert board["result"] == "FAIL"


def test_has_model_matches_qwen_tag_variants():
    assert _has_model(["qwen3.8:27b-q4_K_M"], "qwen3.8:27b-q4_K_M")
    assert _has_model(["qwen3.8:27b"], "qwen3.8:27b-q4_K_M")
    assert not _has_model(["qwen3-coder:30b"], "qwen3.8:27b-q4_K_M")


def test_tower_5090_vast_is_warn_not_fail():
    assert _tower_5090_mark(None, {"ok": False}, vast_active=True) is None
    assert _tower_5090_mark(42.0, {"ok": True, "gpu_pct": 0}, vast_active=True) is None


def test_tower_5090_unreachable_is_warn():
    assert _tower_5090_mark(None, {"ok": False}, vast_active=False) is None


def test_tower_5090_hot_is_fail():
    assert _tower_5090_mark(95.0, {"ok": True}, vast_active=False) is False


def test_check_all_includes_ray():
    board = run_check("all")
    labels = [L["label"] for L in board.get("lines") or []]
    assert any(lbl == "---ray---" for lbl in labels)


def test_aria_ui_uses_html_accept(monkeypatch):
    captured: dict = {}

    class FakeResp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=3.0):
        captured["accept"] = req.headers.get("Accept")
        return FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    code, _ = _http_code("http://192.168.68.103:5173/", kind="html")
    assert code == 200
    assert captured["accept"] == "*/*"


def test_blender_mcp_is_tcp_not_http():
    ok, detail = _tcp_open("127.0.0.1:1", timeout=0.2)
    assert ok is False
    assert "tcp" in detail.lower() or detail
