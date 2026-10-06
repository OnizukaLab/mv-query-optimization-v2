"""Background execution of ``scripts/run_experiment.py`` with log streaming.

One experiment runs at a time (they share the database). Each writes its results to its own
``Output/runs/<run_id>/``; job metadata and logs are persisted under ``Output/web_jobs/<id>/``.
"""

import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from api.schemas import ExperimentRequest
from api.services.progress import ProgressTracker
from src.utils.run_layout import new_run_id

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_JOBS_DIR = PROJECT_ROOT / "Output" / "web_jobs"


class ExperimentBusyError(RuntimeError):
    """An experiment is already running."""


class JobNotFoundError(KeyError):
    """Unknown job id."""


@dataclass
class Job:
    """State of a single experiment run."""

    id: str
    request: ExperimentRequest
    command: list[str]
    run_id: str
    status: str = "running"  # running | completed | failed | stopped
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    return_code: int | None = None
    logs: list[str] = field(default_factory=list)
    tracker: ProgressTracker = field(default_factory=ProgressTracker)
    process: subprocess.Popen[str] | None = None
    stop_requested: bool = False

    def summary(self) -> dict[str, Any]:
        """JSON-serializable job description (without logs)."""
        return {
            "id": self.id,
            "run_id": self.run_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "return_code": self.return_code,
            "request": self.request.model_dump(),
            "progress": self.tracker.snapshot(),
            "log_lines": len(self.logs),
        }


def build_command(req: ExperimentRequest, run_id: str) -> list[str]:
    """Build the run_experiment.py argv (no shell involved)."""
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "run_experiment.py"),
        "--algorithms",
        *req.algorithms,
        "--phases",
        *req.phases,
        "--storage-limit",
        str(req.storage_limit_mb * 1024 * 1024),  # script expects bytes
        "--insert-queries",
        str(req.insert_queries),
        "--workload-type",
        req.workload_type,
        "--run-id",
        run_id,
    ]
    if req.verbose:
        cmd.append("--verbose")
    return cmd


class ExperimentManager:
    """Starts, tracks and stops experiment subprocesses."""

    def __init__(self, jobs_dir: Path = DEFAULT_JOBS_DIR):
        self._jobs_dir = jobs_dir
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def start(self, req: ExperimentRequest) -> Job:
        """Launch an experiment.

        Raises:
            ExperimentBusyError: If another experiment is running.
        """
        with self._lock:
            if any(j.status == "running" for j in self._jobs.values()):
                raise ExperimentBusyError("An experiment is already running")
            job_id = uuid.uuid4().hex[:12]
            run_id = f"{new_run_id(req.workload_type)}_{job_id[:6]}"
            job = Job(id=job_id, request=req, command=build_command(req, run_id), run_id=run_id)
            job.tracker.total_algorithms = len(req.algorithms)
            self._jobs[job.id] = job
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job

    def _run(self, job: Job) -> None:
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        try:
            job.process = subprocess.Popen(
                job.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(PROJECT_ROOT),
                env=env,
                start_new_session=True,  # own process group so stop kills children too
            )
            if job.stop_requested:  # stop arrived before the process existed
                self._terminate(job)
            assert job.process.stdout is not None
            for line in job.process.stdout:
                line = line.rstrip("\n")
                job.logs.append(line)
                job.tracker.feed(line)
            job.return_code = job.process.wait()
            final = (
                "stopped" if job.stop_requested else "completed" if job.return_code == 0 else "failed"
            )
        except OSError as e:
            logger.error(f"Failed to run experiment {job.id}: {e}")
            job.logs.append(f"[ERROR] {e}")
            final = "failed"
        job.finished_at = time.time()
        if final == "completed":
            job.tracker.progress = 100.0
        # Publish the terminal status last so SSE readers see consistent final state.
        job.status = final
        self._persist(job)

    def _persist(self, job: Job) -> None:
        try:
            d = self._jobs_dir / job.id
            d.mkdir(parents=True, exist_ok=True)
            (d / "job.json").write_text(json.dumps(job.summary(), indent=2))
            (d / "log.txt").write_text("\n".join(job.logs))
        except OSError as e:
            logger.warning(f"Could not persist job {job.id}: {e}")

    def stop(self, job_id: str) -> Job:
        """Terminate a running experiment (SIGTERM to its process group)."""
        job = self.get(job_id)
        if job.status == "running":
            job.stop_requested = True
            self._terminate(job)
        return job

    @staticmethod
    def _terminate(job: Job) -> None:
        if job.process is None:
            return  # _run() re-checks stop_requested right after spawning
        try:
            os.killpg(job.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    def get(self, job_id: str) -> Job:
        """Return an in-memory job.

        Raises:
            JobNotFoundError: If unknown.
        """
        try:
            return self._jobs[job_id]
        except KeyError:
            raise JobNotFoundError(job_id) from None

    def list_summaries(self) -> list[dict[str, Any]]:
        """Jobs from this process plus persisted ones, newest first."""
        summaries = {j.id: j.summary() for j in self._jobs.values()}
        if self._jobs_dir.exists():
            for f in self._jobs_dir.glob("*/job.json"):
                if f.parent.name in summaries:
                    continue
                try:
                    summaries[f.parent.name] = json.loads(f.read_text())
                except (OSError, json.JSONDecodeError):
                    continue
        return sorted(summaries.values(), key=lambda s: s["started_at"], reverse=True)

    def get_summary(self, job_id: str) -> dict[str, Any]:
        """Summary for a job from memory or disk.

        Raises:
            JobNotFoundError: If unknown.
        """
        if job_id in self._jobs:
            return self._jobs[job_id].summary()
        f = self._jobs_dir / job_id / "job.json"
        if f.parent.resolve().parent != self._jobs_dir.resolve() or not f.exists():
            raise JobNotFoundError(job_id)
        try:
            return json.loads(f.read_text())
        except (OSError, json.JSONDecodeError) as e:
            raise JobNotFoundError(job_id) from e

    def read_logs(self, job_id: str) -> list[str]:
        """Logs for a job, from memory or from disk for past runs."""
        if job_id in self._jobs:
            return list(self._jobs[job_id].logs)
        log = self._jobs_dir / job_id / "log.txt"
        if log.parent.resolve().parent != self._jobs_dir.resolve() or not log.exists():
            raise JobNotFoundError(job_id)
        return log.read_text().splitlines()
