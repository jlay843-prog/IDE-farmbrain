from pathlib import Path

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
    load_gate_text,
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
    assert "GATE.md" in assure["label"]
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


def test_run_assure_helper_fails_dynamic_eval():
    diff = "--- a/run.py\n+++ b/run.py\n@@\n+value = eval(user_input)\n"
    board = run_assure_helper(diff, "eval input")
    assert board["result"] == "FAIL"
    assert any(L["label"] == "eval" and "dynamic eval" in L["detail"] for L in board["lines"])


def test_run_assure_helper_fails_private_key_without_material():
    blob = "-----BEGIN PRIVATE KEY-----\\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC"
    diff = f"--- a/key.pem\n+++ b/key.pem\n@@\n+{blob}\n"
    board = run_assure_helper(diff, "add key")
    assert board["result"] == "FAIL"
    text = (board.get("board") or "") + " ".join(L["detail"] for L in board["lines"])
    assert "MIIEvQIBADAN" not in text
    assert "private key" in text.lower()


def test_scan_pending_diff_flags_stub_verifier_and_repeats():
    stub = (
        "--- a/auth.ts\n+++ b/auth.ts\n@@\n"
        "+  // For now, assume verification succeeds if the header is present\n"
        "+  return true;\n"
    )
    lines = scan_pending_diff(stub)
    assert any(row["label"] == "stub" or row["label"] == "proof" for row in lines)
    repeated = "+  if (process.env.REQUIRE_ACCESS === \"true\" && fromTrustedEdge(req)) {\n"
    diff = "--- a/mw.ts\n+++ b/mw.ts\n@@\n" + repeated * 2
    again = scan_pending_diff(diff)
    assert any(row["label"] == "repeat" for row in again)


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


def test_assure_ssot_is_gate_md():
    gate = load_gate_text()
    assert "every Edit, in every workspace" in gate
    assert "It is not a checklist of Lone Tree Acres apps" in gate
    assert "stub verifier" in gate
    assert "header is proof" in gate
    src = Path(__file__).resolve().parents[1] / "src" / "forge" / "helpers.py"
    text = src.read_text(encoding="utf-8")
    assert "GATE.md" in text
    assert "Empero must stay on AMD" not in text
    assert "HTML farm apps" not in text
    assert "port-forward Ollama" not in text
    assert "farm-brain apply still needs" not in text


def test_assure_ignores_farm_check_handoff_copy():
    diff = (
        "--- a/notes.md\n+++ b/notes.md\n@@\n"
        "+Empero must never load on the 5070 Ti. ARIA UI uses Accept */*.\n"
        "+forge check llm reports Empero on CUDA as FAIL.\n"
    )
    assert scan_pending_diff(diff) == []


def test_assure_fails_public_bind_and_health_block():
    bind = "--- a/app.py\n+++ b/app.py\n@@\n+app.run(host=\"0.0.0.0\", port=8080)\n"
    board = run_assure_helper(bind, "listen")
    assert board["result"] == "FAIL"
    assert any(L["label"] == "bind" for L in board["lines"])
    health = "--- a/mw.py\n+++ b/mw.py\n@@\n+deny 127.0.0.1 and /health\n"
    board2 = run_assure_helper(health, "lock loopback")
    assert any(L["label"] == "health" for L in board2["lines"])


def test_assure_board_uses_gate_copy():
    board = run_assure_helper(CLEAN_DIFF, "add x")
    assert board["result"] == "PASS"
    assert "GATE.md" in board["note"]
    assert "stub verifier" in board["lines"][0]["detail"]
    assert "invented status" not in (board.get("board") or "").lower()
