"""Unit tests for what-if planning logic (no database; scratch execution is stubbed)."""

import json

import pytest

from api.services.whatif_service import (
    LARGE_MV_BYTES,
    InvalidSelectionError,
    LargeMVError,
    WhatIfBusyError,
    WhatIfService,
)
from config.settings import DatabaseConfig
from api.services.workload_service import NodeNotFoundError

pytestmark = pytest.mark.unit


class FakeWorkload:
    sizes = {"n1": 100, "n2": LARGE_MV_BYTES + 1}

    def query_index(self, qid):
        if qid != "1a":
            raise NodeNotFoundError(qid)
        return 0

    def node_positions(self, node):
        return [(0, 3)] if node in self.sizes else []

    def node_size_bytes(self, node):
        return self.sizes[node]

    def views_consistent(self, views):
        return all(v["node_id"] in self.sizes for v in views)

    def build_rewrite(self, qid, nodes):
        return "SELECT 1 FROM n1", [{"node_id": n, "create_sql": "x", "index_sql": None} for n in nodes]


@pytest.fixture
def service(tmp_path, monkeypatch):
    svc = WhatIfService(FakeWorkload(), DatabaseConfig(), tmp_path / "out", tmp_path / "cache")
    svc.calls = 0

    def fake_scratch(definitions, sql, analyze, timeout_s):
        svc.calls += 1
        return {
            "plan": {"Node Type": "Seq Scan", "Relation Name": "n1"},
            "planning_time_ms": None,
            "execution_time_ms": None,
            "mvs": [{"node_id": d["node_id"], "create_seconds": 0.1} for d in definitions],
        }

    monkeypatch.setattr(svc, "_run_scratch", fake_scratch)
    return svc


def test_plan_is_cached_and_flags_mv_usage(service):
    first = service.plan_with_mvs("1a", ["n1"])
    again = service.plan_with_mvs("1a", ["n1"])
    assert (first["cached"], again["cached"], service.calls) == (False, True, 1)
    assert first["mvs"][0]["used_in_plan"] and first["mvs"][0]["referenced_in_sql"]
    assert service.plan_with_mvs("1a", ["n1"], force=True)["cached"] is False


def test_large_mvs_need_confirmation(service):
    with pytest.raises(LargeMVError):
        service.plan_with_mvs("1a", ["n2"])
    assert service.plan_with_mvs("1a", ["n2"], confirm_large=True)["node_ids"] == ["n2"]


@pytest.mark.parametrize("qid,nodes", [("1a", []), ("1a", ["ghost"]), ("zz", ["n1"])])
def test_rejects_invalid_selection(service, qid, nodes):
    with pytest.raises(InvalidSelectionError):
        service.plan_with_mvs(qid, nodes)


def test_rejects_when_busy(service):
    service._busy.acquire()
    with pytest.raises(WhatIfBusyError):
        service.plan_with_mvs("1a", ["n1"])


def test_selections_only_from_consistent_results(service, tmp_path):
    out = tmp_path / "out"

    def write(set_name, algo, views):
        d = out / set_name / algo / "optimization"
        d.mkdir(parents=True)
        (d / "result.json").write_text(json.dumps({"selected_views": views}))

    write("good", "bigsubs", [{"node_id": "n1", "usage_positions": [[0, 3]]}])
    write("stale", "bigsubs", [{"node_id": "gone", "usage_positions": [[0, 3]]}])
    write("elsewhere", "bigsubs", [{"node_id": "n1", "usage_positions": [[5, 3]]}])
    sels = service.selections_for_query("1a")
    assert [(s["set_id"], s["node_ids"]) for s in sels] == [("good", ["n1"])]
