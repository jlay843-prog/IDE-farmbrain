"""Canned farm status checks for Forge + local coder (qwen3-coder:30b).

Design for a low-reasoning model:
- Agent MUST run `forge check <name>` (or --json) and paste the board.
- Do NOT invent host health — only report lines from this module.
- Each check returns rigid PASS / FAIL / WARN lines + a one-line SUMMARY.
"""

from __future__ import annotations

import os
import socket
import subprocess
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from forge.hosts import (
    BACKENDS,
    EVO,
    FARM_COMPUTE,
    FARM_DIALS,
    FARM_FLEET,
    FARM_HEALTH,
    ONTOLOGY_HEALTH,
    RAY_DASH,
    RAY_JOBS,
    TOWER,
)
from forge.httputil import farm_token, request_json
from forge.probe import farm_health, farm_json, probe_backend, ray_jobs_snapshot, status_snapshot

# Expected warm models (update when farm layout changes)
EXPECT_CUDA = "qwen3.8:27b-q4_K_M"
EXPECT_AMD_HARD = "empero-35b-a3b:q4km"
EXPECT_AMD_CODER = "qwen3-coder:30b"

# kind: json = API (Accept application/json); html = web UI (Accept */*); tcp = raw port
APP_PROBES: list[tuple[str, str, str, str]] = [
    ("farm_dashboard", f"http://{EVO}:5000/health", "Farm Brain", "json"),
    ("aria_ui", f"http://{EVO}:5173/", "ARIA UI", "html"),
    ("aria_api", f"http://{EVO}:8788/health", "ARIA API", "json"),
    ("aipm", f"http://{EVO}:5080/", "AI-PM", "html"),
    ("ontology", ONTOLOGY_HEALTH, "Ontology", "json"),
    ("lumen", f"http://{EVO}:8100/", "Lumen", "html"),
    ("speaches", f"http://{EVO}:8090/", "Speaches TTS", "html"),
    ("academy", f"http://{EVO}:3000/", "Academy", "html"),
    ("ray_dash", f"{RAY_DASH}/", "Ray dashboard", "html"),
    ("blender_mcp", f"{EVO}:9876", "Blender MCP TCP", "tcp"),
    ("tower_ollama", f"http://{TOWER}:11434/api/tags", "Tower Ollama", "json"),
]


def _http_code(url: str, *, kind: str = "json", timeout: float = 3.0) -> tuple[int, str]:
    """Probe HTTP. html pages must not send Accept: application/json (Vite returns 404)."""
    if kind == "json":
        code, body = request_json(url, timeout=timeout, farm=True)
        err = ""
        if code != 200:
            if isinstance(body, dict):
                err = str(body.get("error") or body)[:80]
            else:
                err = str(body)[:80]
        return code, err

    headers = {"Accept": "*/*", "User-Agent": "forge-check/1.0"}
    token = farm_token()
    if token and EVO in url:
        headers["X-Farm-Local-Key"] = token
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, ""
    except urllib.error.HTTPError as exc:
        # 401/403 still means the service answered
        return exc.code, str(exc.reason)[:60]
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)[:80]


def _tcp_open(host_port: str, timeout: float = 2.0) -> tuple[bool, str]:
    """Blender MCP listens as raw TCP on :9876 — not HTTP."""
    host, _, port_s = host_port.partition(":")
    try:
        port = int(port_s or "0")
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"tcp {host}:{port} open"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:80]


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
    """HTTP/TCP probes for LAN apps / tunnels (Meshnet uses same LAN IPs on farm)."""

    def one(row: tuple[str, str, str, str]) -> dict[str, str]:
        key, url, label, kind = row
        if kind == "tcp":
            ok, detail = _tcp_open(url)
            return _line(ok, key, f"{label} {detail}")
        code, err = _http_code(url, kind=kind)
        if code in (401, 403) and key in ("aria_api", "aipm", "lumen"):
            return _line(True, key, f"{label} http={code} (auth — service up)")
        ok = code == 200
        return _line(ok, key, f"{label} http={code} {err}".strip())

    with ThreadPoolExecutor(max_workers=8) as pool:
        lines = list(pool.map(one, APP_PROBES))
    return _board(
        "apps",
        lines,
        note="ARIA UI needs Accept:*/*, Blender MCP is TCP :9876 not HTTP",
    )


