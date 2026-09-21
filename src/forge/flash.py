"""Tower 5090 Flash-Next on llama.cpp :11435 (OpenAI-compatible).

Direct HTTP from Legion often fails (bind/firewall); probe and chat fall back to EVO SSH.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import queue
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from forge.hosts import EVO, TOWER
from forge.httputil import request_json

FLASH_MODEL = "qwen3.8-flash-next"
FLASH_BASE = f"http://{TOWER}:11435"
FLASH_MODELS_URL = f"{FLASH_BASE}/v1/models"
FLASH_CHAT_URL = f"{FLASH_BASE}/v1/chat/completions"
FLASH_CHAT_FROM_EVO = f"http://{TOWER}:11435/v1/chat/completions"
_DIRECT_TIMEOUT_S = 2.0
FIRST_TOKEN_TIMEOUT_S = 90.0
_PROBE_CACHE: tuple[float, tuple[bool, list[str], str]] | None = None
_PROBE_TTL_S = 30.0

DeltaFn = Callable[[str], None]


def _ssh_key() -> str:
    env = os.environ.get("FORGE_SSH_KEY", "").strip()
    if env:
        return env
    return str(Path.home() / ".ssh" / "id_ed25519_farm")


def _ssh_run(host: str, remote: str, *, timeout: float = 20.0) -> tuple[bool, str]:
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-i",
        _ssh_key(),
        f"jeff@{host}",
        remote,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        out = (proc.stdout or "").strip() or (proc.stderr or "").strip()
        return proc.returncode == 0, out[:12000]
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:200]


def _ssh_argv(remote: str) -> list[str]:
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-i",
        _ssh_key(),
        f"jeff@{EVO}",
        remote,
    ]


def remote_python3_cmd(script: str, *args: str) -> str:
    """Tiny remote -c: decode a short script. Payload is never in argv — stdin only."""
    blob = base64.b64encode(script.encode("utf-8")).decode("ascii")
    extra = (" " + " ".join(args)) if args else ""
    return (
        "python3 -c "
        f"\"import base64,sys; exec(base64.b64decode('{blob}').decode())\""
        f"{extra}"
    )


_FLASH_SSH_STREAM_PY = f"""
import json, sys, urllib.request
p = json.load(sys.stdin)
p["stream"] = True
timeout = int(sys.argv[1]) if len(sys.argv) > 1 else 120
req = urllib.request.Request(
    "{FLASH_CHAT_FROM_EVO}",
    data=json.dumps(p).encode(),
    headers={{"Content-Type": "application/json", "Accept": "text/event-stream"}},
    method="POST",
)
resp = urllib.request.urlopen(req, timeout=timeout)
for raw in resp:
    line = raw.decode(errors="replace").strip()
    if not line.startswith("data:"):
        continue
    payload = line[5:].strip()
    if payload == "[DONE]":
        break
    try:
        obj = json.loads(payload)
    except Exception:
        continue
    choices = obj.get("choices") or []
    if not choices:
        continue
    delta = choices[0].get("delta") or {{}}
    text = str(delta.get("content") or delta.get("reasoning_content") or "")
    if text:
        print(json.dumps({{"delta": text}}), flush=True)
