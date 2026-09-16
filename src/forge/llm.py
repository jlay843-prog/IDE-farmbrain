"""Ollama chat against a chosen farm backend. Never port-forward."""

from __future__ import annotations

from typing import Any

from forge.httputil import request_json


def chat(
    base: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.2,
    keep_alive: str = "30m",
    timeout: float = 180.0,
) -> dict[str, Any]:
    code, body = request_json(
        f"{base}/api/chat",
        method="POST",
        body={
            "model": model,
            "messages": messages,
            "stream": False,
            "keep_alive": keep_alive,
            "options": {"temperature": temperature},
        },
        timeout=timeout,
    )
    if code != 200:
        err = body.get("error") if isinstance(body, dict) else body
        raise RuntimeError(f"Ollama {base} returned {code}: {err}")
    message = (body or {}).get("message") or {}
    text = message.get("content") or body.get("response") or ""
    return {
        "text": text,
        "model": body.get("model") or model,
        "done": body.get("done", True),
        "raw": body,
    }
