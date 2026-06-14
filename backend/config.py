"""Static configuration for the experiment cockpit.

Everything is derived live from the playground repo's own files (queue YAMLs,
logs/_queue/*/status.json, wandb/). The cockpit persists nothing except
human-authored hypotheses/conclusions, kept in NOTES_DIR.
"""

import os
import pathlib

# Root of the mujoco_playground checkout we are observing. Override with the
# PLAYGROUND_ROOT env var to point at a different checkout.
PLAYGROUND_ROOT = pathlib.Path(
    os.environ.get(
        "PLAYGROUND_ROOT", "/local/home/nstaykov/workspace/mujoco_playground"
    )
).expanduser().resolve()

LOGS = PLAYGROUND_ROOT / "logs"
WANDB = PLAYGROUND_ROOT / "wandb"
QUEUES = PLAYGROUND_ROOT / "learning" / "queues"
QUEUE_LOGS = LOGS / "_queue"

# Where the playground's helper scripts live, so we can import them.
LEARNING_DIR = PLAYGROUND_ROOT / "learning"
CLAUDE_DIR = PLAYGROUND_ROOT / ".claude"

# Cockpit-owned, human-authored notes (the only thing we persist).
COCKPIT_HOME = pathlib.Path(__file__).resolve().parent.parent
NOTES_DIR = COCKPIT_HOME / "notes"
