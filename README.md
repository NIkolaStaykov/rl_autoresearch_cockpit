# Experiment Cockpit

A small frontend for organizing and monitoring `mujoco_playground` training
**queues**. Each queue (`learning/run_queue.py` + `learning/queues/*.yaml`) is
one experiment — a sweep over env × params × seeds with an expected relation
between results. The cockpit joins, on one screen:

- **Plan** — the sweep, expanded via the playground's own `run_queue.parse_queue`.
- **Execution state** — `logs/_queue/<queue>-<ts>/status.json` + live process detection.
- **Metrics** — per-run reward/success/kl/v_loss via `.claude/analyze_run.extract`.
- **Hypothesis** — the queue YAML's prose comment (and, when present, a structured
  `hypothesis:` block).

It is **stateless read-through**: nothing is duplicated into a database. The only
thing it will ever persist is human-authored conclusions (`notes/`, M3).

## Run

```bash
./run.sh                      # builds the SPA and serves it on http://localhost:8770
PORT=9000 ./run.sh            # the default port 8000 is used by the Policy Analyzer
PLAYGROUND_ROOT=/path ./run.sh
```

Then open the printed URL. The board polls every few seconds, so a running
queue updates live.

### Dev (hot reload)

```bash
# terminal 1 — backend
PLAYGROUND_ROOT=/local/home/nstaykov/workspace/mujoco_playground \
  uv run uvicorn backend.server:app --reload --port 8770
# terminal 2 — frontend (proxies /api -> :8770… set the proxy target in vite.config.js)
cd frontend && npm run dev
```

> Note: `vite.config.js` proxies `/api` to `:8770` (the backend default). Match
> them if you change the port, or just use `./run.sh` (single port, no proxy).

## Layout

```
backend/
  config.py      PLAYGROUND_ROOT + derived paths
  playground.py  sys.path bridge to run_queue / analyze_run (no heavy deps)
  metrics.py     wraps analyze_run.extract
  discovery.py   plan × status × ps join (board + queue detail)
  server.py      FastAPI routes
frontend/        Vite + React SPA (board → queue grid → run drill-in)
run.sh           build + serve on one port
```

## Status

- **M1 (read-only spine):** done — board, queue sweep-matrix, run drill-in.
- **M2 (live + judgment):** done — live in-flight metrics + progress (resolves the
  running run's exp name from its queue log; polls while training), divergence flags
  (`early_stop` KL/collapse semantics) on every run + run-detail banner, and a
  structured-`hypothesis:`-block **verdict** (holds / partial / contradicted / pending)
  with an expected-vs-actual chart. Live updates via polling rather than SSE.
  *Deferred:* reward normalization by env theoretical-max (needs the env module,
  which would pull in heavy deps — revisit via a small subprocess).
- **M3 (control):** done — launch / stop / resume queues from the UI, per-queue
  **conclusion notes** (persisted under `notes/`), and a **plan-next** scaffold that
  drafts a follow-up YAML from a queue and saves it to `learning/queues/`.
  Launches are **dispatched into the dev containers, one per GPU** (`backend/containers.py`):
  on Launch the cockpit picks a container whose bound GPU is free (`nvidia-smi`
  memory < 2 GiB and no `run_queue.py` already inside) and `docker exec -d`s the queue
  with the workspace venv; the orchestrator log lands on the shared mount under
  `state/launch_logs/`. Two GPUs ⇒ up to two queues at once; Launch is disabled when
  none is free. Stop sends **SIGINT** to `run_queue.py` inside the chosen container so
  it kills its training child and writes `status.json`.

  **Credentials / launch env:** before exec'ing, each launch sources the file at
  `LAUNCH_ENV_FILE` (if present) with `set -a`, so `KEY=value` lines there (e.g.
  `WANDB_API_KEY=…`) are exported into the training process. Default location is
  `<workspace>/.cockpit.env` — the bind-mount root *above* the repo, so it needs
  no gitignoring, applies to both containers, and survives container recreation.
  Override with the `COCKPIT_LAUNCH_ENV` env var.

### Control endpoints

`GET /api/queue_specs`, `GET /api/queue_specs/{stem}` (live source YAML),
`GET /api/control/status`, `POST /api/control/{launch,resume,stop}`,
`GET|POST /api/schedule`, `DELETE /api/schedule/{id}`,
`PUT /api/queues/{id}/conclusion`, `POST /api/queues/{id}/plan-next`, `POST /api/queue_specs/save`.
Launch logs are tee'd to `state/launch_logs/`.

### Schedule (run later)

The board's **Schedule queue** button adds a queue to a persisted pending list
(`state/schedule.json`) instead of requiring a free GPU up front. A background
dispatcher thread (`backend/schedule.py`, ticking every few seconds) launches the
head entry onto a GPU — sizing num_envs to free VRAM via `control.launch` — as
soon as one frees up, so you can line up an overnight batch and walk away. This is
the *plan* of what will run; it is the only mutable state the cockpit owns besides
notes.

The board has two tabs: **experiments** (executed queue-runs, grouped by task) and
**scheduled** — the pending queue only (position, when enqueued, the *next* entry
waiting for a GPU), each removable. It is deliberately *not* a log of what already
ran; that stays in the experiments tab.

### Queue-spec snapshot

The experiment view's **view queue** button shows the **exact spec a run executed**,
not a same-named file from `learning/queues/` that may have been edited since.
`run_queue.py` snapshots its source queue into the run's log dir as
`logs/_queue/<run>/queue.yaml` before any run starts; `GET /api/queues/{id}/spec`
serves that snapshot. Runs predating the snapshot fall back to the live file,
flagged `snapshot:false` so the UI warns the bytes may differ.

### Reward / success indicator

Reward and the success indicator each have a **train** and **eval** flavor
(`episode/sum_reward` vs `eval/episode_reward`; `episode/reward/success_per_step`
vs `eval/episode_reward/success_per_step`). A global **eval ⇄ train toggle** in the
top bar switches the whole view; eval is the decision flavor (verdicts are computed
on eval).

The **success metric** — the quantity that decides whether a run worked — is fixed
to **held-success %** (`success_per_step`, defined in `backend/metrics_config.py`):
the fraction of eval steps that met the success marker. That marker is logged every
step whether or not it feeds the reward, so success% sits alongside total reward as
an independent indicator.

### The structured `hypothesis:` block

Optional, additive to a queue YAML (ignored by `run_queue.py`). Example in
`learning/queues/pinch_qbias_sweep.yaml`:

```yaml
hypothesis:
  axis: obs_noise.bias_scales.joint_pos   # independent variable (a swept param)
  group: sensor_bundle                    # split runs into series by this param
  metric: success                         # 'success' | 'reward' | a summary key
  expect:
    baseline: decreasing                  # trend of metric along axis
    proprio.target: flat
```

Trends are classified from ≥3 completed points per group (increasing / flat /
decreasing); fewer points → "insufficient" and the group doesn't count toward the
overall verdict.

## Requirements

- `node` (installed locally at `~/.local/opt`), `uv`.
- A `mujoco_playground` checkout at `PLAYGROUND_ROOT` with `logs/`, `wandb/`,
  `learning/queues/`, and `.claude/analyze_run.py`.
