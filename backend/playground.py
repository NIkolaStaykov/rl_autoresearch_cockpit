"""Bridge to the playground repo's own modules.

We reuse the canonical implementations rather than re-deriving them:
  - run_queue.parse_queue  -> the authoritative sweep expansion
  - analyze_run.resolve/extract -> the authoritative per-run metric extraction

Both modules are stdlib+pyyaml only, so importing them here pulls in no heavy
deps (no jax/mujoco). We add the playground dirs to sys.path lazily.
"""

import sys

from . import config

_loaded = {}


def _ensure_path():
    for p in (config.LEARNING_DIR, config.CLAUDE_DIR):
        sp = str(p)
        if sp not in sys.path:
            sys.path.insert(0, sp)


def run_queue():
    if "run_queue" not in _loaded:
        _ensure_path()
        import run_queue as rq  # noqa: PLC0415

        _loaded["run_queue"] = rq
    return _loaded["run_queue"]


def analyze_run():
    if "analyze_run" not in _loaded:
        _ensure_path()
        import analyze_run as ar  # noqa: PLC0415

        _loaded["analyze_run"] = ar
    return _loaded["analyze_run"]


def early_stop():
    """The divergence-detection thresholds (KL_CEILING, COLLAPSE_FRAC, …)."""
    if "early_stop" not in _loaded:
        _ensure_path()
        import early_stop as es  # noqa: PLC0415

        _loaded["early_stop"] = es
    return _loaded["early_stop"]
