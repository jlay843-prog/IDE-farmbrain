"""Loopback HTTP API + static desk UI. Electron wraps this."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from forge import __version__
from forge.context import list_tree, resolve_under
from forge.edit import apply_diff
from forge.hosts import LINKS
from forge.launch import launch, link_catalog
from forge.probe import mesh_snapshot, models_snapshot, resolve_session, status_snapshot
from forge.recipes import RECIPES, get_recipe
from forge.compare import run_compare
from forge.session import SessionError, run_ask, run_edit
from forge.state import (
    assign_project,
    is_protected_workspace,
    load_state,
    set_tier,
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
}


def _json_bytes(data, status: int = 200) -> tuple[int, bytes, str]:
    return status, json.dumps(data, default=str).encode("utf-8"), "application/json; charset=utf-8"


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


def _dispatch(method: str, path: str, query: dict, body: dict) -> tuple[int, bytes, str]:
    if path == "/api/health":
        return _json_bytes({"ok": True, "name": "forge", "version": __version__})
    if path == "/api/desk":
        root = workspace_path()
        return _json_bytes(
            {
                "ok": True,
                "state": load_state(),
                "files": list_tree(root, "") if root else [],
                "recipes": RECIPES,
                "links": link_catalog(),
                "workspace": str(root) if root else "",
            }
        )
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
        if tier == "burst":
            resolved = resolve_session("burst", body.get("model"))
            if resolved.get("blocked"):
                raise SessionError("burst is blocked while Vast is active on the 5090")
        return _json_bytes(set_tier(tier, body.get("model")))
    if path == "/api/open" and method == "POST":
        return _json_bytes(set_workspace(body["path"]))
    if path == "/api/ask" and method == "POST":
        return _json_bytes(
            run_ask(body["prompt"], body.get("files") or [], tier=body.get("tier"), model=body.get("model"))
        )
    if path == "/api/edit" and method == "POST":
        return _json_bytes(
            run_edit(
                body["prompt"],
                body.get("files") or [],
                apply=False,
                tier=body.get("tier"),
                model=body.get("model"),
            )
        )
    if path == "/api/apply" and method == "POST":
        root = workspace_path()
        if root is None:
            raise ValueError("no workspace")
        if is_protected_workspace(root) and not body.get("confirm_protected"):
            raise SessionError("farm-brain apply requires confirm_protected")
        changed = apply_diff(root, body["diff"])
        return _json_bytes({"ok": True, "changed": changed})
    if path == "/api/projects" and method == "GET":
        return _json_bytes(load_state())
    if path == "/api/projects" and method == "POST":
        return _json_bytes(
            assign_project(body["path"], tier=body.get("tier") or "code", model=body.get("model") or "qwen3-coder:30b")
        )
    if path == "/api/files":
        root = workspace_path()
        if root is None:
            return _json_bytes({"ok": True, "workspace": "", "entries": []})
        rel = (query.get("path") or [""])[0]
        return _json_bytes({"ok": True, "workspace": str(root), "entries": list_tree(root, rel)})
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
    if path == "/api/launch" and method == "POST":
        return _json_bytes(launch(body["target"], body.get("note") or ""))
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
            return _json_bytes(run_ask(prompt, files))
        return _json_bytes(run_edit(prompt, files, apply=False))
    if path == "/api/compare" and method == "POST":
        return _json_bytes(
            run_compare(
                body.get("kind") or "ask",
                body.get("prompt") or "",
                body.get("files") or [],
                body.get("models"),
            )
        )
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
