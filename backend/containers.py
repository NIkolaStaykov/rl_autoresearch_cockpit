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

LAUNCH_LOG_DIR = config.COCKPIT_HOME / "state" / "launch_logs"

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


def status() -> list[dict]:
    mem = gpu_mem_used()
    rows = []
    for c in list_dev_containers():
        q = container_queue(c["name"])
        used = mem.get(c["gpu"])
        free = q is None and used is not None and used < FREE_MEM_MIB
        rows.append({
            "container": c["name"], "gpu": c["gpu"],
            "mem_used": used, "queue": q, "free": free,
        })
    return rows


def pick_free(rows: list[dict]) -> dict | None:
    return next((r for r in rows if r["free"]), None)


def _exec_detached(name: str, inner_cmd: str):
    res = _docker(["exec", "-d", name, "bash", "-lc", inner_cmd], timeout=20)
    if res.returncode != 0:
        raise RuntimeError(f"docker exec failed: {res.stderr.strip() or res.stdout.strip()}")


# Optional env file on the (mounted) playground root, sourced before every
# launch so credentials/config (e.g. WANDB_API_KEY) apply to all containers and
# survive container recreation. Simple `KEY=value` shell syntax, resolved
# relative to PLAYGROUND_ROOT.
ENV_FILE = ".cockpit.env"


def run_queue_in(name: str, gpu: int, run_queue_args: str, label: str) -> dict:
    """Start run_queue.py inside `name`, output to a shared-mount log.

    Before exec'ing, source PLAYGROUND_ROOT/.cockpit.env if it exists (e.g. for
    WANDB_API_KEY) so launches are authenticated without baking secrets into the
    image or the cockpit.
    """
    LAUNCH_LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = LAUNCH_LOG_DIR / f"{label}-{ts}-gpu{gpu}.log"
    inner = (
        f"cd {config.PLAYGROUND_ROOT} && exec > {log_path} 2>&1 && "
        f"{{ [ -f {ENV_FILE} ] && set -a && . ./{ENV_FILE} && set +a; }}; "
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
