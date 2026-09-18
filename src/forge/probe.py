"""Live inventory: Ollama tags/ps + Farm Brain health/fleet/dials."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from forge.hosts import (
    BACKENDS,
    FARM_COMPUTE,
    FARM_DIALS,
    FARM_FLEET,
    FARM_HEALTH,
    ONTOLOGY,
    ONTOLOGY_AGENTS,
    ONTOLOGY_HEALTH,
    RAY_DASH,
    RAY_JOBS,
    backend_for_tier,
)
from forge.httputil import request_json

MESH_PULSE_MS = 20000


def is_loaded(name: str, running: set[str]) -> bool:
    if not name:
        return False
    for row in running:
        if not row:
            continue
        if row == name or row.startswith(name) or name.startswith(row):
            return True
    return False


def _ollama(base: str, path: str, timeout: float = 3.0) -> tuple[int, Any]:
    return request_json(f"{base}{path}", timeout=timeout)


def probe_backend(backend_id: str) -> dict[str, Any]:
    be = BACKENDS[backend_id]
    tags_status, tags = _ollama(be.base, "/api/tags")
    ps_status, ps = _ollama(be.base, "/api/ps")
    models = []
    if isinstance(tags, dict):
        for row in tags.get("models") or []:
            name = row.get("name") or row.get("model") or ""
            models.append(
                {
                    "name": name,
                    "size": row.get("size"),
                    "digest": (row.get("digest") or "")[:12],
                }
            )
    running = []
    if isinstance(ps, dict):
        for row in ps.get("models") or []:
            running.append(
                {
                    "name": row.get("name") or row.get("model") or "",
                    "size_vram": row.get("size_vram") or row.get("size"),
                    "expires_at": row.get("expires_at"),
                }
            )
    ok = tags_status == 200
    return {
        **be.as_dict(),
        "ok": ok,
        "status": tags_status,
        "error": None if ok else (tags.get("error") if isinstance(tags, dict) else str(tags)),
        "models": models,
        "running": running,
    }


def farm_health() -> dict[str, Any]:
    code, body = request_json(FARM_HEALTH, timeout=3.0, farm=True)
    return {"ok": code == 200, "status": code, "body": body, "url": FARM_HEALTH}


def farm_json(url: str) -> dict[str, Any]:
    code, body = request_json(url, timeout=4.0, farm=True)
    return {"ok": code == 200, "status": code, "body": body, "url": url}


def vast_active(compute: dict[str, Any] | None = None, dials: dict[str, Any] | None = None) -> bool:
    for blob in (compute, dials):
        if not isinstance(blob, dict):
            continue
        body = blob.get("body") if "body" in blob else blob
        if not isinstance(body, dict):
            continue
        if body.get("vast_active") is True:
            return True
        modes = body.get("modes")
        if isinstance(modes, dict) and modes.get("vast_active") is True:
            return True
        tower = body.get("tower") or body.get("twr") or {}
        if isinstance(tower, dict) and tower.get("vast_active") is True:
            return True
        hosts = body.get("hosts")
        if isinstance(hosts, dict):
            tw = hosts.get("tower") or {}
            if isinstance(tw, dict) and tw.get("vast_active") is True:
                return True
    return False


def _unwrap(blob: Any) -> dict[str, Any]:
    if not isinstance(blob, dict):
        return {}
    body = blob.get("body") if "body" in blob and isinstance(blob.get("body"), dict) else blob
    return body if isinstance(body, dict) else {}


def _modes(snap: dict[str, Any]) -> dict[str, Any]:
    for key in ("dials", "compute"):
        body = _unwrap(snap.get(key))
        modes = body.get("modes") or body.get("last_modes") or {}
        if isinstance(modes, dict) and modes:
            return modes
    return {}


def farm_hosts_from_dials(dials: dict[str, Any] | None) -> list[dict[str, Any]]:
    """BC-250 cards from live Farm Brain dials. Never invent hosts."""
    body = _unwrap(dials)
    rack = ((body.get("hosts") or {}).get("bc250") or {})
    gpu = str(rack.get("gpu_name") or "GFX1013")
    rows: list[dict[str, Any]] = []
    for n in rack.get("nodes") or []:
        if not isinstance(n, dict):
            continue
        hid = str(n.get("id") or "").strip()
        if not hid.startswith("bc250-"):
            continue
        ip = str(n.get("lan_ip") or "").strip()
        model = str(n.get("model") or n.get("model_short") or "").strip()
        installed = n.get("models_installed") or []
        names: list[str] = []
        for raw in ([model] if model else []) + list(installed):
            name = str(raw or "").strip()
            if name and name not in names:
                names.append(name)
        models = [{"name": name} for name in names]
        running = [{"name": model}] if model and n.get("model_warm") else []
        suffix = hid.split("-")[-1]
        rows.append(
            {
                "id": hid,
                "kind": "bc250",
                "label": f"BC-250 {suffix}",
                "detail": n.get("label") or hid,
                "gpu": n.get("gpu_name") or gpu,
                "host_id": hid,
                "role": "farm",
                "base": f"http://{ip}:11434" if ip else "",
                "lan_ip": ip,
                "ok": bool(n.get("online") or n.get("ok") or n.get("ollama") or n.get("ollama_ok")),
                "models": models,
                "running": running,
                "blocked": False,
                "pulse": bool(n.get("online") or n.get("ok") or n.get("ollama") or n.get("ollama_ok")),
                "ray": bool(n.get("ray")),
                "ollama": bool(n.get("ollama") or n.get("ollama_ok")),
                "posture": n.get("posture") or "",
                "thermal": n.get("thermal") or "",
            }
        )
    rows.sort(key=lambda r: r["id"])
    return rows


def compact_ray_jobs(payload: Any, *, limit: int = 3) -> list[dict[str, Any]]:
    rows: list[Any] = []
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        inner = data.get("result") if isinstance(data, dict) else None
        if isinstance(inner, dict) and isinstance(inner.get("result"), list):
            rows = inner["result"]
        elif isinstance(inner, list):
            rows = inner
        elif isinstance(payload.get("result"), list):
            rows = payload["result"]
    out: list[dict[str, Any]] = []
    for job in rows[:limit]:
        if not isinstance(job, dict):
            continue
        entry = str(job.get("entrypoint") or "")
        name = _ray_job_name(entry)
        out.append(
            {
                "id": str(job.get("job_id") or job.get("submission_id") or ""),
                "status": str(job.get("status") or "UNKNOWN"),
                "name": name,
            }
        )
    return out


def _ray_job_name(entry: str) -> str:
    text = (entry or "").strip()
    low = text.lower()
    if "embed_ping" in low or "bc250_gpu" in low:
        return "bc250 embed ping"
    if "ray_bc250_overnight_smoke" in low:
        return "bc250 overnight smoke"
    first = text.splitlines()[0] if text else ""
    leaf = first.replace("\\", "/").rstrip("/").split("/")[-1]
    return (leaf or "ray job")[:72]


def ray_from_payloads(
    *,
    jobs_body: Any = None,
    jobs_ok: bool = False,
    dash_ok: bool = False,
    modes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    modes = modes or {}
    jobs = compact_ray_jobs(jobs_body)
    running = sum(1 for j in jobs if str(j.get("status") or "").upper() in {"RUNNING", "PENDING"})
    total = len(jobs)
    if isinstance(jobs_body, dict):
        data = jobs_body.get("data") if isinstance(jobs_body.get("data"), dict) else jobs_body
        inner = data.get("result") if isinstance(data, dict) else None
        if isinstance(inner, dict) and inner.get("total") is not None:
            total = int(inner["total"])
        elif isinstance(inner, list):
            total = len(inner)
    return {
        "ok": bool(jobs_ok or dash_ok or modes.get("ray_head_ok")),
        "dash_ok": bool(dash_ok),
        "head_ok": bool(modes.get("ray_head_ok") or jobs_ok or dash_ok),
        "bc250_present": bool(modes.get("ray_bc250_present")),
        "highperf_present": bool(modes.get("ray_highperf_present")),
        "head": "192.168.68.103:6379",
        "dashboard": RAY_DASH,
        "jobs": jobs,
        "running": running,
        "job_count": total,
        "surface": "ray_dashboard",
        "note": (
            "Ray is Farm-Ontology compute on EVO, not an ontology entity graph. "
            "Open the Ray Dashboard for jobs; Farm Brain Compute for per-board badges."
        ),
    }


def ontology_from_payloads(health: Any = None, agents: Any = None) -> dict[str, Any]:
    health = health if isinstance(health, dict) else {}
    rows = agents if isinstance(agents, list) else []
    handles = [
        {
            "id": str(a.get("id") or ""),
            "name": str(a.get("name") or a.get("agent_class") or ""),
            "handle": a.get("ray_actor_handle"),
        }
        for a in rows
        if isinstance(a, dict) and a.get("ray_actor_handle")
    ]
    ok = str(health.get("status") or "") == "ok" or bool(health.get("configured"))
    return {
        "ok": ok,
        "url": ONTOLOGY,
        "docs": f"{ONTOLOGY}/docs",
        "entities": health.get("total_entities"),
        "schema_version": health.get("schema_version"),
        "store_backend": health.get("store_backend"),
        "agent_count": len(rows) if rows else None,
        "ray_actors": len(handles),
        "ray_handles": handles[:8],
        "note": (
            "Ontology is the SQLite world model. Agent records can name a Ray actor, "
            "but live jobs live on the Ray Dashboard — not cloned here."
        ),
    }


def ray_jobs_snapshot(modes: dict[str, Any] | None = None) -> dict[str, Any]:
    dash_code, _dash = request_json(RAY_DASH, timeout=2.5)
    jobs_code, jobs_body = request_json(RAY_JOBS, timeout=3.5)
    return ray_from_payloads(
        jobs_body=jobs_body,
        jobs_ok=jobs_code == 200,
        dash_ok=dash_code == 200,
        modes=modes,
    )


def ontology_snapshot() -> dict[str, Any]:
    health_code, health = request_json(ONTOLOGY_HEALTH, timeout=3.0)
    agents_code, agents = request_json(ONTOLOGY_AGENTS, timeout=3.0)
    snap = ontology_from_payloads(health if health_code == 200 else {}, agents if agents_code == 200 else [])
    if health_code != 200:
        snap["ok"] = False
        snap["error"] = health.get("error") if isinstance(health, dict) else str(health)
    return snap


_CACHE: dict[str, Any] = {"at": 0.0, "data": None}
_CACHE_TTL = 4.0


def status_snapshot(*, refresh: bool = False) -> dict[str, Any]:
    now = time.time()
    if not refresh and _CACHE["data"] is not None and now - _CACHE["at"] < _CACHE_TTL:
        return _CACHE["data"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        be_futs = {key: pool.submit(probe_backend, key) for key in BACKENDS}
        health_f = pool.submit(farm_health)
        fleet_f = pool.submit(farm_json, FARM_FLEET)
        dials_f = pool.submit(farm_json, FARM_DIALS)
        compute_f = pool.submit(farm_json, FARM_COMPUTE)
        backends = {key: fut.result() for key, fut in be_futs.items()}
        health = health_f.result()
        fleet = fleet_f.result()
        dials = dials_f.result()
        compute = compute_f.result()
    vast = vast_active(compute, dials)
    data = {
        "name": "forge",
        "farm": health,
        "fleet": fleet,
        "dials": dials,
        "compute": compute,
        "vast_active": vast,
        "backends": backends,
        "ok": health["ok"] and backends["amd"]["ok"],
    }
    _CACHE["at"] = now
    _CACHE["data"] = data
    return data


def probe_farm_host(node: dict[str, Any]) -> dict[str, Any]:
    """Live /api/tags + /api/ps for one BC-250 dial row. Falls back to dial inventory."""
    base = str(node.get("base") or "").strip()
    if not base:
        return {**node, "ok": False, "models": node.get("models") or [], "running": node.get("running") or []}
    tags_status, tags = _ollama(base, "/api/tags", timeout=2.5)
    _ps_status, ps = _ollama(base, "/api/ps", timeout=2.5)
    models: list[dict[str, str]] = []
    if isinstance(tags, dict):
        for row in tags.get("models") or []:
            name = row.get("name") or row.get("model") or ""
            if name:
                models.append({"name": name})
    if not models:
        models = [{"name": m["name"]} for m in (node.get("models") or []) if m.get("name")]
    running: list[dict[str, str]] = []
    if isinstance(ps, dict):
        for row in ps.get("models") or []:
            name = row.get("name") or row.get("model") or ""
            if name:
                running.append({"name": name})
    if not running:
        running = list(node.get("running") or [])
    ok = tags_status == 200 or bool(node.get("ok"))
    return {**node, "ok": ok, "models": models, "running": running}


def farm_model_rows(dials: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Flatten BC-250 tags from live dials + /api/tags. Never invent hosts."""
    nodes = farm_hosts_from_dials(dials)
    if not nodes:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(nodes))) as pool:
        probed = list(pool.map(probe_farm_host, nodes))
    rows: list[dict[str, Any]] = []
    for node in probed:
        running_names = {r["name"] for r in node.get("running") or [] if r.get("name")}
        for model in node.get("models") or []:
            name = model.get("name") if isinstance(model, dict) else str(model or "")
            if not name:
                continue
            rows.append(
                {
                    "backend": node["id"],
                    "label": node["label"],
                    "gpu": node["gpu"],
                    "host_id": node.get("host_id") or node["id"],
                    "role": "farm",
                    "base": node["base"],
                    "name": name,
                    "loaded": is_loaded(name, running_names),
                    "backend_ok": bool(node.get("ok")),
                }
            )
    return rows


