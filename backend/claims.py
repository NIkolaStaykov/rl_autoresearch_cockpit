"""Cross-queue claims — the top of the hierarchy, graded read-through.

A *claim* aggregates contrasts whose arms may live in *different* queues into a
single directional or general statement ("proprioception sufficient under C1,C2").
Claim specs are human-authored source files (like queue YAMLs), not cockpit state:
they live in `<PLAYGROUND_ROOT>/learning/claims/*.yaml` and are parsed live.

  # learning/claims/proprio_sufficiency.yaml
  statement: Proprioception is sufficient for pinch under {noisy, nominal}
  aggregation: all                 # all | majority | any
  scope:
    covers: [noisy, nominal, low_friction]
    tested: [noisy, nominal]
  falsifiers:
    - proprio underperforms full-state under unseen friction
  children:
    - queue: pinch_single_channel_ablation   # which execution to draw arms from
      task: pinch
      metric: success.eval
      relation: matches
      margin: 0.05
      min_seeds: 3
      arm_a: {sensor_bundle: proprio}
      arm_b: {sensor_bundle: proprio_qdot}
    - statement: ...                          # nesting: a child can be a sub-claim

`queue:` names a queue *stem*; the latest execution of that stem is used. A child
with its own `children:` is a nested sub-claim, graded recursively.

NOTE (assumption): the `learning/claims/` location mirrors `learning/queues/` and
is read-through, so it fits the cockpit's "persist nothing but notes" rule. Say the
word if you'd rather author claims inside the cockpit repo instead.
"""

from __future__ import annotations

import pathlib
from typing import Optional

import yaml

from . import config, contrasts, discovery

CLAIMS_DIR = config.LEARNING_DIR / "claims"


def _latest_run_dir(stem: str) -> Optional[str]:
    """Most-recent execution dir name for a queue stem (by start timestamp)."""
    if not config.QUEUE_LOGS.is_dir():
        return None
    cands = [d.name for d in config.QUEUE_LOGS.iterdir()
             if d.is_dir() and discovery._stem(d.name) == stem]
    if not cands:
        return None
    return sorted(cands, key=lambda n: discovery._started_at(n) or "")[-1]


def _runs_for_queue(stem: str, _cache: dict) -> list[dict]:
    if stem not in _cache:
        run_dir = _latest_run_dir(stem)
        detail = discovery.queue_detail(run_dir, with_metrics=True) if run_dir else None
        _cache[stem] = (detail or {}).get("runs", [])
    return _cache[stem]


def _grade_node(node: dict, _cache: dict) -> dict:
    """A child is either a sub-claim (has `children:`) or a contrast (has `queue:`)."""
    if "children" in node:
        return _grade_claim(node, _cache)
    runs = _runs_for_queue(node["queue"], _cache)
    graded = contrasts.grade_one(node, runs)
    graded["queue"] = node["queue"]
    return graded


def _grade_claim(spec: dict, _cache: dict) -> dict:
    children = [_grade_node(ch, _cache) for ch in spec.get("children", [])]
    scope_d = spec.get("scope") or {}
    return contrasts.grade_claim(
        statement=spec.get("statement", ""),
        child_verdicts=children,
        aggregation=contrasts.Aggregation(spec.get("aggregation", "all")),
        scope=contrasts.Scope(covers=scope_d.get("covers", []), tested=scope_d.get("tested", [])),
        falsifiers=spec.get("falsifiers", []),
    )


def evaluate_file(path: pathlib.Path) -> Optional[dict]:
    try:
        spec = yaml.safe_load(path.read_text()) or {}
    except (yaml.YAMLError, OSError):
        return None
    if not spec.get("children"):
        return None
    out = _grade_claim(spec, {})
    out["id"] = path.stem
    return out


def list_claims() -> list[dict]:
    """Grade every claim file under learning/claims/, live."""
    if not CLAIMS_DIR.is_dir():
        return []
    out = []
    for path in sorted(CLAIMS_DIR.glob("*.yaml")):
        graded = evaluate_file(path)
        if graded is not None:
            out.append(graded)
    return out
