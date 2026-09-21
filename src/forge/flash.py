"""Tower 5090 Flash-Next on llama.cpp :11435 (OpenAI-compatible).

Direct HTTP from Legion often fails (bind/firewall); probe and chat fall back to EVO SSH.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from forge.hosts import EVO, TOWER
from forge.httputil import request_json

FLASH_MODEL = "qwen3.8-flash-next"
FLASH_BASE = f"http://{TOWER}:11435"
FLASH_MODELS_URL = f"{FLASH_BASE}/v1/models"
FLASH_CHAT_URL = f"{FLASH_BASE}/v1/chat/completions"
_PROBE_CACHE: tuple[float, tuple[bool, list[str], str]] | None = None
_PROBE_TTL_S = 30.0


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
    code, body = request_json(FLASH_MODELS_URL, timeout=2.0)
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


def flash_chat(
    prompt: str,
    *,
    model: str | None = None,
    system: str = "",
    temperature: float = 0.2,
    max_tokens: int = 2048,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Non-streaming OpenAI chat against tower Flash-Next."""
    tag = model or probe_flash_tag()
    if not tag:
        raise RuntimeError("5090 flash not reachable on tower :11435")
    messages: list[dict[str, str]] = []
    if system.strip():
        messages.append({"role": "system", "content": system.strip()})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": tag,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    code, body = request_json(
        FLASH_CHAT_URL,
        method="POST",
        body=payload,
        timeout=min(timeout, 30.0),
    )
    via = "direct"
    if code == 200 and isinstance(body, dict):
        text = _parse_chat_body(body)
        if text.strip():
            return {"text": text, "model": tag, "via": via, "backend": "flash", "gpu": "RTX 5090"}
    via = "evo-ssh"
    blob = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    remote = (
        "python3 -c "
        "'import json,base64,urllib.request; "
        f"p=json.loads(base64.b64decode(\"{blob}\").decode()); "
        "req=urllib.request.Request("
        "\"http://192.168.68.106:11435/v1/chat/completions\", "
        "data=json.dumps(p).encode(), "
        "headers={\"Content-Type\":\"application/json\"}, method=\"POST\"); "
        f"print(urllib.request.urlopen(req, timeout={int(timeout)}).read().decode())'"
    )
    ok, out = _ssh_run(EVO, remote, timeout=timeout + 10.0)
    if not ok or not out.strip():
        raise RuntimeError(f"5090 flash chat failed via {via}: {out[:160] or 'empty'}")
    try:
        parsed = json.loads(out)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"5090 flash chat returned invalid JSON: {out[:160]}") from exc
    text = _parse_chat_body(parsed)
    if not text.strip():
        raise RuntimeError("5090 flash returned empty reply")
    return {"text": text, "model": tag, "via": via, "backend": "flash", "gpu": "RTX 5090"}
