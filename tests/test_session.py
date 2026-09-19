from forge.session import ASK_TOOL_NUDGE, build_messages, normalize_history, run_ask, sanitize_ask_reply

LEAKED_TOOL_XML = """<tool name="grep">
<parameter=path>
src/*.py
</parameter>
<parameter=pattern>
import
</parameter>
</function>
</tool_call>"""


def test_normalize_history_keeps_user_and_assistant():
    raw = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "ok"},
        {"role": "system", "content": "skip"},
        {"role": "user", "content": ""},
        {"role": "assistant", "content": "second"},
    ]
    out = normalize_history(raw)
    assert out == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "ok"},
        {"role": "assistant", "content": "second"},
    ]


def test_sanitize_ask_reply_strips_tool_xml():
    assert sanitize_ask_reply(LEAKED_TOOL_XML) == ASK_TOOL_NUDGE
    assert sanitize_ask_reply("Forge can help with code.\n" + LEAKED_TOOL_XML) == "Forge can help with code."
    assert sanitize_ask_reply("plain answer") == "plain answer"


def test_ask_mode_does_not_run_file_tools(monkeypatch):
    monkeypatch.setattr(
        "forge.session.active_session",
        lambda *a, **k: {
            "tier": "chat",
            "model": "qwen3.8:27b",
            "base": "http://127.0.0.1:9",
            "blocked": False,
            "backend": {"id": "cuda", "label": "5090", "gpu": "5090", "ok": True},
        },
    )
    monkeypatch.setattr(
        "forge.session.chat",
        lambda *a, **k: {
            "text": LEAKED_TOOL_XML,
            "model": "qwen3.8:27b",
            "done": True,
            "raw": {},
            "tool_calls": [],
        },
    )
    monkeypatch.setattr("forge.session.run_tool", lambda *a, **k: (_ for _ in ()).throw(AssertionError("ask must not run tools")))
    out = run_ask("what can you do to make software?")
    assert out["text"] == ASK_TOOL_NUDGE
    assert "<tool" not in out["text"]


def test_build_messages_prepends_history_before_current_prompt():
    history = [
        {"role": "user", "content": "earlier ask"},
        {"role": "assistant", "content": "earlier answer"},
    ]
    messages = build_messages("SYS", "follow up", [], history)
    assert messages[0]["role"] == "system"
    assert messages[1]["content"] == "earlier ask"
    assert messages[2]["content"] == "earlier answer"
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "follow up"
