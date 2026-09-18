import json
from pathlib import Path

from forge.cli import build_parser, main
from forge.log import log_turn, read_turns


def test_parser_has_week1_commands():
    parser = build_parser()
    names = parser._subparsers._group_actions[0].choices
    for name in ("status", "models", "use", "open", "which", "ask", "edit", "compare", "git", "serve", "projects", "recipe", "launch", "vault"):
        assert name in names


def test_no_args_exits_zero(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    monkeypatch.setattr(
        "forge.cli.resolve_session",
        lambda tier, model=None: {
            "tier": tier,
            "backend": {"id": "amd", "label": "EVO AMD", "gpu": "GTT", "ok": True},
            "model": "qwen3-coder:30b",
            "base": "http://192.168.68.103:11437",
            "blocked": False,
        },
    )
    assert main([]) == 0
    captured = capsys.readouterr()
    assert "workspace" in captured.out
    assert "usage:" in captured.out.lower() or "status" in captured.out


def test_which_prints_live_backend(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    monkeypatch.setattr(
        "forge.cli.resolve_session",
        lambda tier, model=None: {
            "tier": tier,
            "backend": {"id": "amd", "label": "EVO AMD", "gpu": "Strix Halo GTT", "ok": True},
            "model": "qwen3-coder:30b",
            "base": "http://192.168.68.103:11437",
            "blocked": False,
        },
    )
    assert main(["which"]) == 0
    out = capsys.readouterr().out
    assert "EVO AMD" in out
    assert "qwen3-coder:30b" in out
    assert "11437" in out


def test_use_without_tier_lists_picker_when_not_tty(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    monkeypatch.setattr(
        "forge.cli.picker_snapshot",
        lambda: {
            "vast_active": False,
            "groups": {
                "code": [{"name": "qwen3-coder:30b", "loaded": True, "gpu": "GTT", "tier": "code", "blocked": False}],
                "chat": [{"name": "qwen3.8:27b", "loaded": True, "gpu": "5070", "tier": "chat", "blocked": False}],
                "burst": [],
            },
        },
    )
    monkeypatch.setattr("forge.cli.sys.stdin.isatty", lambda: False)
    assert main(["use"]) == 0
    out = capsys.readouterr().out
    assert "qwen3-coder:30b" in out
    assert "qwen3.8:27b" in out
    assert "not a TTY" in out


def test_models_quiet_lists_loaded_only(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    monkeypatch.setattr(
        "forge.cli.models_snapshot",
        lambda: {
            "vast_active": False,
            "models": [
                {"loaded": True, "backend_ok": True, "backend": "amd", "gpu": "GTT", "name": "qwen3-coder:30b"},
                {"loaded": False, "backend_ok": True, "backend": "cuda", "gpu": "5070", "name": "nomic-embed-text"},
            ],
        },
    )
    assert main(["models", "-q"]) == 0
    out = capsys.readouterr().out
    assert "qwen3-coder:30b" in out
    assert "nomic-embed-text" not in out


def test_session_log_appends_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    log_turn("ask", {"tier": "code", "model": "qwen3-coder:30b", "backend": "amd", "gpu": "GTT"}, "hello")
    path = tmp_path / "data" / "sessions.jsonl"
    text = path.read_text(encoding="utf-8")
    assert "qwen3-coder:30b" in text
    assert '"kind": "ask"' in text
    rows = read_turns(10)
    assert rows[0]["prompt"] == "hello"


def test_ask_streams_tokens_to_stdout(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))

    def fake_ask(prompt, files, **kwargs):
        if kwargs.get("on_begin"):
            kwargs["on_begin"]({"model": "qwen3.8:27b", "backend": "cuda", "gpu": "5070"})
        if kwargs.get("on_delta"):
            kwargs["on_delta"]("Hel")
            kwargs["on_delta"]("lo")
        return {
            "ok": True,
            "kind": "ask",
            "tier": "chat",
            "model": "qwen3.8:27b",
            "backend": "cuda",
            "gpu": "5070",
            "text": "Hello",
            "files": [],
        }

    monkeypatch.setattr("forge.cli.run_ask", fake_ask)
    assert main(["ask", "hi"]) == 0
    out = capsys.readouterr().out
    assert "qwen3.8:27b" in out
    assert "Hello" in out
    log = (tmp_path / "data" / "sessions.jsonl").read_text(encoding="utf-8")
    assert "hi" in log
    assert '"kind": "ask"' in log


def test_electron_names_itself_before_single_instance_lock():
    root = Path(__file__).resolve().parents[1]
    text = (root / "desktop" / "main.cjs").read_text(encoding="utf-8")
    assert 'app.setName("Forge")' in text
    assert "ELECTRON_RUN_AS_NODE" in text
    assert text.index("app.setName") < text.index("requestSingleInstanceLock")


def test_launch_script_passes_repo_root_not_main_cjs():
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "launch-forge.ps1").read_text(encoding="utf-8")
    assert "desktop\\main.cjs" not in text
    assert "node_modules\\electron\\dist\\electron.exe" in text.replace("/", "\\") or "electron.exe" in text
    assert "ArgumentList @($Root)" in text


def test_desk_ui_has_log_tab_and_stream_client():
    root = Path(__file__).resolve().parents[1]
    html = (root / "ui" / "index.html").read_text(encoding="utf-8")
    js = (root / "ui" / "app.js").read_text(encoding="utf-8")
    assert 'data-tab="log"' in html
    assert 'id="log"' in html
    assert "/api/ask/stream" in js
    assert "/api/edit/stream" in js
    assert "ev.tool" in js


def test_desk_ui_has_git_pane_and_no_push():
    root = Path(__file__).resolve().parents[1]
    html = (root / "ui" / "index.html").read_text(encoding="utf-8")
    js = (root / "ui" / "app.js").read_text(encoding="utf-8")
    assert 'id="git"' in html
    assert "/api/git/commit" in js
    assert "/api/git/diff" in js
    assert "git push" not in js.lower()
    assert "pull request" not in js.lower()


def test_edit_prints_multi_file_change_list(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    monkeypatch.setattr("forge.cli.sys.stdin.isatty", lambda: False)

    def fake_edit(prompt, files, **kwargs):
        if kwargs.get("on_begin"):
            kwargs["on_begin"]({"model": "qwen3-coder:30b", "backend": "amd", "gpu": "GTT"})
        if kwargs.get("on_delta"):
            kwargs["on_delta"]("--- a/a.py\n")
        return {
            "ok": True,
            "kind": "edit",
            "tier": "code",
            "model": "qwen3-coder:30b",
            "backend": "amd",
            "gpu": "GTT",
            "text": "--- a/a.py\n+++ b/a.py\n",
            "files": files or [],
            "changes": [
                {"path": "a.py", "kind": "modified", "new": False, "delete": False, "hunks": 1, "added": 2, "deleted": 1},
                {"path": "b.py", "kind": "added", "new": True, "delete": False, "hunks": 1, "added": 3, "deleted": 0},
            ],
            "applied": False,
            "changed": [],
            "protected": False,
        }

    monkeypatch.setattr("forge.cli.run_edit", fake_edit)
    assert main(["edit", "touch two files", "--file", "a.py", "--file", "b.py"]) == 0
    out = capsys.readouterr().out
    assert "changes (2 files):" in out
    assert "M a.py" in out
    assert "A b.py" in out
    assert "diff not applied" in out


def test_parser_edit_has_hunk_flag():
    parser = build_parser()
    args = parser.parse_args(["edit", "x", "--hunk", "0", "--hunk", "2"])
    assert args.hunk == [0, 2]


def test_desk_ui_has_change_list():
    root = Path(__file__).resolve().parents[1]
    js = (root / "ui" / "app.js").read_text(encoding="utf-8")
    html = (root / "ui" / "index.html").read_text(encoding="utf-8")
    assert "renderChangeList" in js
    assert "selectedFiles" in js
    assert 'id="changeList"' in html
    assert "checkbox" in js
    assert "Apply hunk" in js
    assert "Reject hunk" in js
    assert "hunks" in js


def test_desk_ui_has_farm_brain_qc_confirm():
    root = Path(__file__).resolve().parents[1]
    html = (root / "ui" / "index.html").read_text(encoding="utf-8")
    js = (root / "ui" / "app.js").read_text(encoding="utf-8")
    assert 'id="qcGate"' in html
    assert 'id="qcCheck"' in html
    assert "I understand QC" in html
    assert "requestQcConfirm" in js
    assert "confirm_protected" in js
    assert "window.confirm" not in js
    assert "farm-brain QC" in js


def test_desk_ui_has_mesh_pulse_and_blocked_burst_badge():
    root = Path(__file__).resolve().parents[1]
    js = (root / "ui" / "app.js").read_text(encoding="utf-8")
    css = (root / "ui" / "styles.css").read_text(encoding="utf-8")
    assert "Live pulse" in js
    assert "renderMeshPulse" in js
    assert "badge blocked" in js
    assert "5090 blocked" in js
    assert "20000" in js
    assert ".badge.blocked" in css
    assert ".mesh-pulse" in css


def test_desk_ui_has_vault_search():
    root = Path(__file__).resolve().parents[1]
    html = (root / "ui" / "index.html").read_text(encoding="utf-8")
    js = (root / "ui" / "app.js").read_text(encoding="utf-8")
    assert 'id="vaultSearch"' in html
    assert 'id="vaultHits"' in html
    assert "runVaultSearch" in js
    assert 'target: "vault"' in js
    assert "Search vault notes" in html


def test_desk_ui_has_aether_lumen_handoff():
    root = Path(__file__).resolve().parents[1]
    js = (root / "ui" / "app.js").read_text(encoding="utf-8")
    css = (root / "ui" / "styles.css").read_text(encoding="utf-8")
    assert "renderHandoffCard" in js
    assert "Aether · last URL" in js
    assert "Lumen · last URL" in js
    assert "Open in ${kind === \"aether\" ? \"Aether\" : \"Lumen\"}" in js or "Open in" in js
    assert "not absorbed" in js
    assert ".handoff-url" in css


def test_package_json_has_windows_installer_and_portable():
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "package.json").read_text(encoding="utf-8"))
    assert "dist:win" in data["scripts"]
    targets = [t["target"] for t in data["build"]["win"]["target"]]
    assert targets == ["nsis", "portable"]
    assert data["build"]["win"]["icon"] == "ui/forge.ico"
    assert "Forge-${version}.exe" in data["build"]["win"]["artifactName"]
    assert data["build"]["nsis"]["uninstallDisplayName"] == "Forge"
    assert data["build"]["forceCodeSigning"] is False


def test_vault_cli_search(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    vault = tmp_path / "FarmBrainVault"
    (vault / "01-Daily").mkdir(parents=True)
    (vault / "01-Daily" / "Agent-Readout.md").write_text("# QC gate\n", encoding="utf-8")
    monkeypatch.setenv("FORGE_VAULT", str(vault))
    assert main(["vault", "QC gate"]) == 0
    out = capsys.readouterr().out
    assert "01-Daily/Agent-Readout.md" in out
    assert main(["vault", "--json"]) == 0
    info = capsys.readouterr().out
    assert "FarmBrainVault" in info
