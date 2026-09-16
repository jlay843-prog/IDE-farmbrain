from pathlib import Path

from forge.cli import build_parser, main
from forge.log import log_turn


def test_parser_has_week1_commands():
    parser = build_parser()
    names = parser._subparsers._group_actions[0].choices
    for name in ("status", "models", "use", "open", "which", "ask", "edit", "serve", "projects", "recipe", "launch"):
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
