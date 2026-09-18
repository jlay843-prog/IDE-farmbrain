"""Jeff-only local terminal pane. Loopback desk only — never a model tool."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

MAX_CHARS = 220_000

_lock = threading.Lock()
_proc: subprocess.Popen[str] | None = None
_cwd = ""
_buf = ""
_reader: threading.Thread | None = None


def _append(chunk: str) -> None:
    global _buf
    if not chunk:
        return
    _buf += chunk
    if len(_buf) > MAX_CHARS:
        _buf = _buf[-MAX_CHARS:]


def _pump(proc: subprocess.Popen[str]) -> None:
    stream = proc.stdout
    if stream is None:
        return
    try:
        while True:
            chunk = stream.read(256)
            if not chunk:
                break
            with _lock:
                if _proc is proc:
                    _append(chunk)
    except OSError:
        return
    with _lock:
        if _proc is proc:
            _append("\n[process exited]\n")


def snapshot() -> dict[str, Any]:
    with _lock:
        running = _proc is not None and _proc.poll() is None
        return {
            "ok": True,
            "running": running,
            "cwd": _cwd,
            "text": _buf,
            "pid": None if not running or _proc is None else _proc.pid,
            "model_tool": False,
        }


def stop() -> dict[str, Any]:
    global _proc, _reader
    with _lock:
        proc = _proc
        _proc = None
    if proc and proc.poll() is None:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/pid", str(proc.pid), "/t", "/f"],
                    capture_output=True,
                    windowsHide=True,
                    timeout=8,
                )
            else:
                proc.terminate()
                proc.wait(timeout=4)
        except (OSError, subprocess.TimeoutExpired):
            try:
                proc.kill()
            except OSError:
                pass
    _reader = None
    return snapshot()


def start(cwd: Path | None) -> dict[str, Any]:
    global _proc, _cwd, _buf, _reader
    stop()
    root = Path(cwd) if cwd else Path.home()
    if not root.exists():
        raise ValueError(f"terminal cwd does not exist: {root}")
    env = os.environ.copy()
    env["TERM"] = env.get("TERM") or "dumb"
    kwargs: dict[str, Any] = {
        "cwd": str(root),
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "bufsize": 0,
        "env": env,
    }
    if os.name == "nt":
        comspec = env.get("COMSPEC") or "cmd.exe"
        args = [comspec, "/Q", "/D", "/K", "prompt $P$G"]
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs["startupinfo"] = startup
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        args = [env.get("SHELL") or "/bin/sh"]
    proc = subprocess.Popen(args, **kwargs)
    thread = threading.Thread(target=_pump, args=(proc,), daemon=True)
    with _lock:
        _proc = proc
        _cwd = str(root)
        _buf = f"Forge local terminal — {root}\nJeff-only pane. The model cannot see or run this shell.\n"
        _reader = thread
    thread.start()
    time.sleep(0.15)
    return snapshot()


def write(text: str) -> dict[str, Any]:
    payload = text if text.endswith("\n") else text + "\n"
    with _lock:
        proc = _proc
        running = proc is not None and proc.poll() is None
        if running and proc is not None and proc.stdin:
            try:
                _append(payload)
                proc.stdin.write(payload)
                proc.stdin.flush()
            except OSError as exc:
                raise ValueError(f"terminal write failed: {exc}") from exc
    if not running:
        raise ValueError("terminal is not running")
    return snapshot()