def inventory_rows(snap: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for be in snap.get("backends", {}).values():
        running_names = {r["name"] for r in be.get("running") or []}
        for model in be.get("models") or []:
            rows.append(
                {
                    "backend": be["id"],
                    "label": be["label"],
                    "gpu": be["gpu"],
                    "host_id": be["host_id"],
                    "role": be["role"],
                    "base": be["base"],
                    "name": model["name"],
                    "loaded": is_loaded(model["name"], running_names),
                    "backend_ok": be["ok"],
                }
            )
    rows.extend(farm_model_rows(snap.get("dials")))
    return rows


def models_snapshot() -> dict[str, Any]:
    snap = status_snapshot()
    rows = inventory_rows(snap)
    return {
        "vast_active": snap["vast_active"],
        "models": rows,
        "backends": snap["backends"],
        "farm_ok": snap["farm"]["ok"],
        "picker": picker_from_models({"vast_active": snap["vast_active"], "models": rows}),
    }


TALK_SKIP = ("embed", "nomic", "rerank", "whisper", "tts", "clip", "moondream")
PICKER_DEFAULTS = {
    "code": "qwen3-coder:30b",
    "chat": "qwen3.8:27b",
    "burst": "aria-qwen38:27b",
}


def is_talk_model(name: str) -> bool:
    low = (name or "").lower()
    if not low:
        return False
    return not any(part in low for part in TALK_SKIP)


def is_deepseek_model(name: str) -> bool:
    return "deepseek" in (name or "").lower()


def is_qwen38_tower(name: str) -> bool:
    low = (name or "").lower()
    return low.startswith("aria-qwen38") or low.startswith("qwen3.8-pharma")


def _picker_row(row: dict[str, Any], *, tier: str, blocked: bool) -> dict[str, Any]:
    return {
        "name": str(row.get("name") or ""),
        "loaded": bool(row.get("loaded")),
        "backend": row.get("backend"),
        "label": row.get("label"),
        "gpu": row.get("gpu"),
        "ok": bool(row.get("backend_ok")),
        "blocked": blocked,
        "tier": tier,
        "base": row.get("base"),
    }


def _code_extra_rows(rows: list[dict[str, Any]], vast: bool) -> list[dict[str, Any]]:
    """Cross-host code options: BC-250 DeepSeek, EVO CUDA qwen3.8, tower qwen3.8."""
    extras: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "")
        if not is_talk_model(name):
            continue
        role = str(row.get("role") or "")
        backend = str(row.get("backend") or "")
        key = (name, backend)
        if key in seen:
            continue
        blocked = False
        add = False
        if role == "farm" and is_deepseek_model(name):
            add = True
        elif role == "chat" and name == PICKER_DEFAULTS["chat"]:
            add = True
        elif role == "burst" and is_qwen38_tower(name) and name == PICKER_DEFAULTS["burst"]:
            add = True
            blocked = vast
        if add:
            seen.add(key)
            extras.append(_picker_row(row, tier="code", blocked=blocked))
    return extras