def _ssh_key() -> str:
    return str(
        Path(os.environ.get("FORGE_SSH_KEY", ""))
        if os.environ.get("FORGE_SSH_KEY")
        else Path.home() / ".ssh" / "id_ed25519_farm"
    )


def _ssh_run(host: str, remote: str, timeout: float = 8.0) -> tuple[bool, str]:
    key = _ssh_key()
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-i",
        key,
        f"jeff@{host}",
        remote,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        out = (proc.stdout or "").strip() or (proc.stderr or "").strip()
        return proc.returncode == 0, out[:400]
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:120]


def _parse_nvidia_smi(csv_line: str) -> dict[str, Any]:
    # name, temp, util%, mem_used MiB, mem_total MiB
    parts = [p.strip() for p in csv_line.split(",")]
    if len(parts) < 5:
        return {}
    name, temp_s, util_s, used_s, total_s = parts[:5]
    def num(s: str) -> float | None:
        try:
            return float(s.replace("%", "").replace("MiB", "").strip())
        except ValueError:
            return None
    return {
        "name": name,
        "temp_c": num(temp_s),
        "gpu_pct": num(util_s),
        "vram_used_mb": num(used_s),
        "vram_total_mb": num(total_s),
    }


def _live_gpu(host: str) -> dict[str, Any]:
    ok, out = _ssh_run(
        host,
        "nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total --format=csv,noheader",
    )
    if not ok or not out:
        return {"ok": False, "error": out or "ssh/nvidia-smi failed"}
    # first GPU line only
    line = out.splitlines()[0]
    parsed = _parse_nvidia_smi(line)
    parsed["ok"] = bool(parsed.get("temp_c") is not None)
    parsed["raw"] = line
    return parsed


def _live_cpu_temp_c(host: str) -> dict[str, Any]:
    """Best-effort CPU package temp via hwmon (millidegrees)."""
    ok, out = _ssh_run(
        host,
        "python3 -c \"import pathlib; vals=[];\n"
        "root=pathlib.Path('/sys/class/hwmon');\n"
        "[vals.extend([int(p.read_text())/1000 for p in d.glob('temp*_input')]) for d in root.iterdir() if d.is_dir()];\n"
        "print(max(vals) if vals else '')\"",
    )
    if not ok:
        return {"ok": False, "error": out[:80]}
    try:
        temp = float(out.strip()) if out.strip() else None
    except ValueError:
        temp = None
    return {"ok": temp is not None, "temp_c": temp}


def _temp_ok(temp_c: float | None, *, warn_c: float = 80.0, fail_c: float = 90.0) -> bool | None:
    if temp_c is None:
        return None
    if temp_c >= fail_c:
        return False
    if temp_c >= warn_c:
        return None
    return True


def _tower_5090_mark(
    t_temp: float | None,
    tower_gpu: dict[str, Any],
    *,
    vast_active: bool,
) -> bool | None:
    """Tower 5090 idle or blocked-for-Vast → WARN, not FAIL."""
    if vast_active:
        return None
    if not tower_gpu.get("ok") and t_temp is None:
        return None
    return _temp_ok(t_temp)


