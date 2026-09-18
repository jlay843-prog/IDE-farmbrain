from forge.telegram import handle_text, handle_update, on_legion, parse_forge, probe


def test_parse_forge_ignores_other_slashes():
    assert parse_forge("/coder status") is None
    assert parse_forge("/forget") is None
    assert parse_forge("forge status") is None
    assert parse_forge("/forge") == []
    assert parse_forge("/forge help") == []
    assert parse_forge("/forge status") == ["status"]
    assert parse_forge("/forge@ForgeBot ask hello") == ["ask", "hello"]


def test_handle_blocks_edit_and_burst(monkeypatch):
    monkeypatch.setattr("forge.telegram.shell_forge", lambda argv: {"ok": True, "text": "RAN " + " ".join(argv), "argv": argv})
    assert "not available via Telegram" in handle_text("/forge edit add a flag")
    assert "blocked from Telegram" in handle_text("/forge use burst")
    assert "status only" in handle_text("/forge git commit")
    assert handle_text("/forge help").startswith("Forge on Legion")
    assert handle_text("/forge status") == "RAN status"
    assert handle_text("/forge ask what is cli.py") == "RAN ask what is cli.py"
    assert handle_text("hello") is None


def test_allowlist_and_legion(monkeypatch):
    monkeypatch.delenv("FORGE_TELEGRAM_ALLOW_HOST", raising=False)
    assert on_legion("LEGION") is True
    assert on_legion("EVO") is False
    monkeypatch.setenv("FORGE_TELEGRAM_ALLOW_HOST", "1")
    assert on_legion("EVO") is True
    reply = handle_update(
        {"message": {"text": "/forge status", "chat": {"id": 9}, "from": {"id": 9}}},
        allow={1},
    )
    assert reply["text"].startswith("Forge Telegram is allowlisted")
    monkeypatch.setattr("forge.telegram.shell_forge", lambda argv: {"ok": True, "text": "ok", "argv": argv})
    allowed = handle_update(
        {"message": {"text": "/forge which", "chat": {"id": 1}, "from": {"id": 1}}},
        allow={1},
    )
    assert allowed["text"] == "ok"


def test_probe_says_not_farm_brain():
    info = probe()
    assert info["farm_brain"] is False
    assert "cmd" in info
