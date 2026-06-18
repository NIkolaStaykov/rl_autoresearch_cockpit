"""Discover queue-runs and join plan x execution-state x live process info.

Sources, all live-read every call (no DB):
  - learning/queues/<stem>.yaml      : the experiment SPEC (sweep + hypothesis)
  - logs/_queue/<stem>-<ts>/         : one EXECUTION of that spec
      status.json                    : per-run results, appended between runs
      run-XX-*.log / *-overrides.yaml: per-run artifacts
  - `ps`                             : which queue-run is training right now
"""

from __future__ import annotations

import collections
import datetime
import json
import pathlib
import re
import subprocess
from typing import Any, Optional

import yaml

from . import config, containers, contrasts, hypothesis, metrics, metrics_config, notes, playground, settings

_TS_RE = re.compile(r"-(\d{8})-(\d{6})$")


# --------------------------------------------------------------------------
# Live process detection
# --------------------------------------------------------------------------

def active_queue_dirs() -> set[str]:
    """Names of queue-run dirs that have a training subprocess alive now.

    The train subprocess carries --env_overrides_file=logs/_queue/<dir>/...,
    so the live queue-run dir name falls straight out of the process table.
    """
    try:
        out = subprocess.run(
            ["ps", "-eo", "args"], capture_output=True, text=True, timeout=5
        ).stdout
    except Exception:
        return set()
    dirs = set()
    for m in re.finditer(r"_queue/([^/\s]+)/", out):
        dirs.add(m.group(1))
    return dirs


# --------------------------------------------------------------------------
# Spec (queue YAML) parsing
# --------------------------------------------------------------------------

def _stem(dir_name: str) -> str:
    return _TS_RE.sub("", dir_name)


def _started_at(dir_name: str) -> Optional[str]:
    m = _TS_RE.search(dir_name)
    if not m:
        return None
    try:
        dt = datetime.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        return dt.isoformat()
    except ValueError:
        return None


def _raw_yaml(stem: str) -> Optional[dict]:
    path = config.QUEUES / f"{stem}.yaml"
    if not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError:
        return None


def _doc_comment(stem: str) -> Optional[str]:
    """Leading `#` comment block of the queue YAML = the prose hypothesis."""
    path = config.QUEUES / f"{stem}.yaml"
    if not path.exists():
        return None
    lines = []
    for line in path.read_text().splitlines():
        if line.startswith("#"):
            lines.append(line.lstrip("#").rstrip())
        elif line.strip() == "":
            if lines:
                lines.append("")
        else:
            break
    text = "\n".join(lines).strip()
    return text or None


def _axes(raw: Optional[dict]) -> list[str]:
    if not raw:
        return []
    return list((raw.get("sweep", {}) or {}).get("params", {}).keys())


def _expanded_specs(stem: str) -> dict[int, dict]:
    """Full plan from the source YAML, keyed by run idx (empty if YAML gone)."""
    path = config.QUEUES / f"{stem}.yaml"
    if not path.exists():
        return {}
    try:
        rq = playground.run_queue()
        specs = rq.parse_queue(path)
    except Exception:
        return {}
    return {s["idx"]: s for s in specs}


def _load_status(qdir: pathlib.Path) -> list[dict]:
    sp = qdir / "status.json"
    if not sp.exists():
        return []
    try:
        return json.loads(sp.read_text())
    except json.JSONDecodeError:
        return []


def _load_overrides_file(path: Optional[str]) -> dict:
    if not path:
        return {}
    p = pathlib.Path(path)
    if not p.is_absolute():
        p = config.PLAYGROUND_ROOT / p
    if not p.exists():
        return {}
    try:
        return yaml.safe_load(p.read_text()) or {}
    except yaml.YAMLError:
        return {}


def run_log_text(queue_name: str, idx: int) -> Optional[str]:
    """Raw tee'd training log for run `idx` of a queue (backup/debug view).
    Returns None if the queue dir or the run log is missing."""
    qdir = config.QUEUE_LOGS / queue_name
    if not qdir.is_dir():
        return None
    matches = sorted(qdir.glob(f"run-{idx:02d}-*.log"))
    if not matches:
        return None
    try:
        return matches[0].read_text(errors="replace")
    except OSError:
        return None


_LAUNCH_LOG_RE = re.compile(r"^(?P<stem>.+)-(?P<d>\d{8})-(?P<t>\d{6})-gpu\d+\.log$")


