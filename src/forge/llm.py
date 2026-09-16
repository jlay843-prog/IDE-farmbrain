"""Ollama chat against a chosen farm backend. Never port-forward."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from forge.httputil import iter_ndjson


def iter_chat(
    base: str,
    model: str,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.2,
    keep_alive: str = "30m",
    timeout: float = 180.0,
) -> Iterator[dict[str, Any]]:
    """Yield Ollama /api/chat chunks with stream=True (one NDJSON object per line)."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
        "keep_alive": keep_alive,
        "options": {"temperature": temperature},
    }
    if tools:
        payload["tools"] = tools
    try:
        for obj in iter_ndjson(f"{base}/api/chat", method="POST", body=payload, timeout=timeout):
            if not isinstance(obj, dict):
                continue
            if obj.get("error") and not obj.get("message"):
                raise RuntimeError(f"Ollama {base} returned error: {obj['error']}")
            message = obj.get("message") or {}
            delta = message.get("content") or obj.get("response") or ""
            yield {
                "delta": delta,
                "done": bool(obj.get("done")),
                "model": obj.get("model") or model,
                "tool_calls": message.get("tool_calls") or [],
                "raw": obj,
            }
            if obj.get("done"):
                return
    except RuntimeError as exc:
        raise RuntimeError(f"Ollama {base} failed: {exc}") from exc


def chat(
    base: str,
    model: str,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.2,
    keep_alive: str = "30m",
    timeout: float = 180.0,
) -> dict[str, Any]:
    parts: list[str] = []
    last: dict[str, Any] = {}
    tool_calls: list[Any] = []
    for chunk in iter_chat(
        base,
        model,
        messages,
        tools=tools,
        temperature=temperature,
        keep_alive=keep_alive,
        timeout=timeout,
    ):
        if chunk.get("delta"):
            parts.append(chunk["delta"])
        if chunk.get("tool_calls"):
            tool_calls = chunk["tool_calls"]
        last = chunk
    raw = last.get("raw") or {}
    return {
        "text": "".join(parts),
        "model": last.get("model") or model,
        "done": last.get("done", True),
        "tool_calls": tool_calls,
        "raw": raw,
    }
