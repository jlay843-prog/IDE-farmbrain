from forge.serve import handle_api


def test_health():
    status, payload, ctype = handle_api("GET", "/api/health", {}, {})
    assert status == 200
    assert b"forge" in payload
    assert "json" in ctype


def test_desk_bootstrap():
    status, payload, _ = handle_api("GET", "/api/desk", {}, {})
    assert status == 200
    assert b"recipes" in payload
    assert b"links" in payload
