"""Loopback HTTP API + static desk UI. Electron wraps this."""

from __future__ import annotations

import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from forge import __version__
from forge.compare import run_compare
from forge.health import health_snapshot
from forge.term import snapshot as term_snapshot
from forge.term import start as term_start
from forge.term import stop as term_stop
from forge.term import write as term_write
from forge.context import resolve_under, search_paths, tree_listing
from forge.git import commit as git_commit
from forge.git import diff_for as git_diff
from forge.git import snapshot as git_snapshot
from forge.edit import apply_diff
from forge.handoff import snapshot as handoff_snapshot, remember as remember_handoff
from forge.hosts import LINKS
from forge.launch import launch, link_catalog, open_path
from forge.vault import search_vault, vault_info
from forge.log import log_path, log_turn, read_turns
from forge.probe import mesh_snapshot, models_snapshot, resolve_session, status_snapshot
from forge.recipes import RECIPES, get_recipe
from forge.easy import classify_easy_prompt
from forge.project import create_project, sanitize_project_name
from forge.session import SessionError, run_ask, run_edit
from forge.state import (
    PROTECTED_HINT,
    assign_project,
    default_easy_projects_parent as state_default_parent,
    is_protected_workspace,
    load_state,
    resolve_ui_mode,
    set_tier,
    set_ui_mode,
    set_workspace,
    workspace_path,
)

UI_DIR = Path(__file__).resolve().parents[2] / "ui"
MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".ttf": "font/ttf",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}
STREAM_PATHS = {"/api/ask/stream", "/api/edit/stream", "/api/easy/stream"}


def _json_bytes(data, status: int = 200) -> tuple[int, bytes, str]:
    return status, json.dumps(data, default=str).encode("utf-8"), "application/json; charset=utf-8"


def sse_bytes(data: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(data, default=str)}\n\n".encode("utf-8")


def handle_api(method: str, path: str, query: dict, body: dict) -> tuple[int, bytes, str]:
    try:
        return _dispatch(method, path, query, body)
    except SessionError as exc:
        return _json_bytes({"ok": False, "error": str(exc)}, 409)
    except KeyError as exc:
        return _json_bytes({"ok": False, "error": f"unknown {exc}"}, 404)
    except (FileNotFoundError, ValueError) as exc:
        return _json_bytes({"ok": False, "error": str(exc)}, 400)
    except Exception as exc:  # noqa: BLE001
        return _json_bytes({"ok": False, "error": str(exc)}, 500)


def _git_or_empty(root):
    try:
        return git_snapshot(root)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "repo": False, "error": str(exc), "files": [], "remotes": []}


