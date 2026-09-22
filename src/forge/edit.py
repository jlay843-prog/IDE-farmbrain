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


def parse_hunks(text: str) -> list[dict]:
    rows: list[dict] = []
    hid = 0
    for patch in parse_unified_diff(text):
        kind = "deleted" if patch.is_delete else "added" if patch.is_new else "modified"
        i = 0
        lines = patch.lines
        while i < len(lines):
            match = HUNK_RE.match(lines[i])
            if not match:
                i += 1
                continue
            header = lines[i]
            block = [header]
            i += 1
            while i < len(lines) and not lines[i].startswith("@@"):
                block.append(lines[i])
                i += 1
            _, added, deleted = _line_stats(block)
            rows.append(
                {
                    "id": hid,
                    "path": patch.path,
                    "header": header,
                    "old_start": int(match.group(1)),
                    "old_count": int(match.group(2) or 1),
                    "new_start": int(match.group(3)),
                    "new_count": int(match.group(4) or 1),
                    "added": added,
                    "deleted": deleted,
                    "kind": kind,
                    "new": patch.is_new,
                    "delete": patch.is_delete,
                    "lines": block,
                }
            )
            hid += 1
    return rows


def hunk_list(text: str) -> list[dict]:
    return [{k: v for k, v in row.items() if k != "lines"} for row in parse_hunks(text)]


def format_hunk_list(rows: list[dict]) -> str:
    if not rows:
        return "no hunks in this reply"
    lines = [f"hunks ({len(rows)}):"]
    for row in rows:
        lines.append(
            f"  {row.get('id')}) {row.get('path')}  {row.get('header')}  +{row.get('added', 0)} -{row.get('deleted', 0)}"
        )
    return "\n".join(lines)


def diff_for_hunks(text: str, hunk_ids: list[int] | None) -> str:
    if hunk_ids is None:
        return extract_diff(text)
    wanted = {int(i) for i in hunk_ids}
    chosen = [row for row in parse_hunks(text) if row["id"] in wanted]
    if not chosen:
        raise ValueError("no matching hunks")
    parts: list[str] = []
    i = 0
    while i < len(chosen):
        first = chosen[i]
        group = [first]
        i += 1
        while i < len(chosen) and chosen[i]["path"] == first["path"] and chosen[i]["new"] == first["new"] and chosen[i]["delete"] == first["delete"]:
            group.append(chosen[i])
            i += 1
        old = "/dev/null" if first["new"] else f"a/{first['path']}"
        new = "/dev/null" if first["delete"] else f"b/{first['path']}"
        body = "\n".join("\n".join(h["lines"]) for h in group)
        parts.append(f"--- {old}\n+++ {new}\n{body}")
    return "\n".join(parts)


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


def apply_diff(workspace: Path, diff_text: str, hunk_ids: list[int] | None = None) -> list[str]:
    if hunk_ids is not None:
        diff_text = diff_for_hunks(diff_text, hunk_ids)
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
You may call tools: read, list, grep. There is no shell, no bash, no cmd, no powershell, no Python eval.
- read: one named file under the workspace.
- list: one directory; names and paths only.
- grep: a Python regex over file contents (optional path/glob). Never pipes or subprocess.
When you need more context, call read/list/grep in this same Edit turn. Never tell Jeff to click Edit again or say you will check files later.
After you have enough context, return ONLY a unified diff (--- a/ +++ b/ @@ hunks).
One reply may change several files: emit a --- / +++ pair per file.
New files are allowed: use --- /dev/null and +++ b/relative/path with + lines in the hunk.
Paths are relative to the workspace root. Do not open Ollama to the internet.
Do not wrap the diff in extra commentary. If you must explain, put it after the diff.
Never dump the whole repository. Prefer changes inside named files; creating a new file via diff is fine when asked.
Jeff Accepts or Applies your unified diff to write project files locally — never say you cannot touch the filesystem.
Never dump raw tool XML in the final reply; use tools only during inspection, then return the diff.
You CANNOT run cmd/bash/powershell, deploy or host servers, live collaboration, or browser automation.
To call a tool without native function-calling, emit:
<tool name="read">{"path": "src/file.py"}</tool>
"""


def edit_system_text(easy: bool = False) -> str:
    """Edit system prompt plus GATE.md when that file ships beside this module."""
    base = f"{EASY_EDIT_PREFIX}{EDIT_SYSTEM}" if easy else EDIT_SYSTEM
    path = Path(__file__).with_name("GATE.md")
    try:
        extra = path.read_text(encoding="utf-8").strip()
    except OSError:
        return base
    if not extra:
        return base
    return base + "\n\n" + extra

EASY_EDIT_PREFIX = """Easy mode: Jeff reviews your unified diff and clicks Accept once to write all changes. After Accept he can Open the last created or changed file in its OS app.
"""

ASK_SYSTEM = """You are Forge, a local coding assistant. Models stay on the farm LAN.
Be concise. Cite file paths when you refer to code. Do not invent hosts or ports.
In Ask mode you answer and plan in chat — you do not emit file diffs in this turn.
To create or change files, tell Jeff to switch to Edit on the desk, check the target file(s) as named context, send the prompt, review the reply, and click Apply hunk (or Apply remaining).
You CANNOT run cmd, bash, or PowerShell — never suggest bash, touch, cmd, powershell, or running terminal commands. Jeff runs commands in the Terminal pane.
You CANNOT deploy or host servers, live collaboration, or browser automation.
Never say you cannot touch the filesystem — in Edit mode Forge writes files when Jeff Applies diffs.
Never dump raw tool XML in chat replies.
Code work belongs on EVO AMD qwen3-coder-next:latest (:11437), not the 5090 when Vast is live.
"""

EASY_ASK_SYSTEM = """You are Forge in Easy mode — a local coding assistant on Jeff's machine. Models stay on the farm LAN.
Be concise. Answer questions, explain code, and help plan work in this chat.
What Forge CAN do in Easy mode:
- Create and edit project files: describe what you want; create/change work returns a unified diff and Jeff clicks Accept to write files locally.
- After Accept, Jeff can click Open to launch the last created or changed file in its OS app.
- Answer and plan in chat (this turn).
What Forge CANNOT do:
- Run cmd, bash, or PowerShell — there is no shell. Jeff runs commands in Advanced mode's Terminal.
- Deploy or host servers, live collaboration, or browser automation.
Never say you cannot touch the filesystem — files are first-class; Jeff Accepts diffs to write them.
Never dump raw tool XML (<tool>, <function>, etc.) in chat replies.
Code work uses EVO AMD qwen3-coder-next:latest (:11437); do not use the 5090 when Vast is live.
"""
