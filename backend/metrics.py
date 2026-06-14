"""Per-run metric extraction, wrapping the playground's analyze_run.extract.

analyze_run caches by wandb id (invalidated on wandb-summary.json mtime), so
repeated calls are cheap. For the in-flight run we expose a cache-bypassing
path that re-reads output.log (which grows live) for an up-to-date curve.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Optional

from . import config, metrics_config, playground


def _raw_summary(log_run: pathlib.Path) -> dict:
    """The full wandb-summary.json (extract() keeps only a whitelist)."""
    ar = playground.analyze_run()
    wb = ar.find_wandb_dir(log_run)
    if wb is None:
        return {}
    f = wb / "files" / "wandb-summary.json"
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _training_metrics(d: dict) -> dict:
    s = d.get("summary", {}) or {}
    return {
        "kl_train": s.get("training/kl_mean"),
        "kl_ep": s.get("episode/kl_mean"),
        "v_loss": s.get("training/v_loss"),
        "entropy_loss": s.get("training/entropy_loss"),
        "mean_std": s.get("training/policy_dist_mean_std"),
        "max_std": s.get("training/policy_dist_max_std"),
        "sps": s.get("training/sps"),
    }


def divergence(d: dict) -> dict:
    """Per-run divergence verdict, using early_stop's KL_CEILING / COLLAPSE_FRAC
    semantics applied post-hoc to the run's curve + final KL.

    flag: 'ok' | 'warn' (one symptom) | 'diverged' (KL explosion AND collapse).
    """
    ar = playground.analyze_run()
    es = playground.early_stop()
    curve = d.get("curve") or []
    inst = ar._instability(curve) if curve else {"max_drop": None, "low_reward_frac": None}
    s = d.get("summary", {}) or {}
    kl = s.get("training/kl_mean")
    max_drop = inst.get("max_drop")
    peak = max((y for _, y in curve), default=0.0)

    kl_explosion = kl is not None and kl > es.KL_CEILING
    collapsed = (
        max_drop is not None and peak > 5 and max_drop > es.COLLAPSE_FRAC * peak
    )
    reasons = []
    if kl_explosion:
        reasons.append(f"KL {kl:.3f} > {es.KL_CEILING}")
    if collapsed:
        reasons.append(f"reward dropped {max_drop:.1f} from peak {peak:.1f}")

    if kl_explosion and collapsed:
        flag = "diverged"
    elif kl_explosion or collapsed:
        flag = "warn"
    else:
        flag = "ok"
    return {
        "flag": flag,
        "kl": kl,
        "max_drop": max_drop,
        "low_frac": inst.get("low_reward_frac"),
        "reasons": reasons,
    }


def summarize(exp_name: str, success_metric: str = metrics_config.DEFAULT_SUCCESS_METRIC) -> Optional[dict]:
    """Compact summary for a single run. `reward` and `success` each carry both
    an eval and a train value; `success` is the chosen success-metric."""
    ar = playground.analyze_run()
    log_run = ar.resolve(exp_name)
    if log_run is None:
        return None
    d = ar.extract(log_run)
    if "error" in d:
        return {"name": exp_name, "error": d["error"]}
    raw = _raw_summary(log_run)
    return {
        "name": d.get("name", exp_name),
        "env_name": d.get("env_name"),
        "completed": d.get("completed"),
        "n_evals": d.get("n_evals"),
        "final_step": d.get("final_step"),
        "curve": d.get("curve") or [],
        "reward": metrics_config.reward_values(raw),          # {eval, train}
        "success": metrics_config.success_values(raw, success_metric),  # {id,label,kind,eval,train}
        "training": _training_metrics(d),
        "divergence": divergence(d),
    }


def detail(exp_name: str) -> Optional[dict]:
    """Full analyze_run dict for the drill-in view (adds env_config, reward
    breakdown, checkpoint config), plus eval/train reward + every success metric."""
    ar = playground.analyze_run()
    log_run = ar.resolve(exp_name)
    if log_run is None:
        return None
    d = ar.extract(log_run)
    if "error" not in d:
        raw = _raw_summary(log_run)
        d = {
            **d,
            "indicators": {
                "reward": metrics_config.reward_values(raw),
                "success_metrics": metrics_config.all_success_values(raw),
            },
            "divergence": divergence(d),
        }
    return d
