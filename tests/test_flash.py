import base64
import json
import subprocess

from forge.flash import (
    FLASH_MODEL,
    _FLASH_SSH_STREAM_PY,
    probe_flash_models,
    probe_flash_tag,
    remote_python3_cmd,
)


def test_probe_flash_models_returns_tuple():
    ok, ids, via = probe_flash_models()
    assert isinstance(ok, bool)
    assert isinstance(ids, list)
    assert via in {"direct", "evo-ssh"}


def test_probe_flash_tag_matches_expected_name_or_none():
    tag = probe_flash_tag()
    if tag is not None:
        assert FLASH_MODEL in tag


def test_legacy_oneliner_grows_past_windows_cmd_limit():
    """Reproduce Jeff's split: Plan JSON base64 in python3 -c exceeds cmd 8191."""
    prompt = "PROMPT:\n" + ("x" * 4000) + "\n\nRECENT CHAT:\n" + "\n".join(f"USER: {'y' * 800}" for _ in range(6))
    payload = {
        "model": "qwen3.8-flash-next",
        "messages": [
            {"role": "system", "content": "You are the Forge planning model on the tower 5090 flash slot. " * 4},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 1800,
        "stream": True,
    }
    blob = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    remote = (
        "python3 -c "
        "'import json,base64,urllib.request,sys; "
        f"p=json.loads(base64.b64decode(\"{blob}\").decode()); "
        "print(p)'"
    )
    cmdline = subprocess.list2cmdline(["ssh", "-o", "BatchMode=yes", "jeff@192.168.68.103", remote])
    assert 'b64decode("' in remote
    assert len(blob) > 8000
    assert len(cmdline) > 8191


def test_evo_ssh_remote_stays_small_when_plan_prompt_is_large():
    prompt = "PLAN-PROMPT-" + ("x" * 8000)
    remote = remote_python3_cmd(_FLASH_SSH_STREAM_PY, "120")
    cmdline = subprocess.list2cmdline(
        ["ssh", "-o", "BatchMode=yes", "-i", "id_ed25519_farm", "jeff@192.168.68.103", remote]
    )
    assert prompt not in remote
    assert prompt not in cmdline
    assert json.dumps({"content": prompt}) not in remote
    assert len(cmdline) < 4000
    assert "json.load(sys.stdin)" in _FLASH_SSH_STREAM_PY
    assert "11435/v1/chat/completions" in _FLASH_SSH_STREAM_PY
