from forge.flash import probe_flash_tag
from forge.helpers import (
    PLAN_IMPLEMENT,
    PLAN_SYSTEM,
    attach_post_edit_helpers,
    augment_prompt_with_plan,
    has_pending_diff,
    helper_catalog,
    named_files_for_plan,
    parse_plan_files,
    parse_review_board,
    run_assure_helper,
    run_check_helper,
    run_edit_helpers,
    run_helpers,
    run_plan_helper,
    run_review_helper,
    scan_pending_diff,
)


def test_helper_catalog_has_plan_review_assure_and_check():
    rows = helper_catalog()
    ids = {row["id"] for row in rows}
    assert ids == {"plan", "review", "assure", "check"}
    plan = next(row for row in rows if row["id"] == "plan")
    review = next(row for row in rows if row["id"] == "review")
    assure = next(row for row in rows if row["id"] == "assure")
    check = next(row for row in rows if row["id"] == "check")
    assert review["enabled"] is True
    assert review["model"] == "empero-35b-a3b:q4km"
    assert assure["enabled"] is True
    assert assure["model"] == "local"
    assert assure["tier"] == "local"
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
    assert PLAN_IMPLEMENT in augmented
    assert "unified diff" in augmented.lower()


def test_plan_system_asks_json_not_vibe():
    lowered = PLAN_SYSTEM.lower()
    assert "vibe coding" not in lowered
    assert "no vibe" in lowered
    assert "files" in PLAN_SYSTEM
    assert "edits" in PLAN_SYSTEM
    assert "qwen3.8-flash-next" in PLAN_SYSTEM


def test_parse_plan_files_from_json_and_edits():
    text = '{"goal": "greet", "files": ["notes.txt"], "edits": [{"path": "src/hello.py", "change": "rename"}]}'
    assert parse_plan_files(text) == ["notes.txt", "src/hello.py"]
    fenced = "```json\n" + text + "\n```"
    assert parse_plan_files(fenced) == ["notes.txt", "src/hello.py"]
    assert parse_plan_files("FILES: notes.txt, src/hello.py") == ["notes.txt", "src/hello.py"]
    assert parse_plan_files('{"files": ["../escape.txt"]}') == []
    assert parse_plan_files('{"files": ["C:\\\\abs.txt"]}') == []


def test_named_files_for_plan_keeps_existing_workspace_paths(tmp_path):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "notes.txt").write_text("hello farm\n", encoding="utf-8")
    (root / "src" / "hello.py").write_text("x = 1\n", encoding="utf-8")
    plan = {"text": '{"files": ["notes.txt", "missing.py"], "edits": [{"path": "src/hello.py"}]}'}
    out = named_files_for_plan([], plan, workspace=root)
    assert out == ["notes.txt", "src/hello.py"]


def test_run_edit_helpers_without_live_flash(monkeypatch):
    monkeypatch.setattr("forge.helpers.probe_flash_tag", lambda: None)
    prompt, boards, used = run_edit_helpers(["plan"], "add tests", None)
    assert used is False
    assert prompt == "add tests"
    assert boards and boards[0]["helper"] == "plan"


def test_has_pending_diff_requires_unified_diff_or_changes():
    assert has_pending_diff({"text": "", "changes": []}) is False
    assert has_pending_diff({"text": "hello", "changes": []}) is False
    assert has_pending_diff({"text": "--- a\n+++ b\n", "changes": []}) is True
    assert has_pending_diff({"text": "x", "changes": [{"path": "a.py"}]}) is True


def test_run_helpers_skips_review_without_pending_diff(monkeypatch):
    called = []
    monkeypatch.setattr(
        "forge.helpers.run_review_helper",
        lambda *args, **kwargs: called.append(True) or {"helper": "review", "result": "PASS", "lines": [], "board": ""},
    )
    boards = run_helpers(["review"], {"text": "prose only", "changes": []}, "hello")
    assert not called
    assert boards[0]["helper"] == "review"
    assert "Skipped" in boards[0]["lines"][0]["detail"]


