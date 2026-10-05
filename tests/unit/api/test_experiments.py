"""Unit tests for experiment execution, progress parsing and SSE (no database)."""

import sys
import time

import pytest
from fastapi.testclient import TestClient

from api.deps import get_experiment_manager
from api.main import app
from api.schemas import ExperimentRequest
from api.services import experiment_service
from api.services.experiment_service import ExperimentBusyError, ExperimentManager, build_command
from api.services.progress import ProgressTracker

pytestmark = pytest.mark.unit


def make_request(**kw):
    base = dict(algorithms=["frequency"], phases=["query_parsing", "optimization"])
    return ExperimentRequest(**{**base, **kw})


def test_build_command_converts_mb_to_bytes_and_has_no_shell_input():
    cmd = build_command(make_request(storage_limit_mb=10, algorithms=["normal", "bigsubs"]))
    assert cmd[cmd.index("--storage-limit") + 1] == str(10 * 1024 * 1024)
    assert cmd[cmd.index("--algorithms") + 1 : cmd.index("--phases")] == ["normal", "bigsubs"]


@pytest.mark.parametrize("bad", [{"algorithms": ["rm -rf"]}, {"algorithms": []}, {"phases": ["x"]}])
def test_request_rejects_unknown_values(bad):
    with pytest.raises(ValueError):
        make_request(**bad)


def test_progress_tracker_advances_through_phases():
    t = ProgressTracker(total_algorithms=2)
    t.feed("Running ILP: frequency")
    t.feed("[1/6] Parsing queries...")
    p1 = t.progress
    t.feed("[4/6] Creating MVs in database...")
    t.feed("[3/10] Creating leaf_mv_3")
    assert t.progress > p1
    t.feed("[6/6] Executing benchmark...")
    t.feed("Executed 5/10 queries")
    assert t.phase_progress["benchmark"] == 50.0
    t.feed("✓ Completed frequency in 12.30 seconds")
    assert t.algorithms_done == 1 and t.progress >= 50.0
    t.feed("Running ILP: normal")
    assert t.current_algorithm == "normal" and t.phase_step == 0


@pytest.fixture
def manager(tmp_path, monkeypatch):
    def fake_command(req):
        code = "print('[1/6] Parsing queries...');print('hello');print('\\u2713 Completed x in 1.00 seconds')"
        return [sys.executable, "-c", code]

    monkeypatch.setattr(experiment_service, "build_command", fake_command)
    return ExperimentManager(jobs_dir=tmp_path)


def wait_done(job, timeout=10):
    end = time.time() + timeout
    while job.status == "running" and time.time() < end:
        time.sleep(0.05)


def test_job_runs_persists_and_reloads(manager, tmp_path):
    job = manager.start(make_request())
    wait_done(job)
    assert job.status == "completed" and job.tracker.progress == 100.0
    assert "hello" in job.logs
    fresh = ExperimentManager(jobs_dir=tmp_path)  # simulates server restart
    assert fresh.get_summary(job.id)["status"] == "completed"
    assert "hello" in fresh.read_logs(job.id)
    assert [s["id"] for s in fresh.list_summaries()] == [job.id]


def test_second_experiment_is_rejected_while_running(tmp_path, monkeypatch):
    monkeypatch.setattr(
        experiment_service,
        "build_command",
        lambda req: [sys.executable, "-c", "import time; time.sleep(30)"],
    )
    m = ExperimentManager(jobs_dir=tmp_path)
    job = m.start(make_request())
    try:
        with pytest.raises(ExperimentBusyError):
            m.start(make_request())
    finally:
        m.stop(job.id)
        wait_done(job)
    assert job.status == "stopped"


def test_path_traversal_is_not_found(manager):
    with pytest.raises(experiment_service.JobNotFoundError):
        manager.read_logs("..")


def test_sse_streams_logs_and_done(manager):
    app.dependency_overrides[get_experiment_manager] = lambda: manager
    try:
        client = TestClient(app)
        job_id = client.post("/experiments", json=make_request().model_dump()).json()["id"]
        with client.stream("GET", f"/experiments/{job_id}/events") as r:
            body = "".join(r.iter_text())
        assert "event: log" in body and '"hello"' in body
        assert body.rstrip().endswith('event: done\ndata: {"status": "completed"}')
        assert client.get(f"/experiments/{job_id}/logs").text.splitlines()[1] == "hello"
        assert client.get("/experiments/nope").status_code == 404
    finally:
        app.dependency_overrides.clear()