def _launch_log_path(queue_name: str) -> Optional[pathlib.Path]:
    """Orchestrator log for a cockpit-launched queue (run_queue.py stdout/stderr,
    written by containers.run_queue_in). The launch timestamp differs from the
    queue-dir timestamp, so among logs for this stem we pick the one launched
    closest in time to the run. None if the queue was launched outside the cockpit.
    """
    log_dir = containers.LAUNCH_LOG_DIR
    if not log_dir.is_dir():
        return None
    stem = _stem(queue_name)
    cands = []
    for p in log_dir.iterdir():
        m = _LAUNCH_LOG_RE.match(p.name)
        if m and m.group("stem") == stem:
            try:
                dt = datetime.datetime.strptime(m.group("d") + m.group("t"), "%Y%m%d%H%M%S")
            except ValueError:
                continue
            cands.append((dt, p))
    if not cands:
        return None
    started = _started_at(queue_name)
    if started:
        target = datetime.datetime.fromisoformat(started)
        cands.sort(key=lambda c: abs((c[0] - target).total_seconds()))
    else:
        cands.sort(key=lambda c: c[0])  # fall back to the most recent launch
    return cands[-1][1] if not started else cands[0][1]


def queue_log_text(queue_name: str) -> Optional[str]:
    """Raw orchestrator log for a queue-run (the 'why did the queue itself fail'
    view). None if there is no cockpit launch log for it."""
    p = _launch_log_path(queue_name)
    if p is None:
        return None
    try:
        return p.read_text(errors="replace")
    except OSError:
        return None


def _running_exp_name(qdir: pathlib.Path, idx: int) -> Optional[str]:
    """The in-flight run's exp name isn't in status.json yet; it's printed in the
    queue's tee'd run-<idx>-*.log as 'Experiment name: ...'."""
    for log in qdir.glob(f"run-{idx:02d}-*.log"):
        try:
            txt = log.read_text(errors="ignore")
        except OSError:
            continue
        m = re.search(r"Experiment name:\s*(\S+)", txt)
        if m:
            return m.group(1)
    return None


def _duration_s(entry: dict) -> Optional[float]:
    try:
        a = datetime.datetime.fromisoformat(entry["started_at"])
        b = datetime.datetime.fromisoformat(entry["ended_at"])
        return (b - a).total_seconds()
    except Exception:
        return None


# --------------------------------------------------------------------------
# Board
# --------------------------------------------------------------------------

def list_queues() -> list[dict]:
    if not config.QUEUE_LOGS.is_dir():
        return []
    active = active_queue_dirs()
    out = []
    for qdir in config.QUEUE_LOGS.iterdir():
        if not qdir.is_dir():
            continue
        out.append(_queue_card(qdir, active))
    out.sort(key=lambda c: c.get("last_activity") or "", reverse=True)
    return out


def _last_activity(qdir: pathlib.Path) -> Optional[str]:
    mtimes = [p.stat().st_mtime for p in qdir.glob("*")]
    if not mtimes:
        return None
    return datetime.datetime.fromtimestamp(max(mtimes)).isoformat()


# Per-run artifacts are named run-<idx>-<EnvName>[-<suffix>].<ext> (e.g.
# run-00-TesolloDownwardsRotateZ-sharp10-overrides.yaml). Env names are CamelCase
# with no dashes, so the env is the token right after the run index.
_ARTIFACT_ENV_RE = re.compile(r"^run-\d+-([A-Za-z0-9]+)")


def _queue_env(qdir: pathlib.Path, status: list[dict], specs: dict[int, dict]) -> Optional[str]:
    """The task/env this queue-run trains on, inferred from the data (never
    hardcoded). Uses the most common env_name across recorded runs; for queues
    that haven't produced any status yet, falls back to the planned spec's
    env_name, then to the env baked into the per-run artifact filenames (which
    survive even when status.json is empty and the source YAML is gone). Returns
    None when nothing names an env."""
    names: list[str] = []
    for s in status:
        env = s.get("env_name") or (s.get("flags") or {}).get("env_name")
        if env:
            names.append(env)
    if not names:
        for spec in specs.values():
            env = (spec.get("flags") or {}).get("env_name")
            if env:
                names.append(env)
    if not names:
        for p in qdir.glob("run-*"):
            m = _ARTIFACT_ENV_RE.match(p.name)
            if m:
                names.append(m.group(1))
    if not names:
        return None
    return collections.Counter(names).most_common(1)[0][0]