def test_run_helpers_runs_review_after_pending_diff(monkeypatch):
    called = []
    phases = []

    def fake_review(*_args, **_kwargs):
        called.append(True)
        return {"helper": "review", "result": "PASS", "lines": [], "board": ""}

    monkeypatch.setattr("forge.helpers.run_review_helper", fake_review)
    boards = run_helpers(
        ["review"],
        {"text": "--- a/foo.py\n+++ b/foo.py\n@@\n+x\n", "changes": [{"path": "foo.py"}]},
        "hello",
        on_phase=lambda payload: phases.append(payload),
    )
    assert called
    assert phases and phases[0]["phase"] == "review"
    assert boards[0]["helper"] == "review"


def test_pipeline_plan_then_edit_then_review(monkeypatch):
    order = []

    def fake_plan(*_args, on_delta=None, on_begin=None, **_kwargs):
        order.append("plan")
        if on_begin:
            on_begin({"phase": "plan"})
        if on_delta:
            on_delta("step")
        return {
            "helper": "plan",
            "result": "PASS",
            "text": "step one",
            "lines": [],
            "board": "",
        }

    def fake_review(*_args, **_kwargs):
        order.append("review")
        return {"helper": "review", "result": "PASS", "lines": [], "board": ""}

    monkeypatch.setattr("forge.helpers.probe_flash_tag", lambda: "qwen3.8-flash-next")
    monkeypatch.setattr("forge.helpers.run_plan_helper", fake_plan)
    monkeypatch.setattr("forge.helpers.run_review_helper", fake_review)

    edit_prompt, pre_boards, used = run_edit_helpers(
        ["plan", "review"],
        "crop code",
        None,
        on_plan_delta=lambda _d: None,
        on_plan_begin=lambda _m: None,
    )
    assert order == ["plan"]
    assert used is True
    assert "PLAN (5090 flash" in edit_prompt

    order.append("edit")
    edit_result = {
        "text": "--- a/crop.py\n+++ b/crop.py\n@@\n+x=1\n",
        "changes": [{"path": "crop.py"}],
    }
    streamed = []

    attach_post_edit_helpers(
        ["plan", "review"],
        edit_result,
        "crop code",
        None,
        pre_boards,
        plan_used_flash=True,
        on_phase=lambda payload: streamed.append(payload.get("phase")),
        on_helper=lambda board: streamed.append(board.get("helper")),
    )
    assert order == ["plan", "edit", "review"]
    assert streamed == ["review", "review"]


def test_run_helpers_skips_check_when_plan_used_flash(monkeypatch):
    called = []
    monkeypatch.setattr(
        "forge.helpers.run_check_helper",
        lambda *_args, **_kwargs: called.append(True) or {"helper": "check", "result": "PASS", "lines": [], "board": ""},
    )
    boards = run_helpers(
        ["check"],
        {"text": "--- a/foo.py\n+++ b/foo.py\n@@\n+x\n", "changes": [{"path": "foo.py"}]},
        "hello",
        skip_flash_check=True,
    )
    assert not called
    assert boards[0]["helper"] == "check"
    assert "plan already used 5090" in boards[0]["lines"][0]["detail"]


def test_run_plan_helper_streams_callbacks(monkeypatch):
    monkeypatch.setattr("forge.helpers.probe_flash_tag", lambda: "qwen3.8-flash-next")
    deltas: list[str] = []
    began: list[dict] = []

    def fake_chat(*_args, on_delta=None, **_kwargs):
        if on_delta:
            on_delta("step ")
            on_delta("one")
        return {"text": "step one", "model": "qwen3.8-flash-next", "via": "evo-ssh"}

    monkeypatch.setattr("forge.helpers.flash_chat", fake_chat)
    board = run_plan_helper(
        "build a widget",
        on_delta=lambda d: deltas.append(d),
        on_begin=lambda meta: began.append(meta),
    )
    assert board["result"] == "PASS"
    assert "".join(deltas) == "step one"
    assert began and began[0]["phase"] == "plan"