def check_temps() -> dict[str, Any]:
    """EVO 5070 Ti, tower 5950X + 5090, BC-250 dials — live nvidia-smi when dials thin."""
    lines: list[dict[str, str]] = []
    dials = farm_json(FARM_DIALS)
    lines.append(_line(dials.get("ok") is True, "dials_api", f"http={dials.get('status')}"))
    body = dials.get("body") if isinstance(dials.get("body"), dict) else {}
    hosts = (body.get("hosts") or {}) if isinstance(body, dict) else {}

    evo = hosts.get("evo") if isinstance(hosts.get("evo"), dict) else {}
    tower = hosts.get("tower") if isinstance(hosts.get("tower"), dict) else {}

    # Parallel live probes (LAN IPs — Mesh timed out on tower earlier)
    with ThreadPoolExecutor(max_workers=4) as pool:
        evo_gpu_f = pool.submit(_live_gpu, EVO)
        tower_gpu_f = pool.submit(_live_gpu, TOWER)
        evo_cpu_f = pool.submit(_live_cpu_temp_c, EVO)
        tower_cpu_f = pool.submit(_live_cpu_temp_c, TOWER)
        evo_gpu = evo_gpu_f.result()
        tower_gpu = tower_gpu_f.result()
        evo_cpu = evo_cpu_f.result()
        tower_cpu = tower_cpu_f.result()

    # --- EVO + 5070 Ti ---
    evo_temp = evo_gpu.get("temp_c")
    if evo_temp is None and evo.get("temp_c") is not None:
        try:
            evo_temp = float(evo.get("temp_c"))
        except (TypeError, ValueError):
            evo_temp = None
    evo_name = evo_gpu.get("name") or evo.get("gpu_name") or "RTX 5070 Ti"
    evo_vram = ""
    if evo_gpu.get("vram_used_mb") is not None and evo_gpu.get("vram_total_mb"):
        evo_vram = f" vram={evo_gpu['vram_used_mb']:.0f}/{evo_gpu['vram_total_mb']:.0f}MiB"
    elif evo.get("vram_used_gb") is not None:
        evo_vram = f" vram={evo.get('vram_used_gb')}/{evo.get('vram_total_gb')}GiB"
    lines.append(
        _line(
            _temp_ok(evo_temp),
            "evo_5070ti",
            f"{evo_name} temp_c={evo_temp} util%={evo_gpu.get('gpu_pct') if evo_gpu.get('gpu_pct') is not None else evo.get('gpu_pct')}{evo_vram}",
        )
    )
    lines.append(
        _line(
            _temp_ok(evo_cpu.get("temp_c"), warn_c=85.0, fail_c=95.0),
            "evo_cpu",
            f"Strix Halo / EVO CPU package temp_c={evo_cpu.get('temp_c')} load={evo.get('loadavg')}",
        )
    )
    lines.append(
        _line(
            evo.get("online") is True if evo else True,
            "evo_host",
            f"mem%={evo.get('mem_pct')} cpu%={evo.get('cpu_pct')} online={evo.get('online')}",
        )
    )

    # --- Tower 5090 + 5950X ---
    t_temp = tower_gpu.get("temp_c")
    if t_temp is None and tower.get("temp_c") is not None:
        try:
            t_temp = float(tower.get("temp_c"))
        except (TypeError, ValueError):
            t_temp = None
    t_name = tower_gpu.get("name") or tower.get("gpu_name") or "RTX 5090"
    t_vram = ""
    if tower_gpu.get("vram_used_mb") is not None and tower_gpu.get("vram_total_mb"):
        t_vram = f" vram={tower_gpu['vram_used_mb']:.0f}/{tower_gpu['vram_total_mb']:.0f}MiB"
    snap = status_snapshot()
    vast = tower.get("vast_active")
    if vast is None:
        vast = bool(snap.get("vast_active"))
    else:
        vast = bool(vast)
    lines.append(
        _line(
            _tower_5090_mark(t_temp, tower_gpu, vast_active=vast),
            "tower_5090",
            f"{t_name} temp_c={t_temp} util%={tower_gpu.get('gpu_pct')}{t_vram} vast={vast}",
        )
    )
    lines.append(
        _line(
            _temp_ok(tower_cpu.get("temp_c"), warn_c=85.0, fail_c=95.0),
            "tower_5950x",
            f"AMD Ryzen 9 5950X package temp_c={tower_cpu.get('temp_c')} (hwmon max)",
        )
    )
    if not tower_gpu.get("ok") and not t_temp:
        lines.append(
            _line(
                None,
                "tower_probe",
                f"WARN live nvidia-smi thin; dials_err={str(tower.get('error') or '')[:60]}",
            )
        )

    # --- BC-250 array from dials ---
    bc = hosts.get("bc250") or {}
    nodes = bc.get("nodes") if isinstance(bc, dict) else []
    if isinstance(nodes, list):
        for n in nodes:
            if not isinstance(n, dict):
                continue
            hid = str(n.get("id") or "?")
            th = str(n.get("thermal") or "").lower() or "n/a"
            cpu = n.get("cpu_temp_c") or n.get("hot_temp_c") or n.get("temp_c")
            ok = th not in ("critical",)
            if th in ("hot", "warn"):
                ok = None
            lines.append(
                _line(
                    ok,
                    f"temp_{hid}",
                    f"thermal={th} cpu_c={cpu} board_c={n.get('board_temp_c')} ip={n.get('lan_ip')}",
                )
            )

    if len(lines) <= 1:
        lines.append(_line(None, "temps", "WARN no thermal rows"))
    return _board(
        "temps",
        lines,
        note="EVO 5070 Ti + CPU; tower 5090 + 5950X via LAN SSH nvidia-smi/hwmon; BC-250 from dials",
    )


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


