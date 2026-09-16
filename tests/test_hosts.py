from forge.hosts import LINKS, RAY_DASH, TIERS, backend_for_tier
from forge.probe import is_loaded, vast_active


def test_mesh_deep_links_are_siblings_not_new_surfaces():
    assert LINKS["ontology"].endswith(":8000/docs")
    assert LINKS["ray"] == RAY_DASH
    assert LINKS["farm_compute"].endswith("#compute")


def test_code_stays_on_amd():
    be = backend_for_tier("code")
    assert be.id == "amd"
    assert ":11437" in be.base
    assert "coder" in be.default_model
    assert set(TIERS) == {"code", "chat", "burst"}


def test_vast_active_shapes():
    assert vast_active({"body": {"modes": {"vast_active": True}}}) is True
    assert vast_active({"body": {"tower": {"vast_active": True}}}) is True
    assert vast_active({"body": {"ok": True}}) is False


def test_loaded_matches_quant_suffix_not_other_family():
    running = {"qwen3.8:27b-q4_K_M"}
    assert is_loaded("qwen3.8:27b", running) is True
    assert is_loaded("qwen3.8:27b-q4_K_M", running) is True
    assert is_loaded("nomic-embed-text:latest", running) is False
