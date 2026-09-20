"""forge status|check|models|use|open|which|ask|edit|git|health|log|serve|projects|recipe|launch|vault|telegram"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from forge import __version__
from forge.edit import apply_diff, format_change_list, format_hunk_list
from forge.hosts import TIERS, backend_for_tier
from forge.io import configure_stdio, out, write_chunk
from forge.launch import launch
from forge.vault import search_vault, vault_info
from forge.checks import format_board, run_check
from forge.health import health_snapshot
from forge.log import log_path, log_turn, read_turns
from forge.probe import (
    farm_hosts_from_dials,
    mesh_snapshot,
    models_snapshot,
    picker_snapshot,
    resolve_session,
    status_snapshot,
)
from forge.recipes import RECIPES, get_recipe
from forge.compare import run_compare
from forge.helpers import run_helpers
from forge.git import commit as git_commit
from forge.git import diff_for as git_diff
from forge.git import snapshot as git_snapshot
from forge.session import SessionError, run_ask, run_edit
from forge.state import (
    PROTECTED_HINT,
    assign_project,
    is_protected_workspace,
    load_state,
    set_tier,
    set_workspace,
    workspace_path,
)


def _print_json(data) -> int:
    out(json.dumps(data, indent=2, default=str))
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    snap = health_snapshot()
    if args.json:
        return _print_json(snap)
    py = snap.get("python") or {}
    monaco = snap.get("monaco") or {}
    out(f"forge {snap.get('version')}  python={'ok' if py.get('ok') else 'missing'}  monaco={'ok' if monaco.get('ok') else 'missing'}")
    if py.get("exe"):
        out(f"  python  {py['exe']}")
    if monaco.get("path"):
        out(f"  monaco  {monaco['path']}")
    elif not monaco.get("ok"):
        out("  monaco  run npm run vendor:monaco")
    code = 0
    if not py.get("ok"):
        code = 1
    elif not monaco.get("ok"):
        code = 2
    return code


def cmd_log(args: argparse.Namespace) -> int:
    turns = read_turns(args.limit)
    if args.json:
        return _print_json({"ok": True, "path": str(log_path()), "turns": turns})
    path = log_path()
    if not turns:
        out(f"No turns in {path}")
        return 0
    out(f"{path}  ({len(turns)} recent)")
    for row in turns:
        at = row.get("at") or "?"
        kind = row.get("kind") or "?"
        model = row.get("model") or "?"
        prompt = (row.get("prompt") or "").strip()
        if len(prompt) > 72:
            prompt = prompt[:69] + "..."
        files = row.get("files") or []
        extra = f"  files={len(files)}" if files else ""
        applied = row.get("applied")
        if applied is not None:
            extra += f"  applied={applied}"
        out(f"{at}  {kind:5}  {model}{extra}")
        if prompt:
            out(f"  {prompt}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    snap = status_snapshot()
    if args.json:
        return _print_json(snap)
    farm = "up" if snap["farm"]["ok"] else "down"
    out(f"Farm Brain  {farm}  {snap['farm']['url']}")
    out(f"Vast active {snap['vast_active']}")
    for be in snap["backends"].values():
        mark = "ok " if be["ok"] else "down"
        running = ", ".join(r["name"] for r in be.get("running") or []) or "-"
        out(f"{mark} {be['label']:12} {be['gpu']:16} {be['base']}  loaded: {running}")
    farm_nodes = farm_hosts_from_dials(snap.get("dials") or {})
    if farm_nodes:
        live = sum(1 for n in farm_nodes if n.get("ok"))
        bits = [f"{n['id']}{'' if n.get('ok') else '?'}" for n in farm_nodes]
        out(f"BC-250      {live}/{len(farm_nodes)} live  " + ", ".join(bits))
    out("tip: forge check all | farm | llm | temps | apps | vpn")
    return 0 if snap["farm"]["ok"] or any(b["ok"] for b in snap["backends"].values()) else 1


def cmd_check(args: argparse.Namespace) -> int:
    """Canned PASS/FAIL boards for local coder — no improvisation."""
    name = (args.name or "list").strip().lower()
    board = run_check(name)
    if args.json:
        return _print_json(board)
    out(format_board(board))
    return 0 if board.get("result") in ("PASS", "WARN") or board.get("check") == "list" else 1


def cmd_models(args: argparse.Namespace) -> int:
    if getattr(args, "pick", False):
        return _pick_model(None)
    snap = models_snapshot()
    if args.json:
        return _print_json(snap)
    if snap["vast_active"]:
        out("Vast is active - burst/5090 is blocked.")
    for row in snap["models"]:
        if args.quiet and not row["loaded"]:
            continue
        pulse = "*" if row["loaded"] else " "
        live = "up" if row["backend_ok"] else "dn"
        out(f"[{pulse}] {live} {row['backend']:6} {row['gpu']:16} {row['name']}")
    return 0


def cmd_use(args: argparse.Namespace) -> int:
    if args.tier is None or (getattr(args, "pick", False) and not args.model):
        return _pick_model(args.tier)
    tier = args.tier
    be = backend_for_tier(tier)
    resolved = resolve_session(tier, args.model or be.default_model)
    if resolved["blocked"]:
        out("burst blocked: Vast is active on the 5090.", err=True)
        return 2
    state = set_tier(tier, args.model or be.default_model)
    out(f"using {tier} -> {state['last_model']} on {be.label} ({be.gpu}) {be.base}")
    return 0


def _pick_model(tier_filter: str | None) -> int:
    picker = picker_snapshot()
    headings = {
        "code": "Code  EVO AMD  (Edit / coding)",
        "chat": "Ask   EVO CUDA (questions)",
        "burst": "Burst Tower 5090",
    }
    rows: list[dict] = []
    for key in ("code", "chat", "burst"):
        if tier_filter and key != tier_filter:
            continue
        group = (picker.get("groups") or {}).get(key) or []
        out(headings[key])
        if key == "burst" and picker.get("vast_active"):
            out("  blocked while Vast is live")
        if not group:
            out("  (no talk models on this host)")
            continue
        for row in group:
            rows.append(row)
            mark = "*" if row.get("loaded") else " "
            block = "  [blocked]" if row.get("blocked") else ""
            out(f"  {len(rows):2}) [{mark}] {row['name']}  {row.get('gpu') or ''}{block}")
        out("")
    if not rows:
        out("no live models from /api/tags", err=True)
        return 1
    if not sys.stdin.isatty():
        out("not a TTY — pick with: forge use code --model qwen3-coder-next:latest")
        out("                 or: forge use chat --model qwen3.8:27b")
        return 0
    raw = input("Pick a model number: ").strip()
    try:
        idx = int(raw)
    except ValueError:
        out("not a number", err=True)
        return 1
    if idx < 1 or idx > len(rows):
        out("out of range", err=True)
        return 1
    choice = rows[idx - 1]
    if choice.get("blocked"):
        out("burst blocked: Vast is active on the 5090.", err=True)
        return 2
    state = set_tier(choice["tier"], choice["name"])
    be = backend_for_tier(choice["tier"])
    out(f"using {choice['tier']} -> {state['last_model']} on {be.label} ({be.gpu}) {be.base}")
    return 0


def cmd_open(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser()
    if not path.exists():
        out(f"path not found: {path}", err=True)
        return 1
    state = set_workspace(path)
    out(f"workspace {state['workspace']}")
    if is_protected_workspace():
        out(PROTECTED_HINT)
    return 0


def cmd_which(args: argparse.Namespace) -> int:
    state = load_state()
    payload = {
        "workspace": state.get("workspace") or "",
        "tier": state.get("tier") or "code",
        "model": state.get("last_model") or "",
    }
    try:
        sess = resolve_session(payload["tier"], payload["model"] or None)
        payload.update(
            {
                "backend": sess["backend"]["id"],
                "label": sess["backend"]["label"],
                "gpu": sess["backend"]["gpu"],
                "base": sess["base"],
                "resolved_model": sess["model"],
                "reachable": bool(sess["backend"].get("ok")),
                "blocked": bool(sess.get("blocked")),
            }
        )
    except Exception as exc:  # noqa: BLE001
        payload["error"] = str(exc)
    if args.json:
        return _print_json(payload)
    out(f"workspace  {payload['workspace'] or '-'}")
    out(f"tier       {payload['tier']}")
    out(f"model      {payload.get('resolved_model') or payload['model'] or '-'}")
    if payload.get("label"):
        out(f"backend    {payload['label']}  {payload.get('gpu')}  {payload.get('base')}")
        out(f"reachable  {payload.get('reachable')}  blocked {payload.get('blocked')}")
    if payload.get("error"):
        out(str(payload["error"]), err=True)
        return 1
    return 0


def _stream_begin(json_mode: bool):
    def on_begin(meta: dict) -> None:
        if json_mode:
            return
        out(f"# {meta.get('model')}  {meta.get('backend')}  {meta.get('gpu')}")

    return on_begin


def _stream_delta(json_mode: bool):
    def on_delta(delta: str) -> None:
        if json_mode:
            return
        write_chunk(delta)

    return on_delta


def _stream_tool(json_mode: bool):
    def on_tool(ev: dict) -> None:
        if json_mode:
            return
        if ev.get("phase") == "call":
            args = ev.get("args") or {}
            detail = args.get("path") or args.get("pattern") or ""
            out(f"\n# tool {ev.get('name')} {detail}".rstrip())
            return
        out(f"# {ev.get('name')} {ev.get('preview') or ''}".rstrip())

    return on_tool


def cmd_ask(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    try:
        result = run_ask(
            args.prompt,
            args.file,
            tier=args.tier,
            model=args.model,
            on_begin=_stream_begin(json_mode),
            on_delta=_stream_delta(json_mode),
        )
    except (SessionError, FileNotFoundError, ValueError, RuntimeError) as exc:
        out(str(exc), err=True)
        return 1
    if not json_mode:
        write_chunk("\n")
    log_turn("ask", result, args.prompt)
    if json_mode:
        return _print_json(result)
    return 0


def cmd_edit(args: argparse.Namespace) -> int:
    json_mode = False
    try:
        result = run_edit(
            args.prompt,
            args.file,
            apply=False,
            tier=args.tier,
            model=args.model,
            on_begin=_stream_begin(json_mode),
            on_delta=_stream_delta(json_mode),
            on_tool=_stream_tool(json_mode),
        )
    except (SessionError, FileNotFoundError, ValueError, RuntimeError) as exc:
        out(str(exc), err=True)
        return 1
    write_chunk("\n")
    log_turn("edit", result, args.prompt)
    traces = result.get("tools") or []
    if traces:
        out("")
        out("tools: " + ", ".join(f"{t.get('name')} {t.get('detail') or ''}".strip() for t in traces))
    changes = result.get("changes") or []
    if changes:
        out("")
        out(format_change_list(changes))
    hunks = result.get("hunks") or []
    if hunks:
        out("")
        out(format_hunk_list(hunks))
    if result.get("protected"):
        out("")
        out(PROTECTED_HINT)
    helpers = [h for h in (getattr(args, "helper", None) or []) if h]
    if helpers:
        boards = run_helpers(helpers, result, args.prompt, args.file)
        result["helpers"] = boards
        for board in boards:
            out("")
            out(format_board(board))
    hunk_ids = list(args.hunk) if getattr(args, "hunk", None) else None
    if hunk_ids is None and not args.apply and not args.yes:
        if not sys.stdin.isatty():
            out("")
            out("(diff not applied - pass --apply to write, or --hunk N)")
            return 0
        answer = input("\nApply this diff? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            out("skipped")
            return 0
    root = workspace_path()
    if root is None:
        out("no workspace", err=True)
        return 1
    if is_protected_workspace(root) and not args.i_understand_qc:
        out("blocked: farm-brain apply requires --i-understand-qc", err=True)
        return 2
    try:
        changed = apply_diff(root, result["text"], hunk_ids)
    except (ValueError, OSError) as exc:
        out(f"apply failed: {exc}", err=True)
        return 1
    result["applied"] = True
    result["changed"] = changed
    log_turn("apply", result, args.prompt)
    out("applied: " + ", ".join(changed))
    return 0


def cmd_projects(args: argparse.Namespace) -> int:
    state = load_state()
    if args.assign:
        path, tier, model = args.assign
        if tier not in TIERS:
            out("tier must be code|chat|burst", err=True)
            return 1
        state = assign_project(path, tier=tier, model=model)
    if args.json:
        return _print_json(state)
    out(f"workspace {state.get('workspace') or '-'}")
    out(f"tier      {state.get('tier')}  model {state.get('last_model')}")
    for row in state.get("projects") or []:
        out(f"  {row.get('tier'):5} {row.get('model'):22} {row.get('path')}")
    return 0


def cmd_recipe(args: argparse.Namespace) -> int:
    if args.action == "list":
        for row in RECIPES:
            out(f"{row['id']:12} {row['kind']:6} {row['label']}")
        return 0
    if not args.recipe_id:
        out("usage: forge recipe run <id> [prompt]", err=True)
        return 1
    try:
        recipe = get_recipe(args.recipe_id)
    except KeyError:
        out(f"unknown recipe {args.recipe_id}", err=True)
        return 1
    if recipe["kind"] == "launch":
        out_launch = launch(recipe["target"])
        out(str(out_launch.get("url") or out_launch.get("path") or out_launch))
        return 0 if out_launch.get("ok") else 1
    if recipe["kind"] == "shell":
        # Canned farm checks — run forge check, do not ask the LLM to invent status
        cmd = str(recipe.get("command") or "")
        if cmd.startswith("forge check"):
            name = cmd.split()[-1] if cmd.strip() else "all"
            board = run_check(name)
            out(format_board(board))
            return 0 if board.get("result") in ("PASS", "WARN", "list") or board.get("check") == "list" else 1
        out(f"unsupported shell recipe: {cmd}", err=True)
        return 1
    prompt = args.prompt or recipe["prompt"]
    files = args.file or []
    ns = argparse.Namespace(
        prompt=prompt,
        file=files,
        tier=None,
        model=None,
        json=False,
        apply=False,
        yes=False,
        hunk=[],
        i_understand_qc=False,
    )
    if recipe["kind"] == "ask":
        return cmd_ask(ns)
    return cmd_edit(ns)


def cmd_compare(args: argparse.Namespace) -> int:
    models = [m for m in (args.model or []) if m]
    try:
        result = run_compare(args.kind, args.prompt, args.file, models or None)
    except (SessionError, FileNotFoundError, ValueError) as exc:
        out(str(exc), err=True)
        return 1
    log_turn("compare", result, args.prompt)
    if args.json:
        return _print_json(result)
    judge = result.get("judge") or {}
    out(f"# compare {result['kind']}  judge {judge.get('model')} on {judge.get('gpu')}")
    for row in result.get("candidates") or []:
        mark = "ok" if row.get("ok") else "fail"
        out(f"{row['index']}) [{mark}] {row.get('model')}  {row.get('backend') or '-'}  {row.get('error') or ''}")
    out(f"WINNER: {judge.get('winner')} {judge.get('pick_model')}")
    out(f"REASON: {judge.get('reason')}")
    out("")
    out(result.get("text") or "")
    if result.get("kind") == "edit":
        out("")
        out("(winner not applied — use the desk Apply button, or re-run forge edit)")
    return 0


def cmd_launch(args: argparse.Namespace) -> int:
    result = launch(args.target, args.note or "", getattr(args, "url", "") or "")
    if args.json:
        return _print_json(result)
    if not result.get("ok"):
        out(result.get("error", "launch failed"), err=True)
        return 1
    out(str(result.get("url") or result.get("path") or "ok"))
    return 0


def cmd_vault(args: argparse.Namespace) -> int:
    if args.open:
        result = launch("vault", args.open)
        if args.json:
            return _print_json(result)
        if not result.get("ok"):
            out(result.get("error", "open failed"), err=True)
            return 1
        out(str(result.get("url") or result.get("path") or args.open))
        return 0
    query = (args.query or "").strip()
    if not query:
        info = vault_info()
        if args.json:
            return _print_json(info)
        out(info.get("path") or "")
        if not info.get("exists"):
            out("vault missing", err=True)
            return 1
        return 0
    found = search_vault(query)
    if args.json:
        return _print_json(found)
    if not found.get("exists"):
        out(found.get("error") or "vault missing", err=True)
        return 1
    rows = found.get("entries") or []
    if not rows:
        out("no notes match")
        return 0
    for row in rows:
        snippet = (row.get("snippet") or "").replace("\n", " ")
        out(f"{row.get('path')}\t{snippet}")
    if found.get("truncated"):
        out("(truncated)")
    return 0


def cmd_telegram(args: argparse.Namespace) -> int:
    from forge import telegram as tg

    if args.probe or args.json:
        info = tg.probe()
        if args.json:
            return _print_json(info)
        out(f"host    {info['host']}")
        out(f"legion  {info['legion']}")
        out(f"token   {'yes' if info['token'] else 'no'}")
        out(f"allow   {', '.join(str(x) for x in info['allow']) or '(set FORGE_TELEGRAM_ALLOW)'}")
        out("Farm Brain is not used.")
        return 0 if info["legion"] else 2
    if args.text:
        reply = tg.handle_text(args.text)
        out(reply or "(not a /forge command)")
        return 0
    info = tg.probe()
    if not info["legion"]:
        out("forge telegram runs on Legion only (COMPUTERNAME contains Legion).", err=True)
        return 2
    if not tg.token():
        out("Missing FORGE_TELEGRAM_TOKEN or C:\\Users\\jlay\\secrets\\forge_telegram_token.txt", err=True)
        return 2
    return tg.run_poll_loop()


def cmd_serve(args: argparse.Namespace) -> int:
    from forge.serve import serve

    serve(args.host, args.port)
    return 0


def cmd_mesh(args: argparse.Namespace) -> int:
    return _print_json(mesh_snapshot())


def cmd_git(args: argparse.Namespace) -> int:
    root = workspace_path()
    action = args.action or "status"
    if action == "status":
        snap = git_snapshot(root)
        if args.json:
            return _print_json(snap)
        if not snap.get("repo"):
            out(snap.get("summary") or snap.get("error") or "Not a git repository.")
            return 0 if snap.get("ok") else 1
        bits = [snap.get("branch") or "HEAD"]
        if snap.get("head"):
            bits.append(str(snap["head"]))
        if snap.get("empty"):
            bits.append("no commits yet")
        remotes = snap.get("remotes") or []
        bits.append("no remotes" if not remotes else "remotes " + ", ".join(remotes))
        out("  ".join(bits))
        out(snap.get("summary") or "")
        for row in snap.get("files") or []:
            mark = (row.get("status") or "changed")[:1].upper()
            out(f"  {mark} {row.get('path')}")
        return 0 if snap.get("ok") else 1
    if action == "diff":
        data = git_diff(root, args.path or "")
        if args.json:
            return _print_json(data)
        if not data.get("ok") or not data.get("repo"):
            out(data.get("error") or data.get("summary") or "Not a git repository.", err=True)
            return 1
        out(data.get("diff") or "")
        return 0
    if action == "commit":
        try:
            paths = [p for p in [args.path, *(args.path_args or [])] if p]
            result = git_commit(root, args.message or "", paths)
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            out(str(exc), err=True)
            return 1
        if args.json:
            return _print_json(result)
        out(result.get("log") or result.get("summary") or "committed")
        return 0 if result.get("ok") else 1
    out(f"unknown git action {action}", err=True)
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forge", description="Local Qwen coding desk")
    parser.add_argument("--version", action="version", version=f"forge {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("health", help="local python + Monaco vendor (no desk server)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_health)

    p = sub.add_parser("log", help="recent ask/edit turns from sessions.jsonl")
    p.add_argument("--limit", type=int, default=20, help="max rows (default 20, cap 500)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("status", help="probe EVO CUDA/AMD, tower, Farm Brain")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser(
        "check",
        help="canned farm PASS/FAIL boards (farm|llm|temps|apps|cams|vpn|ray|all) — for local coder",
    )
    p.add_argument(
        "name",
        nargs="?",
        default="list",
        help="farm|llm|temps|apps|cams|vpn|ray|all (default: list)",
    )
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("models", help="list tags + running models by host/GPU")
    p.add_argument("--json", action="store_true")
    p.add_argument("-q", "--quiet", action="store_true", help="only show loaded models")
    p.add_argument("--pick", action="store_true", help="interactive picker from live /api/tags")
    p.set_defaults(func=cmd_models)

    p = sub.add_parser("use", help="pin session, or pick a live model")
    p.add_argument("tier", nargs="?", choices=sorted(TIERS))
    p.add_argument("--model", default=None)
    p.add_argument("--pick", action="store_true", help="interactive picker from live /api/tags")
    p.set_defaults(func=cmd_use)

    p = sub.add_parser("open", help="set workspace folder")
    p.add_argument("path")
    p.set_defaults(func=cmd_open)

    p = sub.add_parser("which", help="show pinned workspace, tier, and live backend")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_which)

    p = sub.add_parser("ask", help="ask the pinned local model")
    p.add_argument("prompt")
    p.add_argument("--file", action="append", default=[])
    p.add_argument("--tier")
    p.add_argument("--model")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("edit", help="propose a unified diff; apply after y")
    p.add_argument("prompt")
    p.add_argument("--file", action="append", default=[])
    p.add_argument("--tier")
    p.add_argument("--model")
    p.add_argument("--apply", action="store_true")
    p.add_argument("-y", "--yes", action="store_true")
    p.add_argument("--hunk", action="append", type=int, default=[], help="apply only these hunk ids (repeatable)")
    p.add_argument("--i-understand-qc", dest="i_understand_qc", action="store_true")
    p.add_argument(
        "--helper",
        action="append",
        default=[],
        choices=["review", "check"],
        help="optional sequential helper after diff (review=Empero; check=5090 flash)",
    )
    p.set_defaults(func=cmd_edit)

    p = sub.add_parser("compare", help="run ask/edit on up to 3 live models; AMD coder judges")
    p.add_argument("kind", choices=["ask", "edit"])
    p.add_argument("prompt")
    p.add_argument("--file", action="append", default=[])
    p.add_argument("--model", action="append", default=[], help="live model name (repeat, max 3)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("projects", help="list or assign project model/tier")
    p.add_argument("--json", action="store_true")
    p.add_argument("--assign", nargs=3, metavar=("PATH", "TIER", "MODEL"))
    p.set_defaults(func=cmd_projects)

    p = sub.add_parser("recipe", help="list or run a workstream recipe")
    p.add_argument("action", choices=["list", "run"])
    p.add_argument("recipe_id", nargs="?")
    p.add_argument("prompt", nargs="?")
    p.add_argument("--file", action="append", default=[])
    p.set_defaults(func=cmd_recipe)

    p = sub.add_parser("launch", help="open vault, Aether, Lumen, AI-PM, Farm Brain")
    p.add_argument("target")
    p.add_argument("--note", default="")
    p.add_argument("--url", default="", help="last-URL handoff for Aether or Lumen")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_launch)

    p = sub.add_parser("vault", help="search FarmBrainVault notes, or open one")
    p.add_argument("query", nargs="?", default="")
    p.add_argument("--open", default="", help="open a named note in Obsidian")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_vault)

    p = sub.add_parser("telegram", help="Legion-only /forge alias; shells forge.cmd (not Farm Brain)")
    p.add_argument("--probe", action="store_true", help="print host/token status and exit")
    p.add_argument("--text", default="", help="handle one /forge message locally (no Telegram network)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_telegram)

    p = sub.add_parser("serve", help="desk HTTP API on loopback")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=43180)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("mesh", help="JSON compute graph")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_mesh)

    p = sub.add_parser("git", help="local status, diff, and commit (no push)")
    p.add_argument("action", nargs="?", default="status", choices=["status", "diff", "commit"])
    p.add_argument("path", nargs="?", default="", help="path for diff")
    p.add_argument("path_args", nargs="*", help="paths for commit")
    p.add_argument("-m", "--message", default="")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_git)

    return parser


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        cmd_which(argparse.Namespace(json=False))
        out("")
        parser.print_help()
        return 0
    try:
        return int(args.func(args))
    except SessionError as exc:
        out(str(exc), err=True)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
