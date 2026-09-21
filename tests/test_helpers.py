from forge.flash import probe_flash_tag
from forge.helpers import (
    augment_prompt_with_plan,
    helper_catalog,
    parse_review_board,
    run_check_helper,
    run_edit_helpers,
    run_plan_helper,
    run_review_helper,
)


def test_helper_catalog_has_plan_review_and_check():
    rows = helper_catalog()
    ids = {row["id"] for row in rows}
    assert ids == {"plan", "review", "check"}
    plan = next(row for row in rows if row["id"] == "plan")
    review = next(row for row in rows if row["id"] == "review")
    check = next(row for row in rows if row["id"] == "check")
    assert review["enabled"] is True
    assert review["model"] == "empero-35b-a3b:q4km"
    flash_live = probe_flash_tag() is not None
    assert plan["enabled"] is flash_live
    assert check["enabled"] is flash_live


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
    assert any("flash not reachable" in L["detail"] for L in board["lines"])


def test_run_plan_helper_warns_when_flash_missing(monkeypatch):
    monkeypatch.setattr("forge.helpers.probe_flash_tag", lambda: None)
    board = run_plan_helper("build a widget")
    assert board["result"] == "WARN"


def test_augment_prompt_with_plan_appends_plan_text():
    augmented = augment_prompt_with_plan("add tests", {"text": "step one\nstep two"})
    assert "PLAN (5090 flash" in augmented
    assert "step one" in augmented


def test_run_edit_helpers_without_live_flash(monkeypatch):
    monkeypatch.setattr("forge.helpers.probe_flash_tag", lambda: None)
    prompt, boards, used = run_edit_helpers(["plan"], "add tests", None)
    assert used is False
    assert prompt == "add tests"
    assert boards and boards[0]["helper"] == "plan"
