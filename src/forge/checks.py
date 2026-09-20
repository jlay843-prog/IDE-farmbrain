"""Canned farm status checks for Forge + local coder (qwen3-coder:30b).

Design for a low-reasoning model:
- Agent MUST run `forge check <name>` (or --json) and paste the board.
- Do NOT invent host health — only report lines from this module.
- Each check returns rigid PASS / FAIL / WARN lines + a one-line SUMMARY.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from forge.hosts import (
    BACKENDS,
    EVO,
    FARM_DIALS,
    FARM_FLEET,
    FARM_HEALTH,
    LINKS,
    ONTOLOGY_HEALTH,
    RAY_DASH,
    TOWER,
)
from forge.httputil import request_json
from forge.probe import farm_health, farm_json, probe_backend, status_snapshot

# Expected warm models (update when farm layout changes)
EXPECT_CUDA = "qwen3.8:27b-q4_K_M"
EXPECT_AMD_HARD = "empero-35b-a3b:q4km"
EXPECT_AMD_CODER = "qwen3-coder:30b"

APP_PROBES: list[tuple[str, str, str]] = [
    ("farm_dashboard", f"http://{EVO}:5000/health", "Farm Brain"),
    ("aria_ui", f"http://{EVO}:5173/", "ARIA UI"),
    ("aria_api", f"http://{EVO}:8788/health", "ARIA API"),
    ("aipm", f"http://{EVO}:5080/", "AI-PM"),
    ("ontology", ONTOLOGY_HEALTH, "Ontology"),
    ("lumen", f"http://{EVO}:8100/", "Lumen"),
    ("speaches", f"http://{EVO}:8090/", "Speaches TTS"),
    ("academy", f"http://{EVO}:3000/", "Academy"),
    ("ray_dash", f"{RAY_DASH}/", "Ray dashboard"),
    ("blender_mcp", f"http://{EVO}:9876/", "Blender MCP port"),
    ("tower_ollama", f"http://{TOWER}:11434/api/tags", "Tower Ollama"),
]


def _http_code(url: str, timeout: float = 3.0) -> tuple[int, str]:
    code, body = request_json(url, timeout=timeout, farm=True)
    err = ""
    if code != 200:
        if isinstance(body, dict):
            err = str(body.get("error") or body)[:80]
        else:
            err = str(body)[:80]
    return code, err


def _running_names(backend_id: str) -> list[str]:
    be = probe_backend(backend_id)
    return [str(r.get("name") or "") for r in (be.get("running") or []) if r.get("name")]


def _has_model(running: list[str], expect: str) -> bool:
    exp = expect.lower()
    for name in running:
        n = name.lower()
        if n == exp or n.startswith(exp) or exp.startswith(n.split(":")[0]):
            # prefer exact-ish: qwen3.8:27b-q4_K_M vs qwen3.8:27b
            if expect in name or name in expect or name.startswith(expect.split(":")[0]):
                if "qwen3.8" in exp:
                    return "qwen3.8" in n and "27b" in n
                if "empero" in exp:
                    return "empero" in n
                if "coder" in exp:
                    return "coder" in n and "30b" in n
                return True
    return False


def _line(ok: bool | None, label: str, detail: str) -> dict[str, str]:
    if ok is True:
        mark = "PASS"
    elif ok is False:
        mark = "FAIL"
    else:
        mark = "WARN"
    return {"mark": mark, "label": label, "detail": detail}


def _board(name: str, lines: list[dict[str, str]], *, note: str = "") -> dict[str, Any]:
    passes = sum(1 for L in lines if L["mark"] == "PASS")
    fails = sum(1 for L in lines if L["mark"] == "FAIL")
    warns = sum(1 for L in lines if L["mark"] == "WARN")
    if fails:
        result = "FAIL"
    elif warns:
        result = "WARN"
    else:
        result = "PASS"
    return {
        "check": name,
        "result": result,
        "passes": passes,
        "fails": fails,
        "warns": warns,
        "note": note,
        "lines": lines,
        "instruction_for_model": "Report these lines only. Do not invent hosts or change PASS/FAIL.",
    }


def check_farm() -> dict[str, Any]:
    """Farm Brain health + fleet reachability."""
    lines: list[dict[str, str]] = []
    health = farm_health()
    lines.append(
        _line(
            health.get("ok") is True,
            "dashboard",
            f"http={health.get('status')} url={FARM_HEALTH}",
        )
    )
    # Fleet probe can be slow with many SSH hosts — allow more time
    code, body = request_json(FARM_FLEET, timeout=12.0, farm=True)
    fleet_ok = code == 200 and isinstance(body, dict)
    if not fleet_ok:
        lines.append(_line(False, "fleet", f"http={code} err={str(body)[:80]}"))
        return _board("farm", lines)
    hosts = body.get("hosts") or body.get("items") or []
    if isinstance(hosts, dict):
        rows = list(hosts.values())
    else:
        rows = hosts if isinstance(hosts, list) else []
    online = int(body.get("online_count") or 0)
    total = int(body.get("total") or 0)
    down: list[str] = []
    if rows and (not total or not online):
        online = 0
        total = 0
        for h in rows:
            if not isinstance(h, dict):
                continue
            hid = str(h.get("id") or h.get("host") or "?")
            if h.get("online_expected") is False:
                continue
            total += 1
            ok = h.get("online") is True or h.get("ok") is True or str(h.get("status") or "").lower() in (
                "online",
                "up",
                "ok",
            )
            if ok:
                online += 1
            else:
                down.append(hid)
    elif rows:
        down = [
            str(h.get("id") or "?")
            for h in rows
            if isinstance(h, dict) and h.get("online") is not True and h.get("online_expected") is not False
        ]
    # Jetson/NAS often offline — WARN if only expected-optional hosts down
    optional = {"jetson", "nas", "bc250-02"}
    hard_down = [d for d in down if d not in optional]
    if hard_down:
        lines.append(_line(False, "fleet", f"{online}/{total} online down={','.join(hard_down)}"))
    elif down:
        lines.append(
            _line(None, "fleet", f"WARN {online}/{total} online optional_down={','.join(down)}")
        )
    else:
        lines.append(_line(True, "fleet", f"{online}/{total} online"))
    return _board("farm", lines)


def check_llm() -> dict[str, Any]:
    """Expected warm models: CUDA 3.8 + AMD Empero + coder."""
    lines: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = {k: pool.submit(probe_backend, k) for k in ("cuda", "amd", "burst")}
        backends = {k: f.result() for k, f in futs.items()}

    cuda = backends["cuda"]
    amd = backends["amd"]
    burst = backends["burst"]
    cuda_run = [r["name"] for r in (cuda.get("running") or [])]
    amd_run = [r["name"] for r in (amd.get("running") or [])]

    lines.append(_line(cuda.get("ok") is True, "cuda_ollama", f"{BACKENDS['cuda'].base} http_ok={cuda.get('ok')}"))
    lines.append(
        _line(
            _has_model(cuda_run, EXPECT_CUDA),
            "cuda_warm",
            f"expect={EXPECT_CUDA} loaded={','.join(cuda_run) or 'none'}",
        )
    )
    lines.append(_line(amd.get("ok") is True, "amd_ollama", f"{BACKENDS['amd'].base} http_ok={amd.get('ok')}"))
    lines.append(
        _line(
            _has_model(amd_run, EXPECT_AMD_HARD),
            "amd_empero",
            f"expect={EXPECT_AMD_HARD} loaded={','.join(amd_run) or 'none'}",
        )
    )
    lines.append(
        _line(
            _has_model(amd_run, EXPECT_AMD_CODER),
            "amd_coder",
            f"expect={EXPECT_AMD_CODER} loaded={','.join(amd_run) or 'none'}",
        )
    )
    # Empero must NOT be on CUDA
    if any("empero" in n.lower() for n in cuda_run):
        lines.append(_line(False, "empero_placement", "FAIL Empero is on CUDA — move to AMD :11437"))
    else:
        lines.append(_line(True, "empero_placement", "Empero not on CUDA (ok)"))

    snap = status_snapshot()
    vast = bool(snap.get("vast_active"))
    if vast:
        lines.append(_line(None, "tower_burst", "WARN Vast active — 5090 blocked"))
    else:
        lines.append(
            _line(
                burst.get("ok") is True,
                "tower_ollama",
                f"{BACKENDS['burst'].base} ok={burst.get('ok')}",
            )
        )
    return _board("llm", lines, note="CUDA=chat/AI-PM; AMD=Empero HARD + coder")


def check_apps() -> dict[str, Any]:
    """HTTP probes for LAN apps / tunnels (Meshnet uses same LAN IPs on farm)."""
    lines: list[dict[str, str]] = []

    def one(row: tuple[str, str, str]) -> dict[str, str]:
        key, url, label = row
        code, err = _http_code(url)
        # blender MCP is raw TCP — HTTP may fail even if port open; treat 200-499 as reach for non-health
        if key == "blender_mcp":
            # connection refused → fail; any HTTP response or timeout weirdness
            ok = code != 0 and code < 600
            # request_json often returns 0 on connection refused
            if code == 0:
                ok = False
            return _line(ok if code else False, key, f"{label} http={code} {err}".strip())
        ok = code == 200
        # some apps return 401 without key — still "up"
        if code in (401, 403) and key in ("aria_api", "aipm", "lumen"):
            return _line(True, key, f"{label} http={code} (auth — service up)")
        return _line(ok, key, f"{label} http={code} {err}".strip())

    with ThreadPoolExecutor(max_workers=8) as pool:
        lines = list(pool.map(one, APP_PROBES))
    return _board("apps", lines, note="LAN URLs; Meshnet clients use same .103 when on VPN")


def check_temps() -> dict[str, Any]:
    """Hardware / thermal from Farm Brain compute dials."""
    lines: list[dict[str, str]] = []
    dials = farm_json(FARM_DIALS)
    lines.append(_line(dials.get("ok") is True, "dials_api", f"http={dials.get('status')}"))
    body = dials.get("body") if isinstance(dials.get("body"), dict) else {}
    hosts = (body.get("hosts") or {}) if isinstance(body, dict) else {}
    # EVO / tower if present
    for key in ("evo", "coordinator", "tower"):
        node = hosts.get(key)
        if isinstance(node, dict):
            th = str(node.get("thermal") or node.get("temp_state") or "").lower() or "n/a"
            cpu = node.get("cpu_temp_c") or node.get("hot_temp_c") or node.get("temp_c")
            ok = th not in ("critical", "hot", "fail")
            if th == "n/a" and cpu is None:
                ok = None
            lines.append(_line(ok, f"temp_{key}", f"thermal={th} cpu_c={cpu}"))
    bc = hosts.get("bc250") or {}
    nodes = bc.get("nodes") if isinstance(bc, dict) else []
    if isinstance(nodes, list):
        for n in nodes:
            if not isinstance(n, dict):
                continue
            hid = str(n.get("id") or "?")
            th = str(n.get("thermal") or "").lower() or "n/a"
            cpu = n.get("cpu_temp_c") or n.get("hot_temp_c")
            ok = th not in ("critical",)
            if th in ("hot", "warn"):
                ok = None
            lines.append(_line(ok, f"temp_{hid}", f"thermal={th} cpu_c={cpu} ip={n.get('lan_ip')}"))
    if len(lines) == 1:
        lines.append(_line(None, "temps", "WARN no host thermal rows in dials"))
    return _board("temps", lines)


def check_vpn() -> dict[str, Any]:
    """Tunnel / Meshnet reachability via app HTTP (same checks as apps + farm)."""
    # On-farm, Meshnet and LAN share reachability to .103; this is the practical VPN test.
    farm = check_farm()
    apps = check_apps()
    lines = list(farm["lines"]) + list(apps["lines"])
    lines.insert(
        0,
        _line(
            True,
            "vpn_method",
            "Probe LAN apps on EVO .103 — Meshnet clients use same IPs when tunnel is up",
        ),
    )
    return _board("vpn", lines, note="If FAIL from off-farm, Meshnet/VPN is down or host offline")


def check_all() -> dict[str, Any]:
    parts = [check_farm(), check_llm(), check_temps(), check_apps()]
    lines: list[dict[str, str]] = []
    for part in parts:
        lines.append(_line(None, f"---{part['check']}---", part["result"]))
        lines.extend(part["lines"])
    board = _board("all", lines, note="Combined farm+llm+temps+apps")
    # overall: fail if any subcheck failed
    if any(p["result"] == "FAIL" for p in parts):
        board["result"] = "FAIL"
    elif any(p["result"] == "WARN" for p in parts):
        board["result"] = "WARN"
    else:
        board["result"] = "PASS"
    board["parts"] = {p["check"]: p["result"] for p in parts}
    return board


CHECKS: dict[str, Callable[[], dict[str, Any]]] = {
    "farm": check_farm,
    "llm": check_llm,
    "temps": check_temps,
    "hw": check_temps,
    "apps": check_apps,
    "vpn": check_vpn,
    "tunnels": check_vpn,
    "all": check_all,
    "status": check_all,
}


def list_checks() -> list[dict[str, str]]:
    return [
        {"id": "farm", "help": "Farm Brain /health + fleet online count"},
        {"id": "llm", "help": "CUDA qwen3.8 + AMD Empero + coder warm; Empero not on CUDA"},
        {"id": "temps", "help": "Dials thermal / CPU temps (BC-250 + hosts)"},
        {"id": "apps", "help": "HTTP probes: dashboard, ARIA, AI-PM, ontology, Ray, Blender, tower"},
        {"id": "vpn", "help": "Same as apps+farm — use off-farm to verify Meshnet tunnels"},
        {"id": "all", "help": "farm + llm + temps + apps"},
    ]


def run_check(name: str) -> dict[str, Any]:
    key = (name or "").strip().lower()
    if key in ("list", "help", ""):
        return {
            "check": "list",
            "result": "PASS",
            "checks": list_checks(),
            "instruction_for_model": "Pick one id and run: forge check <id>",
        }
    fn = CHECKS.get(key)
    if not fn:
        return {
            "check": key,
            "result": "FAIL",
            "lines": [_line(False, "unknown", f"unknown check {key!r}; try forge check list")],
            "instruction_for_model": "Run forge check list and pick a valid id.",
        }
    return fn()


def format_board(board: dict[str, Any]) -> str:
    """Plain text board for 30b / human — no prose required."""
    if board.get("check") == "list":
        rows = ["CHECK: list", "RESULT: PASS", "LINES:"]
        for c in board.get("checks") or []:
            rows.append(f"- {c['id']:8} {c['help']}")
        rows.append("SUMMARY: run  forge check <id>  or  forge check all")
        return "\n".join(rows)
    rows = [
        f"CHECK: {board.get('check')}",
        f"RESULT: {board.get('result')}",
        "LINES:",
    ]
    for L in board.get("lines") or []:
        rows.append(f"- {L['mark']:4} {L['label']}: {L['detail']}")
    if board.get("note"):
        rows.append(f"NOTE: {board['note']}")
    rows.append(
        f"SUMMARY: {board.get('passes', 0)} pass, {board.get('fails', 0)} fail, {board.get('warns', 0)} warn"
    )
    rows.append("INSTRUCTION: Report these lines only. Do not invent status.")
    return "\n".join(rows)