def picker_from_models(snap: dict[str, Any] | None) -> dict[str, Any]:
    """Group live /api/tags rows for the code vs ask picker. No toml fork."""
    snap = snap or {}
    vast = bool(snap.get("vast_active"))
    groups: dict[str, list[dict[str, Any]]] = {"code": [], "chat": [], "burst": []}
    for row in snap.get("models") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "")
        if not is_talk_model(name):
            continue
        role = str(row.get("role") or "")
        if role not in groups and role != "farm":
            continue
        if role in groups:
            groups[role].append(
                _picker_row(row, tier=role, blocked=role == "burst" and vast)
            )
    code_keys = {(r["name"], r.get("backend")) for r in groups["code"]}
    for extra in _code_extra_rows(snap.get("models") or [], vast):
        key = (extra["name"], extra.get("backend"))
        if key not in code_keys:
            groups["code"].append(extra)
            code_keys.add(key)
    for tier, rows in groups.items():
        default = PICKER_DEFAULTS[tier]
        prefix = default.split(":")[0]
        rows.sort(
            key=lambda r: (
                r.get("blocked"),
                not r["loaded"],
                0 if r["name"] == default or r["name"].startswith(prefix) else 1,
                r["name"],
            )
        )
    return {
        "vast_active": vast,
        "groups": groups,
        "defaults": {"code": PICKER_DEFAULTS["code"], "chat": PICKER_DEFAULTS["chat"]},
    }


