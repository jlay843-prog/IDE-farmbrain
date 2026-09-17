from pathlib import Path

from forge.launch import launch


def test_launch_vault_note_uses_obsidian_uri(tmp_path, monkeypatch):
    vault = tmp_path / "FarmBrainVault"
    (vault / "01-Daily").mkdir(parents=True)
    note = vault / "01-Daily" / "Agent-Readout.md"
    note.write_text("# hi\n", encoding="utf-8")
    monkeypatch.setenv("FORGE_VAULT", str(vault))
    opened = []
    monkeypatch.setattr("forge.launch.os.startfile", lambda uri: opened.append(uri), raising=False)
    result = launch("vault", "01-Daily/Agent-Readout.md")
    assert result["ok"] is True
    assert result["note"] == "01-Daily/Agent-Readout.md"
    assert opened
    assert opened[0].startswith("obsidian://open?vault=FarmBrainVault&file=")
    assert "01-Daily/Agent-Readout.md" in opened[0]

    missing = launch("vault", "no-such-note.md")
    assert missing["ok"] is False
    assert "no-such-note" in missing["error"]
