"""Legion-only Telegram /forge alias. Shells forge.cmd. Not part of Farm Brain."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from forge.python_find import find_python

FORGE_ROOT = Path(__file__).resolve().parents[2]
FORGE_CMD = FORGE_ROOT / "forge.cmd"
ALLOWED_HEAD = ("status", "which", "models", "use", "ask", "git")
BLOCKED_HEAD = ("edit", "apply", "serve", "telegram", "open", "compare", "recipe", "launch")
TOKEN_FILES = (
    Path(os.environ.get("FORGE_TELEGRAM_TOKEN_FILE", "")),
    Path(r"C:\Users\jlay\secrets\forge_telegram_token.txt"),
)
ALLOW_FILES = (
    Path(os.environ.get("FORGE_TELEGRAM_ALLOW_FILE", "")),
    Path(r"C:\Users\jlay\secrets\forge_telegram_allow.txt"),
)
MAX_OUT = 3500
ASK_TIMEOUT = 120
DEFAULT_TIMEOUT = 45


def on_legion(hostname: str | None = None) -> bool:
    if (os.environ.get("FORGE_TELEGRAM_ALLOW_HOST") or "").strip() == "1":
        return True
    name = (hostname or os.environ.get("COMPUTERNAME") or socket.gethostname() or "").strip().lower()
    return "legion" in name


def token() -> str:
    env = (os.environ.get("FORGE_TELEGRAM_TOKEN") or "").strip()
    if env:
        return env
    for path in TOKEN_FILES:
        if path and path.is_file():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return text
    return ""


def allowed_user_ids() -> set[int]:
    ids: set[int] = set()
    raw = (os.environ.get("FORGE_TELEGRAM_ALLOW") or "").strip()
    chunks = [raw] if raw else []
    for path in ALLOW_FILES:
        if path and path.is_file():
            chunks.append(path.read_text(encoding="utf-8"))
    for chunk in chunks:
        for part in chunk.replace(";", ",").replace("\n", ",").split(","):
            part = part.strip()
            if part.isdigit() or (part.startswith("-") and part[1:].isdigit()):
                ids.add(int(part))
    return ids


def help_text() -> str:
    return (
        "Forge on Legion (not Farm Brain /coder).\n"
        "/forge status\n"
        "/forge which\n"
        "/forge models\n"
        "/forge use code|chat\n"
        "/forge ask <prompt>\n"
        "/forge git\n"
        "Burst/5090 stays blocked while Vast is live. No edit/apply from Telegram."
    )


def parse_forge(text: str) -> list[str] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    lower = raw.lower()
    if lower.startswith("/forge@"):
        parts = raw.split(None, 1)
        raw = "/forge" if len(parts) == 1 else "/forge " + parts[1]
        lower = raw.lower()
    if lower != "/forge" and not lower.startswith("/forge "):
        return None
    rest = raw[6:].strip()
    if not rest or rest.lower() in {"help", "-h", "--help"}:
        return []
    return rest.split()


def _argv_allowed(argv: list[str]) -> str | None:
    if not argv:
        return None
    head = argv[0].lower()
    if head in BLOCKED_HEAD:
        return f"/{head} is not available via Telegram. Use the Legion desk."
    if head not in ALLOWED_HEAD:
        return "Unknown /forge command. Try /forge help."
    if head == "use" and len(argv) > 1 and argv[1].lower() == "burst":
        return "burst/5090 stays blocked from Telegram while Vast can be live. Use code or chat."
    if head == "git" and len(argv) > 1 and argv[1].lower() not in {"status", ""}:
        return "Telegram /forge git is status only (no commit, no push)."
    if head == "ask" and len(argv) < 2:
        return "Usage: /forge ask <prompt>"
    return None


def shell_forge(argv: list[str]) -> dict[str, Any]:
    timeout = ASK_TIMEOUT if argv and argv[0].lower() == "ask" else DEFAULT_TIMEOUT
    if FORGE_CMD.is_file() and os.name == "nt":
        cmd = [str(FORGE_CMD), *argv]
        exe_cwd = str(FORGE_ROOT)
    else:
        found = find_python(FORGE_ROOT)
        if not found["ok"]:
            return {"ok": False, "text": found.get("error") or "python missing", "argv": argv}
        cmd = [found["exe"], *found["args"], "-m", "forge", *argv]
        exe_cwd = str(FORGE_ROOT)
    env = os.environ.copy()
    src = str(FORGE_ROOT / "src")
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    try:
        proc = subprocess.run(
            cmd,
            cwd=exe_cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "text": f"timed out after {timeout}s", "argv": argv}
    except OSError as exc:
        return {"ok": False, "text": str(exc), "argv": argv}
    out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
    out = out.strip() or f"(exit {proc.returncode})"
    if len(out) > MAX_OUT:
        out = out[: MAX_OUT - 20] + "\n…(truncated)"
    return {"ok": proc.returncode == 0, "text": out, "argv": argv, "code": proc.returncode}


def handle_text(text: str) -> str | None:
    argv = parse_forge(text)
    if argv is None:
        return None
    if not argv:
        return help_text()
    blocked = _argv_allowed(argv)
    if blocked:
        return blocked
    result = shell_forge(argv)
    return result["text"]


def _api(token_value: str, method: str, payload: dict[str, Any] | None = None, *, timeout: float = 40.0) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{token_value}/{method}"
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read() if exc.fp else b""
        try:
            parsed = json.loads(raw.decode("utf-8")) if raw else {"ok": False, "error": str(exc)}
        except json.JSONDecodeError:
            parsed = {"ok": False, "error": raw.decode("utf-8", errors="replace") or str(exc)}
        return parsed if isinstance(parsed, dict) else {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def send_message(token_value: str, chat_id: int, text: str) -> dict[str, Any]:
    return _api(token_value, "sendMessage", {"chat_id": chat_id, "text": text[:4090]})


def handle_update(update: dict[str, Any], *, allow: set[int]) -> dict[str, Any] | None:
    message = update.get("message") or update.get("edited_message") or {}
    if not isinstance(message, dict):
        return None
    text = str(message.get("text") or "")
    chat = message.get("chat") or {}
    user = message.get("from") or {}
    chat_id = chat.get("id")
    user_id = user.get("id")
    if chat_id is None:
        return None
    parsed = parse_forge(text)
    if parsed is None:
        return None
    if allow and user_id not in allow and int(chat_id) not in allow:
        return {"chat_id": int(chat_id), "text": "Forge Telegram is allowlisted. Add your user id to forge_telegram_allow.txt."}
    reply = handle_text(text)
    if not reply:
        return None
    return {"chat_id": int(chat_id), "text": reply}


def probe() -> dict[str, Any]:
    host = os.environ.get("COMPUTERNAME") or socket.gethostname()
    return {
        "ok": True,
        "legion": on_legion(),
        "host": host,
        "token": bool(token()),
        "allow": sorted(allowed_user_ids()),
        "cmd": str(FORGE_CMD),
        "farm_brain": False,
    }


def run_poll_loop() -> int:
    info = probe()
    if not info["legion"]:
        return 2
    tok = token()
    if not tok:
        return 2
    allow = allowed_user_ids()
    offset = 0
    while True:
        body = _api(
            tok,
            "getUpdates",
            {"timeout": 25, "offset": offset, "allowed_updates": ["message", "edited_message"]},
            timeout=40.0,
        )
        if not body.get("ok"):
            time.sleep(3)
            continue
        for update in body.get("result") or []:
            offset = max(offset, int(update.get("update_id") or 0) + 1)
            reply = handle_update(update, allow=allow)
            if reply:
                send_message(tok, reply["chat_id"], reply["text"])
        time.sleep(0.2)
