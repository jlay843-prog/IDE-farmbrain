from forge.session import build_messages, normalize_history


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