"""

_FLASH_SSH_ONCE_PY = f"""
import json, sys, urllib.request
p = json.load(sys.stdin)
timeout = int(sys.argv[1]) if len(sys.argv) > 1 else 120
req = urllib.request.Request(
    "{FLASH_CHAT_FROM_EVO}",
    data=json.dumps(p).encode(),
    headers={{"Content-Type": "application/json"}},
    method="POST",
)
print(urllib.request.urlopen(req, timeout=timeout).read().decode())
"""


def _parse_model_ids(body: Any) -> list[str]:
    if not isinstance(body, dict):
        return []
    data = body.get("data") or body.get("models") or []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for row in data:
        if isinstance(row, dict):
            out.append(str(row.get("id") or row.get("name") or ""))
    return [x for x in out if x]


def probe_flash_models(*, force: bool = False) -> tuple[bool, list[str], str]:
    """Return (ok, model_ids, via) for live Flash-Next on tower :11435."""
    global _PROBE_CACHE
    now = time.monotonic()
    if not force and _PROBE_CACHE and now - _PROBE_CACHE[0] < _PROBE_TTL_S:
        return _PROBE_CACHE[1]
    code, body = request_json(FLASH_MODELS_URL, timeout=_DIRECT_TIMEOUT_S)
    ids = _parse_model_ids(body)
    if code == 200 and any(FLASH_MODEL in x for x in ids):
        result = True, ids, "direct"
        _PROBE_CACHE = (now, result)
        return result
    ok, out = _ssh_run(
        EVO,
        "curl -s --max-time 5 http://192.168.68.106:11435/v1/models "
        "| python3 -c \"import sys,json; d=json.load(sys.stdin); "
        "print(','.join((m.get('id') or m.get('name') or '') for m in "
        "(d.get('data') or d.get('models') or []) if isinstance(m,dict)))\"",
        timeout=15.0,
    )
    if ok and out and "Permission denied" not in out:
        ids = [x for x in out.replace("\n", ",").split(",") if x.strip()]
        if any(FLASH_MODEL in x for x in ids):
            result = True, ids, "evo-ssh"
            _PROBE_CACHE = (now, result)
            return result
        if FLASH_MODEL in out:
            result = True, [FLASH_MODEL], "evo-ssh"
            _PROBE_CACHE = (now, result)
            return result
    result = False, ids, "direct" if code else "evo-ssh"
    _PROBE_CACHE = (now, result)
    return result


def preferred_flash_via() -> str:
    """Return the route that last reached flash — direct or evo-ssh."""
    _ok, _ids, via = probe_flash_models()
    return via if _ok else "evo-ssh"


def probe_flash_tag() -> str | None:
    """Return the live flash model id — never invent one."""
    ok, ids, _via = probe_flash_models()
    if not ok:
        return None
    for name in ids:
        if FLASH_MODEL in name:
            return name
    return FLASH_MODEL if ok else None


def _parse_chat_body(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    choices = body.get("choices") or []
    if choices and isinstance(choices[0], dict):
        msg = choices[0].get("message") or {}
        if isinstance(msg, dict):
            content = str(msg.get("content") or "").strip()
            if content:
                return content
            reasoning = str(msg.get("reasoning_content") or "").strip()
            if reasoning:
                return reasoning
        return str(choices[0].get("text") or "")
    return str(body.get("text") or "")


def _delta_from_sse_payload(payload: str) -> str:
    if payload == "[DONE]":
        return ""
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        return ""
    if not isinstance(obj, dict):
        return ""
    choices = obj.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return ""
    delta = choices[0].get("delta") or {}
    if isinstance(delta, dict):
        content = str(delta.get("content") or delta.get("reasoning_content") or "")
        if content:
            return content
    message = choices[0].get("message") or {}
    if isinstance(message, dict):
        return str(message.get("content") or message.get("reasoning_content") or "")
    return ""


def _iter_flash_sse_direct(payload: dict[str, Any], *, timeout: float) -> Iterator[str]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        FLASH_CHAT_URL,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            while True:
                raw = resp.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                payload_text = line[5:].strip()
                delta = _delta_from_sse_payload(payload_text)
                if delta:
                    yield delta
                if payload_text == "[DONE]":
                    break
    except urllib.error.HTTPError as exc:
        raw = exc.read() if exc.fp else b""
        detail = raw.decode("utf-8", errors="replace")[:160]
        raise RuntimeError(f"5090 flash HTTP {exc.code}: {detail or exc}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"5090 flash unreachable: {exc.reason if getattr(exc, 'reason', None) else exc}") from exc


def _iter_flash_sse_ssh(payload: dict[str, Any], *, timeout: float) -> Iterator[str]:
    remote = remote_python3_cmd(_FLASH_SSH_STREAM_PY, str(int(timeout)))
    cmd = _ssh_argv(remote)
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        raise RuntimeError(f"5090 flash ssh failed: {exc}") from exc
    assert proc.stdin is not None
    assert proc.stdout is not None
    try:
        proc.stdin.write(json.dumps(payload))
        proc.stdin.close()
    except OSError as exc:
        proc.kill()
        raise RuntimeError(f"5090 flash ssh stdin failed: {exc}") from exc
    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            delta = str(obj.get("delta") or "")
            if delta:
                yield delta
    finally:
        try:
            proc.wait(timeout=max(1.0, timeout - 1.0))
        except subprocess.TimeoutExpired:
            proc.kill()
            raise RuntimeError("5090 flash ssh stream timed out") from None
        if proc.returncode != 0:
            err = (proc.stderr.read() if proc.stderr else "")[:400]
            raise RuntimeError(f"5090 flash chat failed via evo-ssh: {err or proc.returncode}")


def _flash_messages(prompt: str, *, system: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system.strip():
        messages.append({"role": "system", "content": system.strip()})
    messages.append({"role": "user", "content": prompt})
    return messages


def _flash_payload(
    tag: str,
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    stream: bool,
) -> dict[str, Any]:
    return {
        "model": tag,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }


def _iter_with_first_token_timeout(
    source: Iterator[tuple[str, str]],
    *,
    first_token_timeout: float,
) -> Iterator[tuple[str, str]]:
    """Fail only when no token arrives within first_token_timeout."""
    q: queue.Queue[tuple[str, Any]] = queue.Queue()

    def _worker() -> None:
        try:
            for item in source:
                q.put(("item", item))
        except Exception as exc:  # noqa: BLE001
            q.put(("error", exc))
        q.put(("done", None))

    threading.Thread(target=_worker, daemon=True).start()
    try:
        kind, payload = q.get(timeout=first_token_timeout)
    except queue.Empty:
        raise RuntimeError(
            f"5090 flash: no first token within {int(first_token_timeout)}s — check tower :11435"
        ) from None
    if kind == "error":
        raise payload
    if kind == "done":
        return
    yield payload
    while True:
        kind, payload = q.get()
        if kind == "error":
            raise payload
        if kind == "done":
            break
        yield payload


def _iter_flash_chat_raw(
    tag: str,
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
    timeout: float,
) -> Iterator[tuple[str, str]]:
    payload = _flash_payload(tag, messages, temperature=temperature, max_tokens=max_tokens, stream=True)
    via = preferred_flash_via()
    if via == "direct":
        try:
            for delta in _iter_flash_sse_direct(payload, timeout=min(timeout, 30.0)):
                yield delta, "direct"
            return
        except RuntimeError:
            via = "evo-ssh"
    for delta in _iter_flash_sse_ssh(payload, timeout=timeout):
        yield delta, via


def iter_flash_chat(
    prompt: str,
    *,
    model: str | None = None,
    system: str = "",
    temperature: float = 0.2,
    max_tokens: int = 2048,
    timeout: float = 120.0,
    first_token_timeout: float = FIRST_TOKEN_TIMEOUT_S,
) -> Iterator[tuple[str, str]]:
    """Yield (delta, via) tokens from tower Flash-Next."""
    tag = model or probe_flash_tag()
    if not tag:
        raise RuntimeError("5090 flash not reachable on tower :11435")
    messages = _flash_messages(prompt, system=system)
    raw = _iter_flash_chat_raw(
        tag,
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    yield from _iter_with_first_token_timeout(raw, first_token_timeout=first_token_timeout)


def flash_chat(
    prompt: str,
    *,
    model: str | None = None,
    system: str = "",
    temperature: float = 0.2,
    max_tokens: int = 2048,
    timeout: float = 120.0,
    on_delta: DeltaFn | None = None,
) -> dict[str, Any]:
    """OpenAI chat against tower Flash-Next. Streams when on_delta is set."""
    tag = model or probe_flash_tag()
    if not tag:
        raise RuntimeError("5090 flash not reachable on tower :11435")
    if on_delta is not None:
        parts: list[str] = []
        via = "evo-ssh"
        for delta, route in iter_flash_chat(
            prompt,
            model=tag,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        ):
            via = route
            parts.append(delta)
            on_delta(delta)
        text = "".join(parts)
        if not text.strip():
            raise RuntimeError("5090 flash returned empty reply")
        return {"text": text, "model": tag, "via": via, "backend": "flash", "gpu": "RTX 5090"}

    messages = _flash_messages(prompt, system=system)
    payload = _flash_payload(tag, messages, temperature=temperature, max_tokens=max_tokens, stream=False)
    via = preferred_flash_via()
    if via == "direct":
        code, body = request_json(
            FLASH_CHAT_URL,
            method="POST",
            body=payload,
            timeout=min(timeout, _DIRECT_TIMEOUT_S),
        )
        if code == 200 and isinstance(body, dict):
            text = _parse_chat_body(body)
            if text.strip():
                return {"text": text, "model": tag, "via": "direct", "backend": "flash", "gpu": "RTX 5090"}
    via = "evo-ssh"
    remote = remote_python3_cmd(_FLASH_SSH_ONCE_PY, str(int(timeout)))
    try:
        proc = subprocess.run(
            _ssh_argv(remote),
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=timeout + 10.0,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"5090 flash chat failed via {via}: {str(exc)[:200]}") from exc
    out = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    if proc.returncode != 0 or not out:
        raise RuntimeError(f"5090 flash chat failed via {via}: {out[:400] or 'empty'}")
    try:
        parsed = json.loads(out)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"5090 flash chat returned invalid JSON: {out[:160]}") from exc
    text = _parse_chat_body(parsed)
    if not text.strip():
        raise RuntimeError("5090 flash returned empty reply")
    return {"text": text, "model": tag, "via": via, "backend": "flash", "gpu": "RTX 5090"}
