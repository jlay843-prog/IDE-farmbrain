from forge.checks import format_board, list_checks, run_check


def test_list_checks():
    rows = list_checks()
    ids = {r["id"] for r in rows}
    assert "farm" in ids and "llm" in ids and "all" in ids


def test_run_check_list():
    board = run_check("list")
    assert board["check"] == "list"
    assert board["result"] == "PASS"
    text = format_board(board)
    assert "forge check" in text


def test_unknown_check():
    board = run_check("not-a-real-check")
    assert board["result"] == "FAIL"
