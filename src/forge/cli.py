"""forge status|models|use|open|which|ask|edit|serve|projects|recipe|launch"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from forge import __version__
from forge.edit import apply_diff
from forge.hosts import TIERS, backend_for_tier
from forge.io import configure_stdio, out
from forge.launch import launch
from forge.log import log_turn
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
    return 0 if snap["farm"]["ok"] or any(b["ok"] for b in snap["backends"].values()) else 1


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
    if tier == "burst":
        resolved = resolve_session("burst")
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
        out("not a TTY — pick with: forge use code --model qwen3-coder:30b")
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


def cmd_ask(args: argparse.Namespace) -> int:
    try:
        result = run_ask(args.prompt, args.file, tier=args.tier, model=args.model)
    except (SessionError, FileNotFoundError, ValueError) as exc:
        out(str(exc), err=True)
        return 1
    log_turn("ask", result, args.prompt)
    if args.json:
        return _print_json(result)
    out(f"# {result['model']}  {result['backend']}  {result['gpu']}")
    out(result["text"])
    return 0


def cmd_edit(args: argparse.Namespace) -> int:
    try:
        result = run_edit(
            args.prompt,
            args.file,
            apply=False,
            tier=args.tier,
            model=args.model,
        )
    except (SessionError, FileNotFoundError, ValueError) as exc:
        out(str(exc), err=True)
        return 1
    log_turn("edit", result, args.prompt)
    out(f"# {result['model']}  {result['backend']}  {result['gpu']}")
    out(result["text"])
    if result.get("protected"):
        out("")
        out(PROTECTED_HINT)
    if not args.apply and not args.yes:
        if not sys.stdin.isatty():
            out("")
            out("(diff not applied - pass --apply to write)")
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
        changed = apply_diff(root, result["text"])
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
    result = launch(args.target, args.note or "")
    if args.json:
        return _print_json(result)
    if not result.get("ok"):
        out(result.get("error", "launch failed"), err=True)
        return 1
    out(str(result.get("url") or result.get("path") or "ok"))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from forge.serve import serve

    serve(args.host, args.port)
    return 0


def cmd_mesh(args: argparse.Namespace) -> int:
    return _print_json(mesh_snapshot())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forge", description="Local Qwen coding desk")
    parser.add_argument("--version", action="version", version=f"forge {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("status", help="probe EVO CUDA/AMD, tower, Farm Brain")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

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
    p.add_argument("--i-understand-qc", dest="i_understand_qc", action="store_true")
    p.set_defaults(func=cmd_edit)

    p = sub.add_parser("compare", help="run ask/edit on up to 3 live models; AMD 30B judges")
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
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_launch)

    p = sub.add_parser("serve", help="desk HTTP API on loopback")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=43180)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("mesh", help="JSON compute graph")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_mesh)

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
