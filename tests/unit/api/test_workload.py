"""Tests for the JOB workload index (uses the local dataset; skipped when it is absent)."""

from pathlib import Path

import pytest

from api.services.workload_service import NodeNotFoundError, WorkloadIndex
from config.settings import Settings

ROOT = Path(__file__).resolve().parents[3]
pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(
        not (ROOT / "dataset/RED_JSON/job/1a.json").exists(), reason="JOB plan dataset not available"
    ),
]


@pytest.fixture(scope="module")
def index():
    return WorkloadIndex(Settings(), ROOT)


def preorder(node):
    yield node
    for c in node.get("Plans", []):
        yield from preorder(c)


def test_snapshot_annotates_every_node_and_counts_sharing(index):
    snap = index.snapshot("8c")
    nodes = list(preorder(snap["plan"]))
    assert all("node_id" in n for n in nodes)
    assert set(snap["shared_counts"]) == {n["node_id"] for n in nodes}
    assert all(v >= 1 for v in snap["shared_counts"].values())


def test_node_lists_exactly_the_queries_that_contain_it(index):
    shared = max(index.snapshot("1a")["shared_counts"].items(), key=lambda kv: kv[1])[0]
    node = index.node(shared)
    ids = {q["id"] for q in node["queries"]}
    assert "1a" in ids
    for qid in ids:  # symmetric: every listed query's snapshot contains the node
        assert shared in index.snapshot(qid)["shared_counts"]
    assert node["mv_sql"].startswith("CREATE MATERIALIZED VIEW")


def test_unknown_ids(index):
    with pytest.raises(NodeNotFoundError):
        index.node("nope")
    with pytest.raises(NodeNotFoundError):
        index.snapshot("zz")