def _dispatch(method: str, path: str, query: dict, body: dict) -> tuple[int, bytes, str]:
    if path == "/api/health":
        return _json_bytes(health_snapshot())
    if path == "/api/desk":
        root = workspace_path()
        tree = tree_listing(root, "") if root else {"cwd": "", "parent": None, "crumbs": [], "entries": []}
        protected = bool(root and is_protected_workspace(root))
        state = load_state()
        return _json_bytes(
            {
                "ok": True,
                "state": state,
                "ui_mode": resolve_ui_mode(state),
                "easy_defaults": {
                    "parent": state.get("easy_projects_parent") or str(state_default_parent()),
                },
                "files": tree["entries"],
                "tree": tree,
                "recipes": RECIPES,
                "links": link_catalog(),
                "workspace": str(root) if root else "",
                "log_path": str(log_path()),
                "git": _git_or_empty(root),
                "protected": protected,
                "protected_hint": PROTECTED_HINT if protected else "",
                "vault": vault_info(),
                "handoff": handoff_snapshot(),
                "term": term_snapshot(),
            }
        )
    if path == "/api/log":
        try:
            limit = int((query.get("limit") or ["80"])[0])
        except ValueError:
            limit = 80
        return _json_bytes({"ok": True, "path": str(log_path()), "turns": read_turns(limit)})
    if path == "/api/status":
        return _json_bytes(status_snapshot())
    if path == "/api/models":
        return _json_bytes(models_snapshot())
    if path == "/api/mesh":
        return _json_bytes(mesh_snapshot())
    if path == "/api/state" and method == "GET":
        return _json_bytes(load_state())
    if path == "/api/use" and method == "POST":
        tier = body["tier"]
        resolved = resolve_session(tier, body.get("model"))
        if resolved.get("blocked"):
            raise SessionError("burst is blocked while Vast is active on the 5090")
        return _json_bytes(set_tier(tier, body.get("model")))
    if path == "/api/open" and method == "POST":
        return _json_bytes(set_workspace(body["path"]))
    if path == "/api/reveal" and method == "POST":
        root = workspace_path()
        if root is None:
            raise ValueError("no workspace")
        rel = body.get("path") or ""
        if not rel:
            raise ValueError("path required")
        target = resolve_under(root, rel)
        return _json_bytes(open_path(target))
    if path == "/api/mode" and method == "POST":
        return _json_bytes(set_ui_mode(body.get("mode") or body.get("ui_mode") or ""))
    if path == "/api/easy/defaults" and method == "GET":
        state = load_state()
        return _json_bytes(
            {
                "ok": True,
                "parent": state.get("easy_projects_parent") or str(state_default_parent()),
                "ui_mode": resolve_ui_mode(state),
            }
        )
    if path == "/api/projects/create" and method == "POST":
        name = sanitize_project_name(body.get("name") or "")
        parent = body.get("parent") or None
        return _json_bytes({"ok": True, "state": create_project(name, parent)})
    if path == "/api/easy/classify" and method == "POST":
        prompt = body.get("prompt") or ""
        return _json_bytes({"ok": True, "intent": classify_easy_prompt(prompt), "prompt": prompt})
    if path == "/api/ask" and method == "POST":
        result = run_ask(
            body["prompt"],
            body.get("files") or [],
            tier=body.get("tier"),
            model=body.get("model"),
            history=body.get("history"),
        )
        log_turn("ask", result, body.get("prompt") or "")
        return _json_bytes(result)
    if path == "/api/edit" and method == "POST":
        result = run_edit(
            body["prompt"],
            body.get("files") or [],
            apply=False,
            tier=body.get("tier"),
            model=body.get("model"),
            history=body.get("history"),
        )
        log_turn("edit", result, body.get("prompt") or "")
        return _json_bytes(result)
    if path == "/api/apply" and method == "POST":
        root = workspace_path()
        if root is None:
            raise ValueError("no workspace")
        if is_protected_workspace(root) and not body.get("confirm_protected"):
            raise SessionError("farm-brain apply requires confirm_protected")
        hunks = body.get("hunks")
        if hunks is not None and not isinstance(hunks, list):
            raise ValueError("hunks must be a list of ids")
        ids = [int(x) for x in hunks] if hunks is not None else None
        changed = apply_diff(root, body["diff"], ids)
        result = {"ok": True, "kind": "apply", "changed": changed, "applied": True, "files": [], "hunks": ids}
        log_turn("apply", result, "")
        return _json_bytes(result)
    if path == "/api/projects" and method == "GET":
        return _json_bytes(load_state())
    if path == "/api/projects" and method == "POST":
        return _json_bytes(
            assign_project(body["path"], tier=body.get("tier") or "code", model=body.get("model") or "qwen3-coder:30b")
        )
    if path in {"/api/git", "/api/git/status"}:
        root = workspace_path()
        return _json_bytes(_git_or_empty(root))
    if path == "/api/git/diff":
        root = workspace_path()
        rel = (query.get("path") or [""])[0]
        return _json_bytes(git_diff(root, rel))
    if path == "/api/git/commit" and method == "POST":
        root = workspace_path()
        if root is None:
            raise ValueError("no workspace")
        paths = body.get("paths") or []
        if not isinstance(paths, list):
            raise ValueError("paths must be a list")
        return _json_bytes(git_commit(root, body.get("message") or "", [str(p) for p in paths]))
    if path == "/api/files/search":
        root = workspace_path()
        if root is None:
            return _json_bytes({"ok": True, "workspace": "", "query": "", "entries": [], "truncated": False})
        q = (query.get("q") or [""])[0]
        found = search_paths(root, q)
        return _json_bytes({"ok": True, "workspace": str(root), **found})
    if path == "/api/files":
        root = workspace_path()
        if root is None:
            return _json_bytes({"ok": True, "workspace": "", "cwd": "", "parent": None, "crumbs": [], "entries": []})
        rel = (query.get("path") or [""])[0]
        return _json_bytes({"ok": True, "workspace": str(root), **tree_listing(root, rel)})
    if path == "/api/file" and method == "GET":
        root = workspace_path()
        if root is None:
            raise ValueError("no workspace")
        rel = (query.get("path") or [""])[0]
        target = resolve_under(root, rel)
        if not target.is_file():
            raise FileNotFoundError(rel)
        text = target.read_text(encoding="utf-8", errors="replace")
        return _json_bytes({"ok": True, "path": rel, "text": text})
    if path == "/api/file" and method == "PUT":
        root = workspace_path()
        if root is None:
            raise ValueError("no workspace")
        target = resolve_under(root, body["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body["text"], encoding="utf-8")
        return _json_bytes({"ok": True, "path": body["path"]})
    if path == "/api/links":
        return _json_bytes({"ok": True, "links": link_catalog(), "raw": LINKS})
    if path == "/api/vault":
        return _json_bytes(vault_info())
    if path == "/api/vault/search":
        q = (query.get("q") or [""])[0]
        return _json_bytes(search_vault(q))
    if path == "/api/handoff" and method == "GET":
        return _json_bytes(handoff_snapshot())
    if path == "/api/handoff" and method == "POST":
        target = body["target"]
        if body.get("launch"):
            return _json_bytes(launch(target, body.get("note") or "", body.get("url") or ""))
        remembered = remember_handoff(target, body["url"], title=body.get("title") or "", source="forge")
        return _json_bytes({"ok": True, "handoff": remembered})
    if path == "/api/launch" and method == "POST":
        return _json_bytes(launch(body["target"], body.get("note") or "", body.get("url") or ""))
    if path == "/api/recipes" and method == "GET":
        return _json_bytes({"ok": True, "recipes": RECIPES})
    if path.startswith("/api/recipes/") and path.endswith("/run") and method == "POST":
        recipe_id = path[len("/api/recipes/") : -len("/run")]
        recipe = get_recipe(recipe_id)
        if recipe["kind"] == "launch":
            return _json_bytes(launch(recipe["target"]))
        prompt = (body.get("prompt") or recipe["prompt"]).strip()
        files = body.get("files") or []
        if recipe["kind"] == "ask":
            result = run_ask(prompt, files)
            log_turn("ask", result, prompt)
            return _json_bytes(result)
        result = run_edit(prompt, files, apply=False)
        log_turn("edit", result, prompt)
        return _json_bytes(result)
    if path == "/api/term":
        if method == "GET":
            return _json_bytes(term_snapshot())
        action = str(body.get("action") or "").strip().lower()
        if action == "start":
            return _json_bytes(term_start(workspace_path()))
        if action == "write":
            return _json_bytes(term_write(str(body.get("text") or "")))
        if action in {"stop", "kill"}:
            return _json_bytes(term_stop())
        raise ValueError("term action must be start, write, or stop")
    if path == "/api/compare" and method == "POST":
        result = run_compare(
            body.get("kind") or "ask",
            body.get("prompt") or "",
            body.get("files") or [],
            body.get("models"),
        )
        log_turn("compare", result, body.get("prompt") or "")
        return _json_bytes(result)
    return _json_bytes({"ok": False, "error": "not found"}, 404)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        sys_stderr_write = super().log_message
        sys_stderr_write(fmt, *args)

    def _send(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _write_sse(self, data: dict[str, Any]) -> None:
        self.wfile.write(sse_bytes(data))
        self.wfile.flush()

    def _stream_turn(self, path: str, body: dict) -> None:
        if path.endswith("/easy/stream"):
            kind = "easy"
        elif path.endswith("/edit/stream"):
            kind = "edit"
        else:
            kind = "ask"
        try:
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        prompt = (body.get("prompt") or "").strip()
        files = body.get("files") or []
        history = body.get("history")

        easy_intent = classify_easy_prompt(prompt) if kind == "easy" else None
        routed = easy_intent or kind

        def on_begin(meta: dict[str, Any]) -> None:
            payload = dict(meta)
            if easy_intent:
                payload["intent"] = easy_intent
                payload["easy"] = True
            self._write_sse({"meta": payload})

        def on_delta(delta: str) -> None:
            self._write_sse({"delta": delta})

        def on_tool(ev: dict) -> None:
            self._write_sse({"tool": ev})

        try:
            if not prompt:
                raise SessionError("empty prompt")
            if routed == "edit":
                result = run_edit(
                    prompt,
                    files,
                    apply=False,
                    tier=body.get("tier"),
                    model=body.get("model"),
                    history=history,
                    on_begin=on_begin,
                    on_delta=on_delta,
                    on_tool=on_tool,
                )
            else:
                result = run_ask(
                    prompt,
                    files,
                    tier=body.get("tier"),
                    model=body.get("model"),
                    history=history,
                    on_begin=on_begin,
                    on_delta=on_delta,
                )
            if easy_intent:
                result = {**result, "intent": easy_intent, "easy": True}
            log_turn(routed if kind == "easy" else kind, result, prompt)
            self._write_sse({"done": True, **result})
        except (SessionError, FileNotFoundError, ValueError, RuntimeError) as exc:
            self._write_sse({"done": True, "ok": False, "error": str(exc)})
        except OSError:
            return

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._handle("PUT")

    def _handle(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path in STREAM_PATHS and method == "POST":
            self._stream_turn(path, self._body())
            return
        if path.startswith("/api/"):
            status, payload, ctype = handle_api(method, path, query, self._body() if method in {"POST", "PUT"} else {})
            self._send(status, payload, ctype)
            return
        rel = "index.html" if path in {"", "/"} else path.lstrip("/")
        target = (UI_DIR / rel).resolve()
        try:
            target.relative_to(UI_DIR.resolve())
        except ValueError:
            self._send(403, b"forbidden", "text/plain")
            return
        if not target.is_file():
            self._send(404, b"not found", "text/plain")
            return
        data = target.read_bytes()
        self._send(200, data, MIME.get(target.suffix, "application/octet-stream"))


def serve(host: str = "127.0.0.1", port: int = 43180) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Forge desk http://{host}:{port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()
