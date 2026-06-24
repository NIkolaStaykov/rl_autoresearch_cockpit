"""Which logged quantities the cockpit treats as the reward and the success
indicator, in both TRAIN and EVAL flavors.

Reward and success each exist in two namespaces:
  - eval/*    : deterministic eval rollouts (the decision metric)
  - episode/* : rollout-time training metrics (needs log_training_metrics)

The success indicator — the thing that decides whether a run "worked" — is fixed
to the held-success fraction (success%): the fraction of eval steps that met the
success marker, logged every step whether or not it feeds the reward.
"""

from __future__ import annotations

REWARD = {"eval": "eval/episode_reward", "train": "episode/sum_reward"}

# The single success indicator: held-success %, in eval and train flavors.
SUCCESS = {
    "label": "success",
    "kind": "pct",  # 0-1 fraction, shown as a percentage
    "eval": "eval/episode_reward/success_per_step",
    "train": "episode/reward/success_per_step",
}


def reward_values(raw: dict) -> dict:
    return {"eval": raw.get(REWARD["eval"]), "train": raw.get(REWARD["train"])}


def success_values(raw: dict) -> dict:
    return {
        "label": SUCCESS["label"],
        "kind": SUCCESS["kind"],
        "eval": raw.get(SUCCESS["eval"]),
        "train": raw.get(SUCCESS["train"]),
    }
