"""Which logged quantities the cockpit treats as the reward and the success
indicator, in both TRAIN and EVAL flavors.

Reward and success each exist in two namespaces:
  - eval/*    : deterministic eval rollouts (the decision metric)
  - episode/* : rollout-time training metrics (needs log_training_metrics)

The success indicator — the thing that decides whether a run "worked" — is
configurable (settings.py holds the global default; a queue can override it via
its hypothesis `metric`). A run often logs a per-step success marker that may or
may not feed the reward; the fraction of successful eval steps is the headline.
"""

from __future__ import annotations

REWARD = {"eval": "eval/episode_reward", "train": "episode/sum_reward"}

# id -> display + the eval/train keys + value kind ('pct' for 0-1 fractions).
SUCCESS_METRICS: dict[str, dict] = {
    "success_per_step": {
        "label": "success",
        "kind": "pct",
        "eval": "eval/episode_reward/success_per_step",
        "train": "episode/reward/success_per_step",
    },
    "success_count": {
        "label": "succ-steps/ep",
        "kind": "num",
        "eval": "eval/episode_success_count",
        "train": "episode/success_count",
    },
    "consecutive_success_steps": {
        "label": "consec succ",
        "kind": "num",
        "eval": "eval/episode_consecutive_success_steps",
        "train": "episode/consecutive_success_steps",
    },
}

DEFAULT_SUCCESS_METRIC = "success_per_step"


def resolve_success_id(metric: str | None, global_default: str) -> str:
    """Map a queue's hypothesis `metric` to a known success-metric id.

    A concrete id wins; the legacy alias 'success' (and 'reward', whose success
    column is incidental) fall back to the global default.
    """
    if metric in SUCCESS_METRICS:
        return metric
    return global_default if global_default in SUCCESS_METRICS else DEFAULT_SUCCESS_METRIC


def reward_values(raw: dict) -> dict:
    return {"eval": raw.get(REWARD["eval"]), "train": raw.get(REWARD["train"])}


def success_values(raw: dict, metric_id: str) -> dict:
    m = SUCCESS_METRICS.get(metric_id) or SUCCESS_METRICS[DEFAULT_SUCCESS_METRIC]
    return {
        "id": metric_id,
        "label": m["label"],
        "kind": m["kind"],
        "eval": raw.get(m["eval"]),
        "train": raw.get(m["train"]),
    }


def all_success_values(raw: dict) -> dict:
    """eval+train value for every known success metric (for the run page)."""
    return {mid: success_values(raw, mid) for mid in SUCCESS_METRICS}


def registry() -> list[dict]:
    return [{"id": mid, "label": m["label"], "kind": m["kind"]} for mid, m in SUCCESS_METRICS.items()]
