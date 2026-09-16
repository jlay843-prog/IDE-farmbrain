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
            current.path = current.path.replace("\\", "/")
            patches.append(current)
            continue
        if current is not None:
            current.lines.append(raw)
    return [p for p in patches if p.path]


def _line_stats(lines: list[str]) -> tuple[int, int, int]:
    hunks = added = deleted = 0
    for line in lines:
        if line.startswith("@@"):
            hunks += 1
        elif line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            deleted += 1
    return hunks, added, deleted


def change_list(text: str) -> list[dict]:
    """Paths a single edit would touch. Empty when the reply is not a unified diff."""
    rows: list[dict] = []
    for patch in parse_unified_diff(text):
        hunks, added, deleted = _line_stats(patch.lines)
        if patch.is_delete:
            kind = "deleted"
        elif patch.is_new:
            kind = "added"
        else:
            kind = "modified"
        rows.append(
            {
                "path": patch.path,
                "kind": kind,
                "new": patch.is_new,
                "delete": patch.is_delete,
                "hunks": hunks,
                "added": added,
                "deleted": deleted,
            }
        )
    return rows


def format_change_list(rows: list[dict]) -> str:
    if not rows:
        return "no file hunks in this reply"
    lines = [f"changes ({len(rows)} file{'s' if len(rows) != 1 else ''}):"]
    for row in rows:
        mark = "D" if row.get("delete") else "A" if row.get("new") else "M"
        hunks = int(row.get("hunks") or 0)
        hunk_bit = f"{hunks} hunk" if hunks == 1 else f"{hunks} hunks"
        lines.append(f"  {mark} {row.get('path')}  +{row.get('added', 0)} -{row.get('deleted', 0)}  {hunk_bit}")
    return "\n".join(lines)


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
You may call tools: read, list, grep. There is no shell, no bash, no cmd, no Python eval.
- read: one named file under the workspace.
- list: one directory; names and paths only.
- grep: a Python regex over file contents (optional path/glob). Never pipes or subprocess.
After you have enough context, return ONLY a unified diff (--- a/ +++ b/ @@ hunks).
One reply may change several named files: emit a --- / +++ pair per file.
Paths are relative to the workspace root. Do not open Ollama to the internet.
Do not wrap the diff in extra commentary. If you must explain, put it after the diff.
Never dump the whole repository. Never propose changes outside named files unless asked to create a file.
To call a tool without native function-calling, emit:
<tool name="read">{"path": "src/file.py"}</tool>
"""


ASK_SYSTEM = """You are Forge, a local coding assistant. Models stay on the farm LAN.
Be concise. Cite file paths when you refer to code. Do not invent hosts or ports.
Code work belongs on EVO AMD qwen3-coder:30b (:11437), not the 5090 when Vast is live.
"""
