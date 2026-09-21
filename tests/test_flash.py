from forge.flash import FLASH_MODEL, probe_flash_models, probe_flash_tag


def test_probe_flash_models_returns_tuple():
    ok, ids, via = probe_flash_models()
    assert isinstance(ok, bool)
    assert isinstance(ids, list)
    assert via in {"direct", "evo-ssh"}


def test_probe_flash_tag_matches_expected_name_or_none():
    tag = probe_flash_tag()
    if tag is not None:
        assert FLASH_MODEL in tag