def _queue_card(qdir: pathlib.Path, active: set[str]) -> dict:
    name = qdir.name
    stem = _stem(name)
    status = _load_status(qdir)
    specs = _expanded_specs(stem)
    total = max(len(specs), len(status)) if specs else len(status)
    passed = sum(1 for s in status if s.get("result") == "ok")
    failed = sum(1 for s in status if s.get("result") == "failed")
    completed = len(status)
    is_active = name in active

    durs = [d for d in (_duration_s(s) for s in status) if d]
    median = sorted(durs)[len(durs) // 2] if durs else None
    remaining = max(0, total - completed)
    eta = median * remaining if (median and is_active) else None

    return {
        "id": name,
        "stem": stem,
        "env": _queue_env(qdir, status, specs),
        "started_at": _started_at(name),
        "last_activity": _last_activity(qdir),
        "total": total,
        "completed": completed,
        "passed": passed,
        "failed": failed,
        "running": is_active,
        "status": "running" if is_active else ("done" if completed else "empty"),
        "eta_seconds": eta,
        "has_yaml": bool(specs) or (config.QUEUES / f"{stem}.yaml").exists(),
    }


# --------------------------------------------------------------------------
# Detail
# --------------------------------------------------------------------------

def queue_detail(name: str, with_metrics: bool = True) -> Optional[dict]:
    qdir = config.QUEUE_LOGS / name
    if not qdir.is_dir():
        return None
    stem = _stem(name)
    raw = _raw_yaml(stem)
    status = _load_status(qdir)
    specs = _expanded_specs(stem)
    active = active_queue_dirs()
    is_active = name in active

    status_by_idx = {s["idx"]: s for s in status}
    completed = len(status)
    axes = _axes(raw)

    # Effective success metric = the queue's hypothesis `metric` override if it
    # names a known one, else the global default.
    hyp = (raw or {}).get("hypothesis")
    global_default = settings.read()["success_metric"]
    success_id = metrics_config.resolve_success_id((hyp or {}).get("metric"), global_default)

    idxs = sorted(set(specs) | set(status_by_idx))
    runs = []
    for idx in idxs:
        spec = specs.get(idx)
        st = status_by_idx.get(idx)

        flags = (st or {}).get("flags") or (spec or {}).get("flags") or {}
        overrides = {}
        if spec is not None:
            try:
                overrides = playground.run_queue()._flatten(spec.get("env_overrides", {}))
            except Exception:
                overrides = {}
        if not overrides and st is not None:
            overrides = _load_overrides_file(st.get("overrides_file"))

        if st is not None:
            run_status = "done" if st.get("result") == "ok" else "failed"
        elif is_active and idx == completed:
            run_status = "running"
        else:
            run_status = "pending"

        params = {a: overrides.get(a) for a in axes} if axes else dict(overrides)
        exp_name = (st or {}).get("exp_name")
        if exp_name is None and run_status == "running":
            exp_name = _running_exp_name(qdir, idx)

        row = {
            "idx": idx,
            "env": flags.get("env_name"),
            "suffix": flags.get("suffix"),
            "seed": flags.get("seed"),
            "params": params,
            "status": run_status,
            "exp_name": exp_name,
            "started_at": (st or {}).get("started_at"),
            "ended_at": (st or {}).get("ended_at"),
            "duration_s": _duration_s(st) if st else None,
        }
        if with_metrics and exp_name:
            try:
                m = metrics.summarize(exp_name, success_id)
                if m and "error" not in m:
                    row["reward"] = m["reward"]      # {eval, train}
                    row["success"] = m["success"]    # {id,label,kind,eval,train}
                    row["n_evals"] = m.get("n_evals")
                    row["final_step"] = m.get("final_step")
                    row["divergence"] = m.get("divergence")
                    if run_status == "running":
                        total = flags.get("num_timesteps")
                        if total and m.get("final_step"):
                            row["progress"] = min(1.0, m["final_step"] / float(total))
            except Exception:
                pass
        runs.append(row)

    sm = metrics_config.SUCCESS_METRICS[success_id]
    return {
        "id": name,
        "stem": stem,
        "started_at": _started_at(name),
        "running": is_active,
        "axes": axes,
        "hypothesis": hyp,
        "verdict": hypothesis.evaluate(hyp, runs),
        "contrasts": contrasts.evaluate((raw or {}).get("contrasts"), runs),
        "success_metric": {"id": success_id, "label": sm["label"], "kind": sm["kind"]},
        "doc": _doc_comment(stem),
        "conclusion": notes.read(name),
        "total": len(idxs),
        "completed": completed,
        "log_available": _launch_log_path(name) is not None,
        "runs": runs,
    }


# --------------------------------------------------------------------------
# Launchable queue specs
# --------------------------------------------------------------------------

def list_queue_specs() -> list[dict]:
    """Every queue YAML available to launch, with a run count + summary."""
    if not config.QUEUES.is_dir():
        return []
    out = []
    for path in sorted(config.QUEUES.glob("*.yaml")):
        stem = path.stem
        raw = _raw_yaml(stem) or {}
        try:
            n_runs = len(playground.run_queue().parse_queue(path))
        except Exception:
            n_runs = None
        doc = _doc_comment(stem)
        out.append({
            "stem": stem,
            "n_runs": n_runs,
            "axes": _axes(raw),
            "has_hypothesis": bool(raw.get("hypothesis")),
            "summary": (doc.splitlines()[0] if doc else None),
        })
    return out