def picker_snapshot() -> dict[str, Any]:
    return picker_from_models(models_snapshot())


def mesh_snapshot() -> dict[str, Any]:
    snap = status_snapshot()
    modes = _modes(snap)
    farm_nodes = farm_hosts_from_dials(snap.get("dials") or {})
    nodes = []
    for be in snap["backends"].values():
        nodes.append(
            {
                "id": be["id"],
                "kind": "ollama",
                "label": be["label"],
                "gpu": be["gpu"],
                "host_id": be["host_id"],
                "role": be["role"],
                "base": be["base"],
                "ok": be["ok"],
                "models": be.get("models") or [],
                "running": be.get("running") or [],
                "blocked": be["id"] == "burst" and snap["vast_active"],
                "pulse": bool(be["ok"]) and not (be["id"] == "burst" and snap["vast_active"]),
            }
        )
    nodes.extend(farm_nodes)
    # BC-250s first — that was the missing Mesh column; EVO/Tower follow.
    nodes.sort(key=lambda n: (0 if n.get("kind") == "bc250" else 1, str(n.get("id") or "")))
    with ThreadPoolExecutor(max_workers=2) as pool:
        ray_f = pool.submit(ray_jobs_snapshot, modes)
        ont_f = pool.submit(ontology_snapshot)
        ray = ray_f.result()
        ontology = ont_f.result()
    return {
        "vast_active": snap["vast_active"],
        "farm": snap["farm"],
        "fleet": snap["fleet"],
        "dials": snap["dials"],
        "nodes": nodes,
        "farm_hosts": farm_nodes,
        "ray": ray,
        "ontology": ontology,
        "pulse_at": datetime.now(timezone.utc).isoformat(),
        "pulse_ms": MESH_PULSE_MS,
    }


