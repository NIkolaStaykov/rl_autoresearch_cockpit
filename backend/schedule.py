"""A persisted queue of experiments scheduled to run *later*.

The board lets you schedule a queue without a free GPU; entries land in
state/schedule.json (an ordered list) and a background dispatcher launches the
head entry onto a GPU as soon as one frees up — so you can line up an overnight
batch and walk away. This is the only mutable state the cockpit owns besides
notes; it is the *plan*, not a log of what ran (that stays read-through from
logs/_queue).

A daemon thread ticks every DISPATCH_INTERVAL seconds: if a GPU is free and the
schedule is non-empty, it pops the head and launches it (reusing control.launch,
which sizes num_envs to free VRAM). One launch per tick; a launch that 409s
(no free GPU) leaves the entry in place to retry next tick.
"""

from __future__ import annotations

import datetime
import json
import re
import shutil
import threading
import time
import uuid

from . import config

_PATH = config.COCKPIT_HOME / "state" / "schedule.json"

# A scheduled experiment's stem doubles as the staged YAML's filename and the
# eventual log-dir name, so keep it to plain filename characters.
_STEM_RE = re.compile(r"[A-Za-z0-9._-]+")

# Serializes all schedule.json mutations *and* the launch attempt, so the API
# (add/remove) and the dispatcher can't race on the same entry.
_lock = threading.RLock()

DISPATCH_INTERVAL = 8.0  # seconds between dispatcher ticks
_dispatcher_started = False


def _read_raw() -> list[dict]:
    if not _PATH.exists():
        return []
    try:
        data = json.loads(_PATH.read_text())
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _write_raw(entries: list[dict]) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps(entries, indent=2))


def list_pending() -> list[dict]:
    """The scheduled (not-yet-running) entries, in dispatch order."""
    with _lock:
        return _read_raw()


def _staged_path(entry: dict):
    """Absolute path to a pending entry's editable queue copy."""
    return config.PLAYGROUND_ROOT / entry["staged"]


def add(queue: str, start_from: int | None = None, content: str | None = None) -> dict:
    """Append a queue to the schedule.

    Stages a per-experiment copy of the queue YAML under logs/_scheduled so it
    can be edited independently of the learning/queues template. `content`, if
    given, is the (possibly edited) YAML to stage; otherwise the current template
    is copied verbatim — in which case it must exist, so we don't enqueue
    something that can never launch."""
    if not _STEM_RE.fullmatch(queue):
        raise ValueError("queue name must be a plain <name> (no path separators)")
    if content is None:
        tmpl = config.QUEUES / f"{queue}.yaml"
        if not tmpl.exists():
            raise FileNotFoundError(f"no such queue: {queue}.yaml")
        content = tmpl.read_text()

    entry_id = uuid.uuid4().hex[:8]
    staged = config.QUEUE_STAGE / entry_id / f"{queue}.yaml"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_text(content)
    entry = {
        "id": entry_id,
        "queue": queue,
        "start_from": int(start_from) if start_from else None,
        "enqueued_at": datetime.datetime.now().isoformat(timespec="seconds"),
        # repo-relative so it resolves the same inside the dev container
        "staged": str(staged.relative_to(config.PLAYGROUND_ROOT)),
    }
    with _lock:
        entries = _read_raw()
        entries.append(entry)
        _write_raw(entries)
    # Best-effort: try to dispatch right away if a GPU is free, so scheduling
    # with idle GPUs feels immediate rather than waiting for the next tick.
    threading.Thread(target=tick, daemon=True).start()
    return entry


def staged_content(entry_id: str) -> dict | None:
    """The staged YAML of a pending entry, for the editor. None if unknown."""
    with _lock:
        entry = next((e for e in _read_raw() if e.get("id") == entry_id), None)
    if entry is None or "staged" not in entry:
        return None
    path = _staged_path(entry)
    if not path.is_file():
        return None
    return {"stem": entry["queue"], "yaml": path.read_text(errors="replace")}


def update(entry_id: str, content: str) -> bool:
    """Rewrite a pending entry's staged queue copy. Only affects the per-
    experiment copy, never the learning/queues template. False if no such entry
    (e.g. it already launched). The lock serializes against the dispatcher, so an
    entry can't be edited mid-launch."""
    with _lock:
        entry = next((e for e in _read_raw() if e.get("id") == entry_id), None)
        if entry is None or "staged" not in entry:
            return False
        path = _staged_path(entry)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return True


def remove(entry_id: str) -> bool:
    with _lock:
        entries = _read_raw()
        kept = [e for e in entries if e.get("id") != entry_id]
        if len(kept) == len(entries):
            return False
        _write_raw(kept)
        # Drop the staged copy too — it only mattered while the entry was pending.
        shutil.rmtree(config.QUEUE_STAGE / entry_id, ignore_errors=True)
        return True


def tick() -> dict | None:
    """If a GPU is free and the schedule is non-empty, launch the head entry.

    Returns the launched entry (with its launch result) or None. Imports control
    lazily to avoid a circular import (control imports discovery, not us)."""
    from . import control  # noqa: PLC0415

    with _lock:
        entries = _read_raw()
        if not entries:
            return None
        head = entries[0]
        try:
            # Launch the staged per-experiment copy, not the live template.
            res = control.launch(
                head["queue"], head.get("start_from"), queue_path=head.get("staged")
            )
        except control.Busy:
            return None  # no free GPU; leave it queued for next tick
        except FileNotFoundError:
            # Staged YAML vanished since it was scheduled — drop it so it can't
            # wedge the head of the queue forever.
            _write_raw(entries[1:])
            return None
        except Exception:
            return None
        _write_raw(entries[1:])
        return {**head, "launched": res}


def _loop() -> None:
    while True:
        time.sleep(DISPATCH_INTERVAL)
        try:
            tick()
        except Exception:
            pass  # never let a transient error kill the dispatcher


def start_dispatcher() -> None:
    """Start the background dispatcher once per process."""
    global _dispatcher_started
    with _lock:
        if _dispatcher_started:
            return
        _dispatcher_started = True
    threading.Thread(target=_loop, daemon=True, name="schedule-dispatcher").start()
