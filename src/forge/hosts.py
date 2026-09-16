"""Live farm endpoints. Do not fork llm_models.toml — probe these hosts."""

from __future__ import annotations

from dataclasses import asdict, dataclass

EVO = "192.168.68.103"
TOWER = "192.168.68.106"

FARM_HEALTH = f"http://{EVO}:5000/health"
FARM_FLEET = f"http://{EVO}:5000/api/fleet/status"
FARM_DIALS = f"http://{EVO}:5000/api/compute/dials"
FARM_COMPUTE = f"http://{EVO}:5000/api/compute/status"
ONTOLOGY = f"http://{EVO}:8000"
ONTOLOGY_HEALTH = f"{ONTOLOGY}/health"
ONTOLOGY_AGENTS = f"{ONTOLOGY}/entities/agent_record"
RAY_DASH = f"http://{EVO}:8265"
RAY_JOBS = f"{RAY_DASH}/api/v0/jobs"

LINKS = {
    "vault": r"C:\Users\jlay\Documents\FarmBrainVault",
    "aether_launch": r"C:\Users\jlay\Grok\aether\scripts\launch-aether.ps1",
    "lumen": f"http://{EVO}:8100",
    "aipm": f"http://{EVO}:5080",
    "farm": f"http://{EVO}:5000",
    "farm_compute": f"http://{EVO}:5000/#compute",
    "farm_coder": f"http://{EVO}:5000/agent",
    "ontology": f"{ONTOLOGY}/docs",
    "ray": RAY_DASH,
}


@dataclass(frozen=True)
class Backend:
    id: str
    label: str
    host_id: str
    gpu: str
    base: str
    default_model: str
    role: str

    def as_dict(self) -> dict:
        return asdict(self)


BACKENDS: dict[str, Backend] = {
    "cuda": Backend(
        id="cuda",
        label="EVO CUDA",
        host_id="evo",
        gpu="RTX 5070 Ti",
        base=f"http://{EVO}:11434",
        default_model="qwen3.8:27b",
        role="chat",
    ),
    "amd": Backend(
        id="amd",
        label="EVO AMD",
        host_id="evo",
        gpu="Strix Halo GTT",
        base=f"http://{EVO}:11437",
        default_model="qwen3-coder:30b",
        role="code",
    ),
    "burst": Backend(
        id="burst",
        label="Tower 5090",
        host_id="tower",
        gpu="RTX 5090",
        base=f"http://{TOWER}:11434",
        default_model="aria-qwen38:27b",
        role="burst",
    ),
}

TIERS: dict[str, str] = {
    "code": "amd",
    "chat": "cuda",
    "burst": "burst",
}

PROTECTED_WORKSPACES = frozenset({"farm-brain"})


def backend_for_tier(tier: str) -> Backend:
    key = TIERS.get(tier)
    if not key:
        raise ValueError(f"unknown tier {tier!r}; use code|chat|burst")
    return BACKENDS[key]
