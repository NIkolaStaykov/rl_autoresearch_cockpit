"""Dispatch queues into the dev containers, one per GPU.

Each dev container binds a single GPU (NVIDIA_VISIBLE_DEVICES) and mounts the
workspace at the same host path, so it can run `.venv/bin/python
learning/run_queue.py` directly. On launch we pick a container whose GPU is free
and `docker exec -d` the queue inside it; the orchestrator's stdout is redirected
to a log under the (shared) cockpit state dir so the host can read it.

Free = the bound GPU is under FREE_MEM_MIB *and* no run_queue.py is already
running inside that container (covers the window before JAX grabs memory).
"""

from __future__ import annotations

import datetime
import json
import re
import subprocess
import time

from . import config

# A GPU using less than this (MiB) counts as free. A mujoco JAX run preallocates
# multiple GB; the idle 4090s sit at ~13 MiB, so the gap is wide.
FREE_MEM_MIB = 2000

# VRAM-based num_envs sizing. 18 GiB free is enough for the full 8192-env config;
# below that, halve num_envs (8192 -> 4096 -> 2048 ...) down to the largest
# power of two that fits, keeping it divisible by typical minibatch counts. A GPU
# with too little free VRAM for MIN_ENVS is not eligible to receive a queue.
VRAM_FOR_MAX_ENVS_MIB = 18 * 1024
MAX_ENVS = 8192
MIN_ENVS = 512

LAUNCH_LOG_DIR = config.COCKPIT_HOME / "state" / "launch_logs"


def envs_for_free_vram(free_mib: int | None) -> int | None:
    """Largest power-of-two num_envs that fits in `free_mib` of VRAM. VRAM scales
    linearly with envs (18 GiB -> MAX_ENVS), so we take that estimate and floor it
    to a power of two (halving). None if it can't fit MIN_ENVS."""
    if not free_mib:
        return None
    capped = min(int(MAX_ENVS * free_mib / VRAM_FOR_MAX_ENVS_MIB), MAX_ENVS)
    if capped < MIN_ENVS:
        return None
    return 1 << (capped.bit_length() - 1)  # largest power of two <= capped

_cache: dict = {"containers": None, "ts": 0.0}


def _docker(args, timeout=15) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def list_dev_containers(ttl: float = 60.0) -> list[dict]:
    """Running containers that bind exactly one GPU and mount PLAYGROUND_ROOT.
    Cached (the set rarely changes) -> [{name, gpu}] sorted by gpu."""
    now = time.time()
    if _cache["containers"] is not None and now - _cache["ts"] < ttl:
        return _cache["containers"]
    out = []
    try:
        names = _docker(["ps", "--format", "{{.Names}}"]).stdout.split()
    except Exception:
        names = []
    root = str(config.PLAYGROUND_ROOT)
    for n in names:
        try:
            info = json.loads(_docker(["inspect", n]).stdout)[0]
        except Exception:
            continue
        env = dict(
            e.split("=", 1) for e in info.get("Config", {}).get("Env", []) if "=" in e
        )
        vis = env.get("NVIDIA_VISIBLE_DEVICES", "")
        if not re.fullmatch(r"\d+", vis):  # need exactly one numeric GPU
            continue
        mounts = info.get("Mounts", [])
        if not any(root.startswith(m.get("Destination", "\0")) for m in mounts):
            continue
        out.append({"name": n, "gpu": int(vis)})
    out.sort(key=lambda c: c["gpu"])
    _cache.update(containers=out, ts=now)
    return out


def gpu_mem_used() -> dict:
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except Exception:
        return {}
    mem = {}
    for line in res.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 2 and parts[0].isdigit():
            mem[int(parts[0])] = int(parts[1])
    return mem


def _gpu_mem_free_once() -> dict:
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except Exception:
        return {}
    free = {}
    for line in res.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 2 and parts[0].isdigit():
            free[int(parts[0])] = int(parts[1])
    return free


def gpu_mem_free(samples: int = 1, interval: float = 0.25) -> dict:
    """Free VRAM per GPU index. With samples>1, take the MAX free seen across a few
    quick reads: nvidia-smi is instantaneous and a transient allocation by another
    process briefly depresses `free`, which would undersize num_envs. Max-free over a
    short window rejects such blips and reflects the steady-state headroom. samples=1
    (the default) keeps the frequently-polled dashboard fast."""
    free = _gpu_mem_free_once()
    for _ in range(max(0, samples - 1)):
        time.sleep(interval)
        for gpu, f in _gpu_mem_free_once().items():
            free[gpu] = max(free.get(gpu, 0), f)
    return free


