from forge.helpers import helper_catalog, parse_review_board, probe_flash_tag, run_check_helper, run_review_helper


def test_helper_catalog_has_review_and_check():
    rows = helper_catalog()
    ids = {row["id"] for row in rows}
    assert ids == {"review", "check"}
    review = next(row for row in rows if row["id"] == "review")
    check = next(row for row in rows if row["id"] == "check")
    assert review["enabled"] is True
    assert review["model"] == "empero-35b-a3b:q4km"
    assert check["enabled"] is (probe_flash_tag() is not None)


def test_parse_review_board_reads_result_line():
    board = parse_review_board("RESULT: PASS\nSUMMARY: looks fine")
    assert board["result"] == "PASS"
    assert "board" in board


def test_run_review_helper_warns_on_empty_diff():
    board = run_review_helper("", "hello")
    assert board["result"] == "WARN"


def test_run_check_helper_warns_when_flash_missing(monkeypatch):
    monkeypatch.setattr("forge.helpers.probe_flash_tag", lambda: None)
    board = run_check_helper("diff", "hello")
    assert board["result"] == "WARN"
    assert any("flash not pulled" in L["detail"] for L in board["lines"])
