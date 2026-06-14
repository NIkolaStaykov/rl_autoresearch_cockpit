#!/usr/bin/env bash
# Launch the experiment cockpit (backend serves the built SPA on one port).
#
#   ./run.sh                 # build frontend + serve on :8770
#   PORT=9000 ./run.sh       # different port
#   PLAYGROUND_ROOT=... ./run.sh
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8770}"
export PATH="$HOME/.local/bin:$PATH"
export PLAYGROUND_ROOT="${PLAYGROUND_ROOT:-/local/home/nstaykov/workspace/mujoco_playground}"

echo "building frontend…"
( cd frontend && npm run build >/dev/null )

echo "serving cockpit at http://localhost:${PORT}  (PLAYGROUND_ROOT=${PLAYGROUND_ROOT})"
exec uv run uvicorn backend.server:app --port "$PORT" --host 0.0.0.0
