"""Windows-safe stdout. Legion consoles are often cp1252."""

from __future__ import annotations

import sys


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            try:
                reconf(encoding="utf-8", errors="replace")
            except Exception:
                pass


def out(text: str = "", *, err: bool = False) -> None:
    write_chunk(text + "\n", err=err)


def write_chunk(text: str, *, err: bool = False) -> None:
    """Write without forcing a newline. Used for streamed model tokens."""
    if text == "":
        return
    stream = sys.stderr if err else sys.stdout
    try:
        stream.write(text)
        stream.flush()
    except UnicodeEncodeError:
        encoded = text.encode(stream.encoding or "ascii", errors="replace").decode(stream.encoding or "ascii")
        stream.write(encoded)
        stream.flush()
