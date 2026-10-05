"""Unit tests for result discovery and comparison (filesystem only)."""

import json

import pytest

from api.services.results_service import ResultNotFoundError, ResultsService

pytestmark = pytest.mark.unit


def write_algo(base, name, total_time, queries=10, workload="w", failed=0):
    d = base / name
    (d / "benchmark").mkdir(parents=True)
    (d / "optimization").mkdir()
    (d / "summary.json").write_text(
        json.dumps({"algorithm": name, "total_execution_time": 5, "phases": {"benchmark": 3}})
    )
    (d / "benchmark" / "benchmark_results.json").write_text(
        json.dumps(
            {
                "workload_type": workload,
                "total_queries": queries,
                "successful": queries - failed,
                "failed": failed,
                "total_time": total_time,
                "avg_time_per_query": total_time / queries,
                "group_results": {},
                "queries": [{"query_id": "1a"}],
            }
        )
    )
    (d / "optimization" / "result.json").write_text(
        json.dumps({"total_storage_mb": 1.5, "selected_views": [1, 2, 3], "metadata": {}})
    )


@pytest.fixture
def output(tmp_path):
    write_algo(tmp_path, "none", 100.0)
    write_algo(tmp_path, "normal", 50.0)
    (tmp_path / "exp1").mkdir()
    write_algo(tmp_path / "exp1", "bigsubs", 25.0, queries=5)
    (tmp_path / "logs").mkdir()  # not a result set
    return tmp_path


def test_lists_root_and_named_sets(output):
    sets = {s["id"]: s for s in ResultsService(output).list_sets()}
    assert set(sets) == {"_root", "exp1"}
    assert sets["_root"]["algorithms"] == ["none", "normal"]


def test_compare_computes_speedup_and_strips_heavy_fields(output):
    result = ResultsService(output).compare("_root")
    normal = next(a for a in result["algorithms"] if a["name"] == "normal")
    assert normal["speedup_vs_baseline"] == 2.0
    assert normal["optimization"]["num_selected_views"] == 3
    assert "queries" not in normal["benchmark"]
    assert result["baseline"] == "none"


def test_warns_on_mismatched_query_counts(output):
    write_algo(output / "exp1", "none", 10.0, queries=7, failed=1)
    warnings = ResultsService(output).compare("exp1")["warnings"]
    assert any("query counts" in w for w in warnings)
    assert any("failed" in w for w in warnings)


@pytest.mark.parametrize("bad", ["..", "a/b", ".hidden", "missing", "logs"])
def test_rejects_unknown_or_unsafe_ids(output, bad):
    with pytest.raises(ResultNotFoundError):
        ResultsService(output).compare(bad)


def test_speedup_is_none_when_baseline_ran_a_different_workload(output):
    write_algo(output / "exp1", "none", 10.0, queries=5, workload="other")
    by = {a["name"]: a for a in ResultsService(output).compare("exp1")["algorithms"]}
    assert by["bigsubs"]["speedup_vs_baseline"] is None
