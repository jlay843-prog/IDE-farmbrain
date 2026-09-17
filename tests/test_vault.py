from pathlib import Path

from forge.vault import resolve_note, search_vault, vault_info


def _vault(tmp_path: Path) -> Path:
    root = tmp_path / "FarmBrainVault"
    (root / "01-Daily").mkdir(parents=True)
    (root / ".obsidian").mkdir()
    (root / ".obsidian" / "workspace.json").write_text("{}\n", encoding="utf-8")
    (root / "01-Daily" / "Agent-Readout.md").write_text(
        "# Agent readout\n\nQC gate still applies.\n", encoding="utf-8"
    )
    (root / "05-Projects").mkdir(parents=True)
    (root / "05-Projects" / "AgentRx-checklist.md").write_text(
        "# AgentRx\n\nInstruction adherence on the farm.\n", encoding="utf-8"
    )
    (root / "02-Facts" / "secret.md").parent.mkdir(parents=True)
    (root / "02-Facts" / "secret.md").write_text("do-not-leak-whole-note " * 40 + "\n", encoding="utf-8")
    return root


def test_search_matches_path_and_content(tmp_path, monkeypatch):
    root = _vault(tmp_path)
    monkeypatch.setenv("FORGE_VAULT", str(root))
    by_path = search_vault("Agent-Readout")
    assert by_path["exists"] is True
    assert by_path["entries"][0]["path"] == "01-Daily/Agent-Readout.md"
    assert "text" not in by_path["entries"][0]
    by_body = search_vault("Instruction adherence")
    paths = [row["path"] for row in by_body["entries"]]
    assert "05-Projects/AgentRx-checklist.md" in paths
    assert "Instruction" in by_body["entries"][0]["snippet"]


def test_search_skips_obsidian_and_does_not_dump_note(tmp_path, monkeypatch):
    root = _vault(tmp_path)
    monkeypatch.setenv("FORGE_VAULT", str(root))
    found = search_vault("workspace")
    assert all(".obsidian" not in row["path"] for row in found["entries"])
    leaked = search_vault("do-not-leak-whole-note")
    assert leaked["entries"]
    blob = leaked["entries"][0]["snippet"]
    assert "do-not-leak-whole-note" in blob
    assert len(blob) <= 160


def test_empty_query_is_empty(tmp_path, monkeypatch):
    root = _vault(tmp_path)
    monkeypatch.setenv("FORGE_VAULT", str(root))
    found = search_vault("  ")
    assert found["entries"] == []
    info = vault_info()
    assert info["exists"] is True
    assert info["path"] == str(root)


def test_resolve_note_stays_in_vault(tmp_path, monkeypatch):
    root = _vault(tmp_path)
    monkeypatch.setenv("FORGE_VAULT", str(root))
    note = resolve_note("01-Daily/Agent-Readout.md")
    assert note.is_file()
    try:
        resolve_note("../outside.md")
        assert False, "should refuse escape"
    except ValueError:
        pass