def check_ray() -> dict[str, Any]:
    """Ray head on EVO: GCS :6379, dashboard :8265, jobs API, compute modes."""
    lines: list[dict[str, str]] = []

    gcs_ok, gcs_detail = _tcp_open(f"{EVO}:6379", timeout=2.5)
    lines.append(_line(gcs_ok, "ray_gcs", f"GCS {gcs_detail}"))

    dash_code, _ = request_json(RAY_DASH, timeout=3.0)
    lines.append(_line(dash_code == 200, "ray_dashboard", f"{RAY_DASH} http={dash_code}"))

    jobs_code, jobs_body = request_json(RAY_JOBS, timeout=4.0)
    lines.append(_line(jobs_code == 200, "ray_jobs_api", f"{RAY_JOBS} http={jobs_code}"))

    compute = farm_json(FARM_COMPUTE)
    dials = farm_json(FARM_DIALS)
    modes: dict[str, Any] = {}
    for blob in (compute.get("body"), dials.get("body")):
        if isinstance(blob, dict):
            m = blob.get("modes") or blob.get("last_modes") or {}
            if isinstance(m, dict) and m:
                modes = m
                break

    snap = ray_jobs_snapshot(modes)
    head_ok = bool(snap.get("head_ok") or (gcs_ok and dash_code == 200))
    lines.append(
        _line(
            head_ok,
            "ray_head",
            f"head_ok={snap.get('head_ok')} gcs={gcs_ok} dash={dash_code == 200}",
        )
    )
    lines.append(
        _line(
            bool(modes.get("ray_head_ok")) if "ray_head_ok" in modes else head_ok,
            "ray_mode_head",
            f"compute_modes.ray_head_ok={modes.get('ray_head_ok')}",
        )
    )
    bc = modes.get("ray_bc250_present")
    if bc is None:
        lines.append(_line(None, "ray_bc250_workers", "WARN modes.ray_bc250_present missing"))
    else:
        lines.append(
            _line(
                True if bc else None,
                "ray_bc250_workers",
                f"ray_bc250_present={bc} (WARN if false — head can still be ok)",
            )
        )
    hp = modes.get("ray_highperf_present")
    lines.append(
        _line(
            None if hp is False else (True if hp else None),
            "ray_highperf",
            f"ray_highperf_present={hp} (tower worker; often false)",
        )
    )

    jobs = snap.get("jobs") or []
    running = int(snap.get("running") or 0)
    job_count = int(snap.get("job_count") or 0)
    lines.append(
        _line(
            True,
            "ray_jobs",
            f"listed={len(jobs)} running_or_pending={running} total≈{job_count}",
        )
    )
    for j in jobs[:3]:
        st = str(j.get("status") or "?")
        lines.append(
            _line(
                None if st.upper() not in {"FAILED", "ERROR"} else False,
                f"job_{str(j.get('id') or '')[:10]}",
                f"{st} {j.get('name')}",
            )
        )

    note = "Ray head = EVO GCS :6379 + dashboard :8265 (num-gpus=0; 5070 Ti left for Ollama)"
    return _board("ray", lines, note=note)


def check_all() -> dict[str, Any]:
    parts = [check_farm(), check_llm(), check_temps(), check_apps(), check_ray()]
    lines: list[dict[str, str]] = []
    for part in parts:
        lines.append(_line(None, f"---{part['check']}---", part["result"]))
        lines.extend(part["lines"])
    board = _board("all", lines, note="Combined farm+llm+temps+apps+ray")
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
    "ray": check_ray,
    "all": check_all,
    "status": check_all,
}


def list_checks() -> list[dict[str, str]]:
    return [
        {"id": "farm", "help": "Farm Brain /health + fleet online count"},
        {"id": "llm", "help": "CUDA qwen3.8 + AMD Empero + coder warm; Empero not on CUDA"},
        {"id": "temps", "help": "EVO 5070 Ti + CPU, tower 5090 + 5950X, BC-250 dials"},
        {"id": "apps", "help": "HTTP probes: dashboard, ARIA, AI-PM, ontology, Ray UI, Blender, tower"},
        {"id": "vpn", "help": "Same as apps+farm — use off-farm to verify Meshnet tunnels"},
        {"id": "ray", "help": "Ray head GCS :6379 + dashboard + jobs API + worker modes"},
        {"id": "all", "help": "farm + llm + temps + apps + ray"},
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
