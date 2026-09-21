"""Tiny Plan → Code handoff smoke. Never auto-applies. Not Farm-Ontology."""

from __future__ import annotations

import json
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from forge.flash import FLASH_MODEL, probe_flash_tag  # noqa: E402
from forge.helpers import (  # noqa: E402
    attach_post_edit_helpers,
    augment_prompt_with_plan,
    has_pending_diff,
    named_files_for_plan,
    parse_plan_files,
    run_edit_helpers,
    run_helpers,
)
from forge.session import run_edit  # noqa: E402
from forge.state import set_workspace  # noqa: E402

PROMPT = (
    "In notes.txt, change the first line from hello farm to hello forge. "
    "One file only. Do not touch any other path."
)


def _attempt(log: list[dict], name: str, ok: bool, detail: str, extra: dict | None = None) -> None:
    row = {"attempt": name, "ok": ok, "detail": detail}
    if extra:
        row.update(extra)
    log.append(row)
    mark = "PASS" if ok else "FAIL"
    print(f"{mark} {name}: {detail}")


def main() -> int:
    log: list[dict] = []
    tmp = Path(tempfile.mkdtemp(prefix="forge-plan-code-"))
    notes = tmp / "notes.txt"
    notes.write_text("hello farm\n", encoding="utf-8")
    set_workspace(tmp)

    tag = probe_flash_tag()
    _attempt(
        log,
        "flash_tag",
        tag == FLASH_MODEL,
        f"probe={tag!r} expected={FLASH_MODEL!r}",
        {"class": "model tag"},
    )
    if tag != FLASH_MODEL:
        print(json.dumps({"ok": False, "workspace": str(tmp), "log": log}, indent=2))
        return 1

    plan_prompt, boards, used = run_edit_helpers(["plan"], PROMPT, ["notes.txt"])
    plan = boards[0] if boards else {}
    plan_text = str(plan.get("text") or "")
    paths = parse_plan_files(plan_text)
    json_ok = bool(paths) and "notes.txt" in paths
    _attempt(
        log,
        "plan_json",
        plan.get("result") == "PASS" and used and json_ok,
        f"result={plan.get('result')} used={used} via={plan.get('backend')} "
        f"model={plan.get('model')} files={paths} text={plan_text[:240]!r}",
        {"class": "plan json / SSH"},
    )
    if not (plan.get("result") == "PASS" and used):
        print(json.dumps({"ok": False, "workspace": str(tmp), "log": log, "plan": plan_text[:2000]}, indent=2))
        return 1

    named = named_files_for_plan(["notes.txt"], plan, workspace=tmp)
    edit_prompt = augment_prompt_with_plan(PROMPT, plan)
    result = run_edit(
        edit_prompt,
        named,
        apply=False,
        require_diff=True,
        workspace=tmp,
    )
    pending = has_pending_diff(result)
    applied = bool(result.get("applied"))
    _attempt(
        log,
        "coder_diff",
        pending and not applied,
        f"model={result.get('model')} backend={result.get('backend')} "
        f"tool_rounds={result.get('tool_rounds')} diff_retry={result.get('diff_retry')} "
        f"changes={result.get('changes')} applied={applied} "
        f"text={str(result.get('text') or '')[:400]!r}",
        {"class": "empty inspect / no pending diff"},
    )

    skip_boards = run_helpers(
        ["review", "check"],
        {"text": "prose only", "changes": []},
        PROMPT,
        skip_flash_check=True,
    )
    skip_ok = all(b.get("result") == "WARN" and "Skipped" in str(b.get("lines")) for b in skip_boards)
    _attempt(
        log,
        "helpers_skip_without_diff",
        skip_ok,
        f"boards={[ (b.get('helper'), b.get('result'), b.get('lines')) for b in skip_boards ]}",
        {"class": "check skip"},
    )

    post = attach_post_edit_helpers(
        ["plan", "review", "check"],
        result,
        PROMPT,
        named,
        [plan],
        plan_used_flash=True,
    )
    helpers = post.get("helpers") or []
    check = next((b for b in helpers if b.get("helper") == "check"), None)
    review = next((b for b in helpers if b.get("helper") == "review"), None)
    check_note = ""
    if check:
        check_note = str((check.get("lines") or [{}])[0].get("detail") or check.get("note") or "")
    if pending:
        check_ok = check is not None and (
            "plan already used 5090" in check_note or check.get("result") in {"PASS", "WARN", "FAIL"}
        )
        review_ok = review is not None and review.get("result") in {"PASS", "WARN", "FAIL"}
        _attempt(
            log,
            "helpers_after_diff",
            check_ok and review_ok,
            f"review={review.get('result') if review else None} "
            f"check={check.get('result') if check else None} check_note={check_note!r}",
            {"class": "check skip / review after diff"},
        )
    else:
        _attempt(
            log,
            "helpers_after_diff",
            False,
            "no pending diff so review/check must stay skipped — coder handoff failed",
            {"class": "no pending diff"},
        )

    still = notes.read_text(encoding="utf-8")
    _attempt(
        log,
        "no_auto_apply",
        still == "hello farm\n",
        f"notes.txt after smoke={still!r}",
        {"class": "auto-apply"},
    )

    ok = all(row["ok"] for row in log)
    payload = {
        "ok": ok,
        "workspace": str(tmp),
        "plan_text": plan_text[:2000],
        "diff": str(result.get("text") or "")[:4000],
        "log": log,
    }
    print(json.dumps(payload, indent=2, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        print(json.dumps({"ok": False, "error": str(exc), "class": "uncaught"}, indent=2))
        raise SystemExit(1)
