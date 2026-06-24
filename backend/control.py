"""Queue control: launch / stop / resume training queues in the dev containers,
plus a plan-next scaffold.

Launches are dispatched into a dev container whose GPU is free (see
containers.py) via `docker exec -d`. One queue per GPU/container; launch/resume
return 409 if no container is free. Stop sends SIGINT to run_queue.py inside the
container so it kills its training child and writes status.json.
"""

from __future__ import annotations

import datetime
import re

from . import config, containers, discovery


class Busy(Exception):
    """No free GPU/container to dispatch to."""


class NotRunning(Exception):
    """No queue process to act on."""


def status() -> dict:
    rows = containers.status()
    return {
        "containers": rows,
        "any_free": any(r["free"] for r in rows),
        "running": [r for r in rows if r["queue"]],
    }


def launch(
    queue_stem: str,
    start_from: int | None = None,
    queue_path: str | None = None,
) -> dict:
    # `queue_path` is a repo-relative YAML to run (e.g. a scheduled experiment's
    # staged copy under logs/_scheduled); it defaults to the learning/queues
    # template for the stem. Either way run_queue.py reads it with the dev
    # container's cwd at the playground root, so the path stays repo-relative.
    rel = queue_path or f"learning/queues/{queue_stem}.yaml"
    yaml_path = config.PLAYGROUND_ROOT / rel
    if not yaml_path.exists():
        raise FileNotFoundError(f"no such queue: {rel}")
    # Robust VRAM read (max free across a few samples) so a transient spike in
    # another process can't undersize num_envs at launch.
    target = containers.pick_for_vram(containers.status(vram_samples=4))
    if target is None:
        raise Busy("no GPU with enough free VRAM available")
    num_envs = target["num_envs"]
    args = f"--queue {rel} --yes --num-envs {num_envs}"
    if start_from:
        args += f" --start-from {int(start_from)}"
    res = containers.run_queue_in(target["container"], target["gpu"], args, queue_stem)
    res["num_envs"] = num_envs
    res["mem_free"] = target["mem_free"]
    return res


def resume(n: int, steps: int, source_dir: str | None = None) -> dict:
    target = containers.pick_free(containers.status())
    if target is None:
        raise Busy("no free GPU/container available")
    args = f"--resume {int(n)} --resume-steps {int(steps)} --yes"
    if source_dir:
        args += f" --resume-from logs/_queue/{source_dir}"
    return containers.run_queue_in(target["container"], target["gpu"], args, "resume")


def stop(container: str | None = None) -> dict:
    """Stop the queue in `container` (or the only running one if unambiguous)."""
    running = [r for r in containers.status() if r["queue"]]
    if not running:
        raise NotRunning("no container is running a queue")
    if container is None:
        if len(running) != 1:
            raise NotRunning("multiple queues running; specify a container")
        container = running[0]["container"]
    elif container not in {r["container"] for r in running}:
        raise NotRunning(f"{container} is not running a queue")
    ok = containers.stop_in(container)
    return {"stopped": container, "ok": ok}


# --------------------------------------------------------------------------
# Plan-next scaffold
# --------------------------------------------------------------------------

def plan_next_draft(queue_id: str) -> dict:
    """A starting-point YAML for the follow-up experiment: the source queue's
    spec, renamed, for the user to edit. Does not write anything."""
    stem = discovery._stem(queue_id)
    src = config.QUEUES / f"{stem}.yaml"
    content = src.read_text() if src.exists() else "defaults:\n  flags:\n    use_wandb: true\n\nsweep:\n"
    new_stem = f"{stem}_v2"
    header = (
        f"# Drafted from {stem} by the cockpit on "
        f"{datetime.date.today().isoformat()}. Edit before launching.\n"
    )
    return {"filename": f"{new_stem}.yaml", "yaml": header + content}


def save_queue(filename: str, content: str, overwrite: bool = False) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9._-]+\.yaml", filename):
        raise ValueError("filename must be a plain <name>.yaml")
    target = config.QUEUES / filename
    if target.exists() and not overwrite:
        raise FileExistsError(f"{filename} already exists")
    target.write_text(content)
    return {"path": str(target), "stem": filename[:-5]}
