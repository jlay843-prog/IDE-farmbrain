"""Small HTTP helpers. Farm APIs may need X-Farm-Local-Key from Legion."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

TOKEN_CANDIDATES = (
    Path(os.environ.get("FORGE_FARM_TOKEN_FILE", "")),
    Path(r"C:\Users\jlay\secrets\farm_operator_token.txt"),
)


def farm_token() -> str:
    env = (os.environ.get("FORGE_FARM_TOKEN") or os.environ.get("FARM_LOCAL_KEY") or "").strip()
    if env:
        return env
    for path in TOKEN_CANDIDATES:
        if path and path.is_file():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return text
    return ""


def request_json(
    url: str,
    *,
    method: str = "GET",
    body: dict | None = None,
    timeout: float = 4.0,
    farm: bool = False,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    if farm:
        token = farm_token()
        if token:
            headers["X-Farm-Local-Key"] = token
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if not raw:
                return resp.status, {}
            try:
                return resp.status, json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return resp.status, {"text": raw.decode("utf-8", errors="replace")}
    except urllib.error.HTTPError as exc:
        raw = exc.read() if exc.fp else b""
        parsed: Any
        try:
            parsed = json.loads(raw.decode("utf-8")) if raw else {"error": str(exc)}
        except json.JSONDecodeError:
            parsed = {"error": raw.decode("utf-8", errors="replace") or str(exc)}
        return exc.code, parsed
    except Exception as exc:  # noqa: BLE001 — probe failures are expected
        return 0, {"error": str(exc)}


def iter_ndjson(
    url: str,
    *,
    method: str = "POST",
    body: dict | None = None,
    timeout: float = 180.0,
):
    """Yield JSON objects from an NDJSON HTTP response, line by line."""
    data = None
    headers = {"Accept": "application/x-ndjson, application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            while True:
                line = resp.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    yield {"error": line.decode("utf-8", errors="replace")}
    except urllib.error.HTTPError as exc:
        raw = exc.read() if exc.fp else b""
        try:
            parsed = json.loads(raw.decode("utf-8")) if raw else {"error": str(exc)}
        except json.JSONDecodeError:
            parsed = {"error": raw.decode("utf-8", errors="replace") or str(exc)}
        err = parsed.get("error") if isinstance(parsed, dict) else parsed
        raise RuntimeError(f"HTTP {exc.code}: {err}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc.reason if getattr(exc, "reason", None) else exc)) from exc
