"""Parse and apply unified diffs. Confirmation is the caller's job."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from forge.context import resolve_under

FENCE_RE = re.compile(r"^```(?:diff|patch)?\s*$", re.I)
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class FilePatch:
    path: str
    old_path: str
    is_new: bool
    is_delete: bool
    lines: list[str] = field(default_factory=list)


def extract_diff(text: str) -> str:
    stripped = text.strip()
    if "```" in stripped:
        chunks = stripped.split("```")
        for i, chunk in enumerate(chunks):
            body = chunk
            if i % 2 == 1:
                if body.lower().startswith(("diff", "patch")):
                    body = body.split("\n", 1)[1] if "\n" in body else ""
                if "--- " in body or "+++" in body:
                    return body.strip()
        for i, chunk in enumerate(chunks):
            if i % 2 == 1 and ("--- " in chunk or "@@ " in chunk):
                body = chunk
                if body.lower().startswith(("diff", "patch")):
                    body = body.split("\n", 1)[1] if "\n" in body else ""
                return body.strip()
    return stripped


def parse_unified_diff(text: str) -> list[FilePatch]:
    diff = extract_diff(text)
    patches: list[FilePatch] = []
    current: FilePatch | None = None
    for raw in diff.splitlines():
        if raw.startswith("diff --git"):
            continue
        if raw.startswith("--- "):
            old = raw[4:].strip()
            if old.startswith("a/"):
                old = old[2:]
            current = FilePatch(path="", old_path=old, is_new=old == "/dev/null", is_delete=False)
            continue
        if raw.startswith("+++ ") and current is not None:
            new = raw[4:].strip()
            if new.startswith("b/"):
                new = new[2:]
            current.is_delete = new == "/dev/null"
            current.path = current.old_path if current.is_delete else new
            if current.path in {"/dev/null", ""}:
                current.path = current.old_path
            patches.append(current)
            continue
        if current is not None:
            current.lines.append(raw)
    return [p for p in patches if p.path]


def _apply_hunks(original: str, patch_lines: list[str]) -> str:
    src = original.splitlines()
    out: list[str] = []
    idx = 0
    i = 0
    while i < len(patch_lines):
        line = patch_lines[i]
        match = HUNK_RE.match(line)
        if not match:
            i += 1
            continue
        old_start = int(match.group(1))
        cursor = max(old_start - 1, 0)
        if cursor > idx:
            out.extend(src[idx:cursor])
            idx = cursor
        elif cursor < idx:
            # Overlapping / already consumed — keep going from current idx
            pass
        i += 1
        while i < len(patch_lines) and not patch_lines[i].startswith("@@"):
            row = patch_lines[i]
            if row.startswith("+"):
                out.append(row[1:])
            elif row.startswith("-"):
                if idx < len(src):
                    idx += 1
            elif row.startswith("\\"):
                pass
            else:
                context = row[1:] if row.startswith(" ") else row
                if idx < len(src):
                    out.append(src[idx])
                    idx += 1
                else:
                    out.append(context)
            i += 1
    out.extend(src[idx:])
    newline = "\n" if original.endswith("\n") or not original else ""
    body = "\n".join(out)
    if original.endswith("\n") and not body.endswith("\n"):
        body += "\n"
    elif newline and not original:
        body += "\n" if body and not body.endswith("\n") else ""
    return body


def apply_diff(workspace: Path, diff_text: str) -> list[str]:
    changed: list[str] = []
    for patch in parse_unified_diff(diff_text):
        dest = resolve_under(workspace, patch.path)
        if patch.is_delete:
            if dest.is_file():
                dest.unlink()
                changed.append(patch.path)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        original = dest.read_text(encoding="utf-8", errors="replace") if dest.is_file() else ""
        if patch.is_new and not dest.exists():
            added = [ln[1:] for ln in patch.lines if ln.startswith("+") and not ln.startswith("+++")]
            dest.write_text("\n".join(added) + ("\n" if added else ""), encoding="utf-8")
        else:
            dest.write_text(_apply_hunks(original, patch.lines), encoding="utf-8")
        changed.append(patch.path)
    if not changed:
        raise ValueError("no file hunks found in model reply")
    return changed


EDIT_SYSTEM = """You are Forge, a local coding assistant on this farm LAN.
Return ONLY a unified diff that applies to the workspace (--- a/ +++ b/ @@ hunks).
Paths are relative to the workspace root. Do not open Ollama to the internet.
Do not wrap the diff in extra commentary. If you must explain, put it after the diff.
Never propose changes outside the named files unless the user asked to create a new file.
"""


ASK_SYSTEM = """You are Forge, a local coding assistant. Models stay on the farm LAN.
Be concise. Cite file paths when you refer to code. Do not invent hosts or ports.
Code work belongs on EVO AMD qwen3-coder:30b (:11437), not the 5090 when Vast is live.
"""
