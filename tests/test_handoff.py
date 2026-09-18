import json
from pathlib import Path

from forge import handoff as ho
from forge.launch import launch


def test_lumen_url_stays_on_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    assert ho.normalize_url("lumen", "/compliance/deviation").endswith("/compliance/deviation")
    assert ho.normalize_url("lumen", "http://192.168.68.103:8100/compliance/workbench").endswith("/compliance/workbench")
    try:
        ho.normalize_url("lumen", "https://example.com/")
        assert False, "should refuse foreign origin"
    except ValueError:
        pass


def test_aether_needs_http(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    assert ho.normalize_url("aether", "https://ispe.org/page") == "https://ispe.org/page"
    try:
        ho.normalize_url("aether", "javascript:alert(1)")
        assert False, "should refuse non-http"
    except ValueError:
        pass


def test_reads_last_aether_audit_url(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    data = tmp_path / "aether-data"
    data.mkdir()
    monkeypatch.setenv("AETHER_DATA", str(data))
    (data / "audit.jsonl").write_text(
        json.dumps({"kind": "search", "title": "q"}) + "\n"
        + json.dumps({"kind": "navigate", "title": "Page", "url": "https://example.org/last"}) + "\n",
        encoding="utf-8",
    )
    last = ho.read_aether_last_url()
    assert last["url"] == "https://example.org/last"
    assert last["source"] == "aether-audit"
    snap = ho.snapshot()
    assert snap["aether"]["url"] == "https://example.org/last"


def test_remember_writes_sibling_handoff_file(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    data = tmp_path / "aether-data"
    monkeypatch.setenv("AETHER_DATA", str(data))
    ho.remember("aether", "https://example.org/from-forge", title="Forge")
    payload = json.loads((data / "forge-handoff.json").read_text(encoding="utf-8"))
    assert payload["url"] == "https://example.org/from-forge"
    assert payload["from"] == "forge"
    stored = ho.stored_handoff()
    assert stored["aether"]["url"] == "https://example.org/from-forge"


def test_launch_lumen_uses_last_url(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    opened = []
    monkeypatch.setattr("forge.launch.webbrowser.open", lambda url: opened.append(url))
    result = launch("lumen", url="/compliance/deviation")
    assert result["ok"] is True
    assert opened == ["http://192.168.68.103:8100/compliance/deviation"]
    again = launch("lumen")
    assert again["url"] == "http://192.168.68.103:8100/compliance/deviation"


def test_launch_aether_does_not_open_system_browser(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    data = tmp_path / "aether-data"
    data.mkdir()
    monkeypatch.setenv("AETHER_DATA", str(data))
    popped = []
    opened = []
    monkeypatch.setattr("forge.launch.subprocess.Popen", lambda *a, **k: popped.append(a))
    monkeypatch.setattr("forge.launch.webbrowser.open", lambda url: opened.append(url))
    monkeypatch.setattr("forge.handoff.aether_status", lambda: {"ok": False, "status": 0, "body": {}})
    script = tmp_path / "launch-aether.ps1"
    script.write_text("# fake\n", encoding="utf-8")
    monkeypatch.setitem(__import__("forge.hosts", fromlist=["LINKS"]).LINKS, "aether_launch", str(script))
    result = launch("aether", url="https://example.org/page")
    assert result["ok"] is True
    assert popped
    assert opened == []
    assert result["url"] == "https://example.org/page"
    assert (data / "forge-handoff.json").is_file()
    assert result["launched"] is True


def test_aether_sibling_reads_named_handoff_file():
    aether = Path(r"C:\Users\jlay\Grok\aether\src\lib\forge-handoff.ts")
    assert aether.is_file()
    text = aether.read_text(encoding="utf-8")
    assert "forge-handoff.json" in text
    assert "LOCALAPPDATA" in text
    assert "Aether" in text
    route = Path(r"C:\Users\jlay\Grok\aether\src\app\api\forge-handoff\route.ts")
    assert route.is_file()


def test_launch_aether_skips_spawn_when_desk_is_up(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_DATA", str(tmp_path / "data"))
    data = tmp_path / "aether-data"
    data.mkdir()
    monkeypatch.setenv("AETHER_DATA", str(data))
    popped = []
    monkeypatch.setattr("forge.launch.subprocess.Popen", lambda *a, **k: popped.append(a))
    monkeypatch.setattr("forge.handoff.aether_status", lambda: {"ok": True, "status": 200, "body": {"app": "aether"}})
    monkeypatch.setattr(
        "forge.handoff.aether_browse",
        lambda url: {"ok": True, "status": 200, "title": "Page", "url": url, "error": None},
    )
    script = tmp_path / "launch-aether.ps1"
    script.write_text("# fake\n", encoding="utf-8")
    monkeypatch.setitem(__import__("forge.hosts", fromlist=["LINKS"]).LINKS, "aether_launch", str(script))
    result = launch("aether", url="https://example.org/page")
    assert popped == []
    assert result["launched"] is False
    assert result["browse"]["ok"] is True
