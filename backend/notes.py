"""Human-authored conclusions per queue-run — the one thing the cockpit persists
(everything else is read-through from the playground). Stored as JSON under
NOTES_DIR, keyed by queue-run id. Kept separate from discovery/control to avoid
import cycles.
"""

from __future__ import annotations

import datetime
import json

from . import config


def _path(queue_id: str):
    return config.NOTES_DIR / f"{queue_id}.json"


def read(queue_id: str):
    f = _path(queue_id)
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text())
    except json.JSONDecodeError:
        return None


def write(queue_id: str, text: str):
    config.NOTES_DIR.mkdir(parents=True, exist_ok=True)
    data = {"text": text, "updated_at": datetime.datetime.now().isoformat()}
    _path(queue_id).write_text(json.dumps(data, indent=2))
    return data