CLEAN_DIFF = "--- a/foo.py\n+++ b/foo.py\n@@\n+x = 1\n"


def test_run_assure_helper_warns_on_empty_diff():
    board = run_assure_helper("", "hello")
    assert board["result"] == "WARN"
    assert board["helper"] == "assure"
    assert "No pending diff" in board["lines"][0]["detail"]


def test_run_assure_helper_passes_clean_diff():
    board = run_assure_helper(CLEAN_DIFF, "add x")
    assert board["result"] == "PASS"
    assert board["model"] == "local"
    text = (board.get("board") or "") + " ".join(L["detail"] for L in board["lines"])
    lowered = text.lower()
    assert "payload" not in lowered
    assert "poc" not in lowered
    assert "how to attack" not in lowered
    assert "proof of concept" not in lowered


def test_run_assure_helper_fails_secret_and_redacts():
    diff = "--- a/cfg.py\n+++ b/cfg.py\n@@\n+api_key = \"sk-live-farm-secret-99\"\n"
    board = run_assure_helper(diff, "add key")
    assert board["result"] == "FAIL"
    detail = " ".join(L["detail"] for L in board["lines"])
    assert "sk-live-farm-secret-99" not in detail
    assert "***" in detail
    assert "secrets" in {L["label"] for L in board["lines"]}


def test_run_assure_helper_warns_on_shell_true():
    diff = "--- a/run.py\n+++ b/run.py\n@@\n+subprocess.run(cmd, shell=True)\n"
    board = run_assure_helper(diff, "run cmd")
    assert board["result"] == "WARN"
    assert any(L["label"] == "injection" for L in board["lines"])


def test_run_assure_helper_fails_private_key_without_material():
    blob = "-----BEGIN PRIVATE KEY-----\\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC"
    diff = f"--- a/key.pem\n+++ b/key.pem\n@@\n+{blob}\n"
    board = run_assure_helper(diff, "add key")
    assert board["result"] == "FAIL"
    text = (board.get("board") or "") + " ".join(L["detail"] for L in board["lines"])
    assert "MIIEvQIBADAN" not in text
    assert "private key" in text.lower()


def test_scan_pending_diff_ignores_removed_secret_lines():
    diff = "--- a/cfg.py\n+++ b/cfg.py\n@@\n-api_key = \"sk-live-old-secret-99\"\n+x = 1\n"
    assert scan_pending_diff(diff) == []


def test_run_helpers_skips_assure_without_pending_diff(monkeypatch):
    called = []
    monkeypatch.setattr(
        "forge.helpers.run_assure_helper",
        lambda *args, **kwargs: called.append(True) or {"helper": "assure", "result": "PASS", "lines": [], "board": ""},
    )
    boards = run_helpers(["assure"], {"text": "prose only", "changes": []}, "hello")
    assert not called
    assert boards[0]["helper"] == "assure"
    assert "Skipped" in boards[0]["lines"][0]["detail"]


def test_run_helpers_runs_assure_after_review(monkeypatch):
    order = []

    def fake_review(*_args, **_kwargs):
        order.append("review")
        return {"helper": "review", "result": "PASS", "lines": [], "board": ""}

    def fake_assure(*_args, **_kwargs):
        order.append("assure")
        return {"helper": "assure", "result": "PASS", "lines": [], "board": ""}

    monkeypatch.setattr("forge.helpers.run_review_helper", fake_review)
    monkeypatch.setattr("forge.helpers.run_assure_helper", fake_assure)
    phases = []
    boards = run_helpers(
        ["check", "assure", "review"],
        {"text": CLEAN_DIFF, "changes": [{"path": "foo.py"}]},
        "hello",
        skip_flash_check=True,
        on_phase=lambda payload: phases.append(payload.get("phase")),
    )
    assert order == ["review", "assure"]
    assert [b["helper"] for b in boards] == ["review", "assure", "check"]
    assert phases == ["review", "assure"]
