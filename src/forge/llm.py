"""Ollama chat against a chosen farm backend. Never port-forward."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from forge.httputil import iter_ndjson
from forge.tools import sanitize_messages_for_ollama

OLLAMA_TOOL_XML_ERR = re.compile(
    r"expected element type\s*<function>\s*but have\s*<parameter>",
    re.I,
)


def ollama_tool_xml_error(exc: BaseException) -> bool:
    msg = str(exc)
    if OLLAMA_TOOL_XML_ERR.search(msg):
        return True
    lower = msg.lower()
    return "expected element type" in lower and "parameter" in lower and "function" in lower


def _stream_chat(
    base: str,
    model: str,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.2,
    keep_alive: str = "30m",
    timeout: float = 180.0,
) -> Iterator[dict[str, Any]]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
        "keep_alive": keep_alive,
        "options": {"temperature": temperature},
    }
    if tools:
        payload["tools"] = tools
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
    clean = sanitize_messages_for_ollama(messages)
    try:
        yield from _stream_chat(
            base,
            model,
            clean,
            tools=tools,
            temperature=temperature,
            keep_alive=keep_alive,
            timeout=timeout,
        )
    except RuntimeError as exc:
        if tools and ollama_tool_xml_error(exc):
            yield from _stream_chat(
                base,
                model,
                clean,
                tools=None,
                temperature=temperature,
                keep_alive=keep_alive,
                timeout=timeout,
            )
            return
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
