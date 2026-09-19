from forge.easy import classify_easy_prompt


def test_classify_capability_question_as_ask():
    assert classify_easy_prompt("what can you do to make software?") == "ask"
    assert classify_easy_prompt("How does Forge work?") == "ask"
    assert classify_easy_prompt("explain the edit loop") == "ask"


def test_classify_create_change_as_edit():
    assert classify_easy_prompt("create a hello world script") == "edit"
    assert classify_easy_prompt("add tests for the parser") == "edit"
    assert classify_easy_prompt("fix the greeting function") == "edit"


def test_classify_mixed_capability_stays_ask():
    assert classify_easy_prompt("what can you do to create a todo app?") == "ask"