_TIER_BACKEND_PREF: dict[str, tuple[str, ...]] = {
    "code": ("amd", "farm", "cuda", "burst"),
    "chat": ("cuda", "amd", "farm", "burst"),
    "burst": ("burst",),
}


def _match_inventory_rows(name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    want = (name or "").strip()
    if not want:
        return []
    exact = [r for r in rows if r.get("name") == want]
    if exact:
        return exact
    prefix = want.split(":")[0]
    return [r for r in rows if str(r.get("name") or "").startswith(prefix)]


def _backend_rank(tier: str, row: dict[str, Any]) -> int:
    pref = _TIER_BACKEND_PREF.get(tier, ())
    backend = str(row.get("backend") or "")
    role = str(row.get("role") or "")
    if backend in pref:
        return pref.index(backend)
    if role == "farm":
        return pref.index("farm") if "farm" in pref else 99
    return 99


def _backend_snapshot_for_row(row: dict[str, Any], dials: dict[str, Any] | None) -> dict[str, Any]:
    backend_id = str(row.get("backend") or "")
    if backend_id in BACKENDS:
        return probe_backend(backend_id)
    node = next((n for n in farm_hosts_from_dials(dials) if n.get("id") == backend_id), None)
    if node is None:
        return {
            "id": backend_id,
            "label": row.get("label") or backend_id,
            "host_id": row.get("host_id") or backend_id,
            "gpu": row.get("gpu") or "",
            "base": row.get("base") or "",
            "ok": bool(row.get("backend_ok")),
            "role": "farm",
        }
    live = probe_farm_host(node)
    return {
        "id": backend_id,
        "label": live.get("label") or backend_id,
        "host_id": live.get("host_id") or backend_id,
        "gpu": live.get("gpu") or "",
        "base": live.get("base") or row.get("base") or "",
        "ok": bool(live.get("ok")),
        "role": "farm",
    }


def resolve_session(tier: str, model: str | None = None) -> dict[str, Any]:
    status = status_snapshot()
    vast = bool(status.get("vast_active"))
    be = backend_for_tier(tier)
    chosen = model or be.default_model
    rows = inventory_rows(status)
    matches = _match_inventory_rows(chosen, rows)
    if matches:
        matches.sort(key=lambda r: (_backend_rank(tier, r), not r.get("loaded"), r.get("name") or ""))
        pick = matches[0]
        chosen = str(pick.get("name") or chosen)
        backend = _backend_snapshot_for_row(pick, status.get("dials"))
        base = str(pick.get("base") or backend.get("base") or be.base)
        blocked = (tier == "burst" and vast) or (
            vast and str(pick.get("role") or "") == "burst"
        )
        return {
            "tier": tier,
            "backend": backend,
            "model": chosen,
            "base": base,
            "blocked": blocked,
        }
    snap = probe_backend(be.id)
    names = [m["name"] for m in snap.get("models") or []]
    if names and chosen not in names:
        prefix = chosen.split(":")[0]
        match = next((n for n in names if n == chosen or n.startswith(prefix)), None)
        if match:
            chosen = match
    return {
        "tier": tier,
        "backend": snap,
        "model": chosen,
        "base": be.base,
        "blocked": tier == "burst" and vast,
    }
