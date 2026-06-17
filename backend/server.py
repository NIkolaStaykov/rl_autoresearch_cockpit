"""Experiment cockpit API.

Stateless read-through over the playground's queue YAMLs, logs/_queue status
files and wandb. Run with:

    PLAYGROUND_ROOT=/path/to/mujoco_playground \
        uv run uvicorn backend.server:app --reload --port 8000
"""

from __future__ import annotations

import pathlib

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import claims, config, control, discovery, metrics, metrics_config, notes, settings

app = FastAPI(title="Experiment Cockpit")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "playground_root": str(config.PLAYGROUND_ROOT),
        "queue_logs_exists": config.QUEUE_LOGS.is_dir(),
    }


@app.get("/api/queues")
def queues():
    return discovery.list_queues()


@app.get("/api/queues/{name}")
def queue_detail(name: str, with_metrics: bool = True):
    d = discovery.queue_detail(name, with_metrics=with_metrics)
    if d is None:
        raise HTTPException(404, f"queue-run {name!r} not found")
    return d


@app.get("/api/runs/{exp_name}")
def run_detail(exp_name: str):
    d = metrics.detail(exp_name)
    if d is None:
        raise HTTPException(404, f"run {exp_name!r} not found")
    return d


@app.get("/api/queues/{name}/runs/{idx}/log", response_class=PlainTextResponse)
def run_log(name: str, idx: int):
    """Raw training log for one queue run -- backup/debug view (opened in a tab)."""
    txt = discovery.run_log_text(name, idx)
    if txt is None:
        raise HTTPException(404, f"no log for run {idx} in queue {name!r}")
    return txt


@app.get("/api/queues/{name}/log", response_class=PlainTextResponse)
def queue_log(name: str):
    """Raw orchestrator (run_queue.py) log for a queue-run -- the fallback view for
    when the queue itself is failing. 404 if launched outside the cockpit."""
    txt = discovery.queue_log_text(name)
    if txt is None:
        raise HTTPException(404, f"no orchestrator log for queue {name!r}")
    return txt


# --- control (launch / stop / resume) --------------------------------------

class LaunchBody(BaseModel):
    queue: str
    start_from: int | None = None


class ResumeBody(BaseModel):
    n: int
    steps: int
    source_dir: str | None = None


class StopBody(BaseModel):
    container: str | None = None


class ConclusionBody(BaseModel):
    text: str


class SaveQueueBody(BaseModel):
    filename: str
    content: str
    overwrite: bool = False


class SettingsBody(BaseModel):
    success_metric: str | None = None


@app.get("/api/settings")
def get_settings():
    return {
        **settings.read(),
        "success_metrics": metrics_config.registry(),
    }


@app.put("/api/settings")
def put_settings(body: SettingsBody):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    return {**settings.write(patch), "success_metrics": metrics_config.registry()}


@app.get("/api/queue_specs")
def queue_specs():
    return discovery.list_queue_specs()


@app.get("/api/claims")
def list_claims():
    """Cross-queue claims, graded live from learning/claims/*.yaml."""
    return claims.list_claims()


@app.get("/api/control/status")
def control_status():
    return control.status()


@app.post("/api/control/launch")
def control_launch(body: LaunchBody):
    try:
        return control.launch(body.queue, body.start_from)
    except control.Busy as e:
        raise HTTPException(409, str(e))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.post("/api/control/resume")
def control_resume(body: ResumeBody):
    try:
        return control.resume(body.n, body.steps, body.source_dir)
    except control.Busy as e:
        raise HTTPException(409, str(e))


@app.post("/api/control/stop")
def control_stop(body: StopBody | None = None):
    try:
        return control.stop(body.container if body else None)
    except control.NotRunning as e:
        raise HTTPException(409, str(e))


@app.put("/api/queues/{name}/conclusion")
def put_conclusion(name: str, body: ConclusionBody):
    return notes.write(name, body.text)


@app.post("/api/queues/{name}/plan-next")
def plan_next(name: str):
    return control.plan_next_draft(name)


@app.post("/api/queue_specs/save")
def save_queue(body: SaveQueueBody):
    try:
        return control.save_queue(body.filename, body.content, body.overwrite)
    except (ValueError, FileExistsError) as e:
        raise HTTPException(409, str(e))


# --- static frontend (built SPA), optional ---------------------------------
_DIST = config.COCKPIT_HOME / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/")
    def _index():
        return FileResponse(_DIST / "index.html")
