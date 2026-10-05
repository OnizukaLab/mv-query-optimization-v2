"""Experiment endpoints: start/stop, history, and live log streaming (SSE)."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse

from api.deps import get_experiment_manager
from api.schemas import ExperimentRequest
from api.services.experiment_service import (
    ExperimentBusyError,
    ExperimentManager,
    JobNotFoundError,
)

router = APIRouter(prefix="/experiments", tags=["experiments"])

POLL_INTERVAL_S = 0.5
MAX_LINES_PER_BATCH = 500


def _sse(event: str, data: str, event_id: int | None = None) -> str:
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {data}\n\n"


@router.post("", status_code=201)
def start_experiment(
    req: ExperimentRequest, manager: ExperimentManager = Depends(get_experiment_manager)
) -> dict[str, Any]:
    """Start an experiment. 409 if one is already running."""
    try:
        return manager.start(req).summary()
    except ExperimentBusyError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.get("")
def list_experiments(
    manager: ExperimentManager = Depends(get_experiment_manager),
) -> list[dict[str, Any]]:
    """Experiment history, newest first."""
    return manager.list_summaries()


@router.get("/{job_id}")
def get_experiment(
    job_id: str, manager: ExperimentManager = Depends(get_experiment_manager)
) -> dict[str, Any]:
    """One experiment's status and progress."""
    try:
        return manager.get_summary(job_id)
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail="Experiment not found") from e


@router.post("/{job_id}/stop")
def stop_experiment(
    job_id: str, manager: ExperimentManager = Depends(get_experiment_manager)
) -> dict[str, Any]:
    """Request termination of a running experiment."""
    try:
        return manager.stop(job_id).summary()
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail="Experiment not found") from e


@router.get("/{job_id}/logs", response_class=PlainTextResponse)
def get_logs(job_id: str, manager: ExperimentManager = Depends(get_experiment_manager)) -> str:
    """Full log text (works for finished experiments from earlier sessions)."""
    try:
        return "\n".join(manager.read_logs(job_id))
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail="Experiment not found") from e


@router.get("/{job_id}/events")
async def stream_events(
    job_id: str,
    last_event_id: str | None = Header(default=None),
    manager: ExperimentManager = Depends(get_experiment_manager),
) -> StreamingResponse:
    """Server-Sent Events: ``log`` lines, ``progress`` snapshots, final ``done``.

    Reconnects resume from ``Last-Event-ID`` (the index of the last line received).
    """
    try:
        job = manager.get(job_id)
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail="Experiment not running in this session") from e
    try:
        cursor = int(last_event_id) + 1 if last_event_id is not None else 0
    except ValueError:
        cursor = 0

    async def gen() -> AsyncIterator[str]:
        nonlocal cursor
        while True:
            finished = job.status != "running"  # read before logs so no line is missed
            batch = job.logs[cursor : cursor + MAX_LINES_PER_BATCH]
            for line in batch:
                yield _sse("log", json.dumps(line), cursor)
                cursor += 1
            yield _sse("progress", json.dumps(job.summary()))
            if finished and cursor >= len(job.logs):
                yield _sse("done", json.dumps({"status": job.status}))
                return
            if not batch:
                await asyncio.sleep(POLL_INTERVAL_S)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