def container_queue(name: str) -> str | None:
    """Queue stem of the run_queue.py running inside the container, or None.
    The `[r]` glob keeps grep from matching its own command line."""
    try:
        out = _docker(
            ["exec", name, "bash", "-lc", "ps -eo args= | grep '[r]un_queue.py' || true"],
            timeout=8,
        ).stdout
    except Exception:
        return None
    if "run_queue.py" not in out:
        return None
    m = re.search(r"queues/(\S+?)\.yaml", out)
    return m.group(1) if m else "(running)"


def status(vram_samples: int = 1) -> list[dict]:
    mem = gpu_mem_used()
    mem_free = gpu_mem_free(samples=vram_samples)
    rows = []
    for c in list_dev_containers():
        q = container_queue(c["name"])
        used = mem.get(c["gpu"])
        free_mib = mem_free.get(c["gpu"])
        fit_envs = envs_for_free_vram(free_mib)
        rows.append({
            "container": c["name"], "gpu": c["gpu"],
            "mem_used": used, "mem_free": free_mib, "queue": q,
            # legacy boolean: GPU essentially idle and no queue here
            "free": q is None and used is not None and used < FREE_MEM_MIB,
            # VRAM-based eligibility: no cockpit queue here and enough free VRAM
            "fit_envs": fit_envs if q is None else None,
        })
    return rows


def pick_free(rows: list[dict]) -> dict | None:
    return next((r for r in rows if r["free"]), None)


def pick_for_vram(rows: list[dict]) -> dict | None:
    """Pick the eligible container with the most free VRAM, sizing num_envs to it.
    Eligible = no cockpit queue already running there and enough free VRAM for
    MIN_ENVS. Returns the row plus the chosen `num_envs`, or None if none fit."""
    eligible = [r for r in rows if r.get("fit_envs")]
    if not eligible:
        return None
    best = max(eligible, key=lambda r: r["mem_free"])
    return {**best, "num_envs": best["fit_envs"]}


def _exec_detached(name: str, inner_cmd: str):
    res = _docker(["exec", "-d", name, "bash", "-lc", inner_cmd], timeout=20)
    if res.returncode != 0:
        raise RuntimeError(f"docker exec failed: {res.stderr.strip() or res.stdout.strip()}")


def run_queue_in(name: str, gpu: int, run_queue_args: str, label: str) -> dict:
    """Start run_queue.py inside `name`, output to a shared-mount log.

    Before exec'ing, source config.LAUNCH_ENV_FILE if it exists (e.g. for
    WANDB_API_KEY) so launches are authenticated without baking secrets into the
    image or the cockpit. It lives on the bind-mounted workspace, so the same
    absolute path resolves inside the container.
    """
    LAUNCH_LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = LAUNCH_LOG_DIR / f"{label}-{ts}-gpu{gpu}.log"
    envf = config.LAUNCH_ENV_FILE
    # The sourced env file (config.LAUNCH_ENV_FILE, i.e. workspace/.cockpit.env)
    # also carries MUJOCO_GL=egl / PYOPENGL_PLATFORM=egl, overriding the images'
    # baked-in glx defaults so mujoco exposes its Renderer for headless wandb
    # video logging (glx needs an X display the container lacks).
    inner = (
        f"cd {config.PLAYGROUND_ROOT} && exec > {log_path} 2>&1 && "
        f"{{ [ -f {envf} ] && set -a && . {envf} && set +a; }}; "
        f"exec ./.venv/bin/python -u learning/run_queue.py {run_queue_args}"
    )
    _exec_detached(name, inner)
    return {"container": name, "gpu": gpu, "log": str(log_path)}


def stop_in(name: str) -> bool:
    """SIGINT the run_queue.py inside `name` (graceful: it kills its child and
    writes status.json). The `[r]` glob avoids pkill matching itself."""
    res = _docker(
        ["exec", name, "bash", "-lc", "pkill -INT -f '[l]earning/run_queue.py'"],
        timeout=10,
    )
    return res.returncode == 0
