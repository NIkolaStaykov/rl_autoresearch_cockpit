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

# Per-experiment editable copies of scheduled queues. Each scheduled entry gets
# its own copy here (logs/_scheduled/<entry_id>/<stem>.yaml) so it can be edited
# without touching the learning/queues template, and so the file is bind-mounted
# into the dev containers where run_queue.py launches it. It's the ground truth
# for that specific scheduled experiment.
QUEUE_STAGE = LOGS / "_scheduled"

# Where the playground's helper scripts live, so we can import them.
LEARNING_DIR = PLAYGROUND_ROOT / "learning"
CLAUDE_DIR = PLAYGROUND_ROOT / ".claude"

# Cockpit-owned, human-authored notes (the only thing we persist).
COCKPIT_HOME = pathlib.Path(__file__).resolve().parent.parent
NOTES_DIR = COCKPIT_HOME / "notes"

# Optional env file sourced inside the container before each launch (e.g. for
# WANDB_API_KEY). Defaults to the bind-mount root (the workspace dir above the
# repo), so it needs no gitignoring and resolves to the same path in both
# containers. Override with COCKPIT_LAUNCH_ENV.
LAUNCH_ENV_FILE = pathlib.Path(
    os.environ.get("COCKPIT_LAUNCH_ENV", str(PLAYGROUND_ROOT.parent / ".cockpit.env"))
).expanduser()
