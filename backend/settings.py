"""Cockpit-global settings (just the default success metric for now). Persisted
to state/settings.json; merged over DEFAULTS so new keys appear automatically.
"""

from __future__ import annotations

import json

from . import config, metrics_config

DEFAULTS = {"success_metric": metrics_config.DEFAULT_SUCCESS_METRIC}

_PATH = config.COCKPIT_HOME / "state" / "settings.json"


def read() -> dict:
    data = dict(DEFAULTS)
    if _PATH.exists():
        try:
            data.update(json.loads(_PATH.read_text()))
        except json.JSONDecodeError:
            pass
    # Guard against a stale/invalid metric id.
    if data.get("success_metric") not in metrics_config.SUCCESS_METRICS:
        data["success_metric"] = metrics_config.DEFAULT_SUCCESS_METRIC
    return data


def write(patch: dict) -> dict:
    data = read()
    data.update({k: v for k, v in patch.items() if k in DEFAULTS})
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps(data, indent=2))
    return read()
