"""Tests for the per-run output layout, workload identity and manifests (no database)."""

import json
import time

import pytest

from src.utils import run_layout as rl

pytestmark = pytest.mark.unit


def make_files(tmp_path, contents):
    files = []
    for name, text in contents.items():
        f = tmp_path / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
        files.append(str(f))
    return files


def test_workload_id_depends_on_content_not_location(tmp_path):
    a = make_files(tmp_path / "a", {"1a.json": "x", "1b.json": "y"})
    b = make_files(tmp_path / "b", {"1a.json": "x", "1b.json": "y"})
    # same relative names and bytes under different roots: same workload
    assert rl.compute_workload_id(a, tmp_path / "a") == rl.compute_workload_id(b, tmp_path / "b")


def test_workload_id_changes_with_content_membership_order_and_frequency(tmp_path):
    f = make_files(tmp_path, {"1a.json": "x", "1b.json": "y"})
    base = rl.compute_workload_id(f, tmp_path)
    assert rl.compute_workload_id(f[:1], tmp_path) != base  # subset
    assert rl.compute_workload_id(f[::-1], tmp_path) != base  # order = query index
    assert rl.compute_workload_id(f, tmp_path, {f[0]: 3}) != base  # RedBench repeats queries
    (tmp_path / "1b.json").write_text("changed")
    assert rl.compute_workload_id(f, tmp_path) != base  # edited query file


def test_run_ids_sort_chronologically_and_reject_path_tricks():
    early = rl.new_run_id("job", now=1_000_000_000)
    late = rl.new_run_id("job", now=1_000_000_000 + 86_400)
    assert early < late and early.endswith("_job")
    assert rl.new_run_id("redbench job/../x").count("/") == 0
    for bad in ["..", ".", "a/b", "", ".hidden", "x" * 200]:
        with pytest.raises(ValueError):
            rl.validate_run_id(bad)


def test_artifacts_dir_is_keyed_by_workload_and_insert_queries(tmp_path):
    assert rl.artifacts_dir(tmp_path, "abc", 1000) != rl.artifacts_dir(tmp_path, "abc", 10)
    assert rl.artifacts_dir(tmp_path, "abc", 1000) != rl.artifacts_dir(tmp_path, "def", 1000)


def test_manifest_roundtrip_and_missing(tmp_path):
    assert rl.RunManifest.read(tmp_path) is None
    m = rl.RunManifest(
        run_id="r",
        created_at=time.time(),
        status="running",
        workload={"id": "w", "label": "job"},
        params={"algorithms": ["normal"]},
    )
    m.write(tmp_path / "r")
    assert rl.RunManifest.read(tmp_path / "r") == m
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / rl.MANIFEST_NAME).write_text("{not json")
    assert rl.RunManifest.read(tmp_path / "bad") is None


def algo(d, name):
    (d / name / "optimization").mkdir(parents=True)
    (d / name / "optimization" / "result.json").write_text(json.dumps({"selected_views": []}))


def test_iter_result_sets_lists_runs_and_legacy_without_infrastructure_dirs(tmp_path):
    algo(tmp_path / "runs" / "20260101-000000_job", "normal")
    (tmp_path / "runs" / "empty").mkdir()
    algo(tmp_path, "normal")  # legacy: Output/<algo>
    algo(tmp_path / "exp1", "bigsubs")  # legacy named set
    algo(tmp_path / "artifacts" / "w_i1000", "normal")  # never a result set
    (tmp_path / "web_jobs" / "abc").mkdir(parents=True)

    sets = {s.set_id: s.kind for s in rl.iter_result_sets(tmp_path)}
    assert sets == {"20260101-000000_job": "run", "_root": "legacy", "exp1": "legacy"}


def test_find_result_set_does_not_trust_ids_as_paths(tmp_path):
    algo(tmp_path / "runs" / "r1", "normal")
    assert rl.find_result_set(tmp_path, "r1").path == tmp_path / "runs" / "r1"
    for bad in ["..", "runs/r1", "../x", ".hidden", "missing"]:
        assert rl.find_result_set(tmp_path, bad) is None


def test_workload_label_for_ceb_templates():
    from types import SimpleNamespace as NS

    s = NS(
        benchmark=NS(ceb_template="2a", ceb_limit=50, query_selection_mode="all_ceb", type="ceb")
    )
    assert rl.workload_label("ceb-1a", s) == "ceb-2a-50"
    assert rl.workload_label("job", s) == "job"
    assert rl.workload_label(None, s) == "all_ceb-ceb"
