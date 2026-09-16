"""Thin local git status / diff / commit. No remotes, no push, no PRs."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from forge.context import resolve_under

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
MAX_STATUS = 200
MAX_DIFF_CHARS = 200_000
MAX_UNTRACKED_BYTES = 64_000
GIT_TIMEOUT = 20

_STATUS_NAMES = {
    "M": "modified",
    "A": "added",
    "D": "deleted",
    "R": "renamed",
    "C": "copied",
    "U": "unmerged",
    "?": "untracked",
    "!": "ignored",
    " ": "unchanged",
}


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["LC_ALL"] = "C"
    return env


def run_git(cwd: Path, args: list[str], timeout: int = GIT_TIMEOUT) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", "-c", "core.quotepath=false", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=_env(),
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("git timed out") from exc
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def git_root(workspace: Path) -> Path | None:
    code, out, _ = run_git(workspace, ["rev-parse", "--show-toplevel"])
    if code != 0:
        return None
    text = out.strip()
    if not text:
        return None
    return Path(text).resolve()


def _norm(rel: str) -> str:
    return (rel or "").replace("\\", "/").strip("/")


def _safe_rel(root: Path, rel: str) -> str:
    return _norm(str(resolve_under(root, rel).relative_to(root.resolve())))


def _label(index: str, worktree: str) -> str:
    if index == "?" and worktree == "?":
        return "untracked"
    if "U" in index + worktree:
        return "unmerged"
    if index == "R" or worktree == "R":
        return "renamed"
    if index == "A" or worktree == "A":
        return "added"
    if index == "D" or worktree == "D":
        return "deleted"
    if index == "C" or worktree == "C":
        return "copied"
    if index == "M" or worktree == "M":
        return "modified"
    return _STATUS_NAMES.get(worktree or index, "changed")


def _parse_branch_header(line: str) -> dict:
    text = line[2:].strip() if line.startswith("##") else line.strip()
    info: dict = {
        "branch": "",
        "detached": False,
        "empty": False,
        "upstream": None,
        "ahead": 0,
        "behind": 0,
    }
    if text.startswith("No commits yet on "):
        info["empty"] = True
        info["branch"] = text[len("No commits yet on ") :].split("...")[0].strip()
        return info
    if text.startswith("HEAD (no branch)"):
        info["detached"] = True
        info["branch"] = "HEAD"
        return info
    name, _, rest = text.partition("...")
    info["branch"] = name.strip() or "HEAD"
    if rest:
        upstream, _, trail = rest.partition(" ")
        info["upstream"] = upstream.strip() or None
        if "[ahead " in trail or "[behind " in trail:
            body = trail.strip().strip("[]")
            for part in body.split(","):
                bits = part.strip().split()
                if len(bits) == 2 and bits[0] == "ahead":
                    try:
                        info["ahead"] = int(bits[1])
                    except ValueError:
                        pass
                if len(bits) == 2 and bits[0] == "behind":
                    try:
                        info["behind"] = int(bits[1])
                    except ValueError:
                        pass
    return info


def _parse_porcelain(raw: str) -> tuple[dict, list[dict]]:
    parts = raw.split("\0")
    header = {"branch": "", "detached": False, "empty": False, "upstream": None, "ahead": 0, "behind": 0}
    files: list[dict] = []
    i = 0
    if parts and parts[0].startswith("## "):
        header = _parse_branch_header(parts[0])
        i = 1
    while i < len(parts):
        rec = parts[i]
        i += 1
        if not rec:
            continue
        if rec.startswith("## "):
            header = _parse_branch_header(rec)
            continue
        if len(rec) < 3:
            continue
        index, worktree, path = rec[0], rec[1], rec[2:].lstrip()
        old = None
        if index in {"R", "C"}:
            if i < len(parts) and parts[i]:
                old = path
                path = parts[i]
                i += 1
            elif " -> " in path:
                old, _, path = path.partition(" -> ")
        files.append(
            {
                "path": _norm(path),
                "old": _norm(old) if old else None,
                "index": index,
                "worktree": worktree,
                "staged": index not in {" ", "?"},
                "status": _label(index, worktree),
            }
        )
        if len(files) >= MAX_STATUS:
            break
    return header, files


def _remotes(root: Path) -> list[str]:
    code, out, _ = run_git(root, ["remote"])
    if code != 0:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _head(root: Path) -> str:
    code, out, _ = run_git(root, ["rev-parse", "--short", "HEAD"])
    if code != 0:
        return ""
    return out.strip()


def empty_snapshot(workspace: str = "") -> dict:
    return {
        "ok": True,
        "repo": False,
        "workspace": workspace,
        "root": "",
        "branch": "",
        "head": "",
        "empty": False,
        "detached": False,
        "upstream": None,
        "ahead": 0,
        "behind": 0,
        "remotes": [],
        "files": [],
        "truncated": False,
        "summary": "Not a git repository.",
    }


def snapshot(workspace: Path | None) -> dict:
    if workspace is None:
        return empty_snapshot()
    root_dir = workspace.resolve()
    try:
        root = git_root(root_dir)
    except RuntimeError as exc:
        data = empty_snapshot(str(root_dir))
        data["ok"] = False
        data["error"] = str(exc)
        data["summary"] = str(exc)
        return data
    if root is None:
        return empty_snapshot(str(root_dir))
    code, out, err = run_git(root, ["status", "--porcelain=v1", "-b", "-z", "--untracked-files=all"])
    if code != 0:
        data = empty_snapshot(str(root_dir))
        data["ok"] = False
        data["repo"] = True
        data["root"] = str(root)
        data["error"] = (err or out or "git status failed").strip()
        data["summary"] = data["error"]
        return data
    header, files = _parse_porcelain(out)
    remotes = _remotes(root)
    empty = bool(header["empty"])
    if not empty:
        probe, _, _ = run_git(root, ["rev-parse", "--verify", "HEAD"])
        empty = probe != 0
        header["empty"] = empty
    head = "" if empty else _head(root)
    truncated = len(files) >= MAX_STATUS
    n = len(files)
    if n == 0:
        summary = "Working tree clean."
    elif n == 1:
        summary = "1 changed path."
    else:
        summary = f"{n} changed paths."
    if empty:
        summary = f"No commits yet on {header['branch'] or 'HEAD'}. " + summary
    return {
        "ok": True,
        "repo": True,
        "workspace": str(root_dir),
        "root": str(root),
        "branch": header["branch"],
        "head": head,
        "empty": empty,
        "detached": bool(header["detached"]),
        "upstream": header["upstream"],
        "ahead": int(header["ahead"] or 0),
        "behind": int(header["behind"] or 0),
        "remotes": remotes,
        "files": files,
        "truncated": truncated,
        "summary": summary.strip(),
    }


def _new_file_diff(rel: str, text: str) -> str:
    lines = text.splitlines()
    body = "\n".join(f"+{line}" for line in lines)
    n = max(len(lines), 1) if text else 0
    hunk = f"@@ -0,0 +1,{n} @@" if n else "@@ -0,0 +0,0 @@"
    return (
        f"diff --git a/{rel} b/{rel}\n"
        "new file mode 100644\n"
        f"--- /dev/null\n"
        f"+++ b/{rel}\n"
        f"{hunk}\n"
        f"{body}\n"
    )


def _untracked_diff(root: Path, rel: str) -> str:
    path = resolve_under(root, rel)
    if not path.is_file():
        return f"diff --git a/{rel} b/{rel}\nnew file mode 100644\n--- /dev/null\n+++ b/{rel}\n"
    try:
        data = path.read_bytes()
    except OSError as exc:
        return f"error reading {rel}: {exc}\n"
    if b"\0" in data:
        return f"diff --git a/{rel} b/{rel}\nnew file mode 100644\nBinary file {rel} differs\n"
    if len(data) > MAX_UNTRACKED_BYTES:
        return (
            f"diff --git a/{rel} b/{rel}\n"
            "new file mode 100644\n"
            f"--- /dev/null\n"
            f"+++ b/{rel}\n"
            f"@@ untracked file truncated at {MAX_UNTRACKED_BYTES} bytes @@\n"
        )
    text = data.decode("utf-8", errors="replace")
    return _new_file_diff(rel, text)


def _trim(text: str) -> str:
    if len(text) <= MAX_DIFF_CHARS:
        return text
    return text[:MAX_DIFF_CHARS] + "\n\n/* diff truncated */\n"


def _tracked_diff(root: Path, rel: str | None, empty: bool) -> str:
    args = ["diff", "--find-renames"]
    if empty:
        args.append(EMPTY_TREE)
    else:
        args.append("HEAD")
    args.append("--")
    if rel:
        args.append(rel)
    code, out, err = run_git(root, args)
    if empty and code not in {0, 1}:
        return ""
    if code not in {0, 1}:
        raise ValueError((err or out or "git diff failed").strip())
    return out


def diff_for(workspace: Path | None, rel: str = "") -> dict:
    snap = snapshot(workspace)
    if not snap.get("ok"):
        return {**snap, "path": rel or "", "diff": ""}
    if not snap.get("repo"):
        return {**snap, "path": rel or "", "diff": "", "error": "Not a git repository."}
    root = Path(snap["root"])
    path = _safe_rel(root, rel) if rel else ""
    empty = bool(snap.get("empty"))
    files = {row["path"]: row for row in snap["files"]}
    chunks: list[str] = []
    if path:
        row = files.get(path)
        if row and row.get("status") == "untracked":
            chunks.append(_untracked_diff(root, path))
        else:
            tracked = _tracked_diff(root, path, empty)
            if tracked.strip():
                chunks.append(tracked)
            elif row is None:
                chunks.append(f"No changes in {path}.\n")
        staged_args = ["diff", "--cached", "--"]
        staged_args.append(path)
        _, staged, _ = run_git(root, staged_args)
        if staged.strip() and staged not in chunks:
            chunks.insert(0, staged)
    else:
        tracked = _tracked_diff(root, None, empty)
        if tracked.strip():
            chunks.append(tracked)
        _, staged, _ = run_git(root, ["diff", "--cached"])
        if staged.strip() and staged not in chunks:
            chunks.insert(0, staged)
        for row in snap["files"]:
            if row.get("status") == "untracked":
                chunks.append(_untracked_diff(root, row["path"]))
    text = _trim("\n".join(chunk.rstrip() for chunk in chunks if chunk).strip())
    if not text:
        text = "Working tree clean.\n" if not path else f"No changes in {path}.\n"
    return {
        "ok": True,
        "repo": True,
        "root": str(root),
        "branch": snap.get("branch") or "",
        "empty": empty,
        "path": path,
        "diff": text,
        "remotes": snap.get("remotes") or [],
    }


def commit(workspace: Path | None, message: str, paths: list[str] | None = None) -> dict:
    snap = snapshot(workspace)
    if not snap.get("ok"):
        return snap
    if not snap.get("repo"):
        raise ValueError("Not a git repository.")
    msg = (message or "").strip()
    if not msg:
        raise ValueError("Commit message is empty.")
    root = Path(snap["root"])
    wanted = [_safe_rel(root, p) for p in (paths or []) if str(p).strip()]
    if not wanted:
        wanted = [row["path"] for row in snap["files"] if row.get("path")]
    if not wanted:
        raise ValueError("Nothing to commit.")
    code, out, err = run_git(root, ["add", "--", *wanted])
    if code != 0:
        raise ValueError((err or out or "git add failed").strip())
    code, out, err = run_git(root, ["commit", "-m", msg, "--", *wanted])
    if code != 0:
        raise ValueError((err or out or "git commit failed").strip())
    after = snapshot(workspace)
    after["committed"] = True
    after["message"] = msg
    after["paths"] = wanted
    after["log"] = (out or "").strip()
    return after
