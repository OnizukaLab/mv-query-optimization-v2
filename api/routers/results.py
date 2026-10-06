"""Experiment result endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_results_service, get_workload_index
from api.services.results_service import ResultNotFoundError, ResultsService
from api.services.workload_service import WorkloadIndex

router = APIRouter(prefix="/results", tags=["results"])


@router.get("/sets")
def list_sets(service: ResultsService = Depends(get_results_service)) -> list[dict]:
    """Result sets found under Output/, newest first."""
    return service.list_sets()


@router.get("/sets/{set_id}/compare")
def compare(set_id: str, service: ResultsService = Depends(get_results_service)) -> dict:
    """Algorithm comparison for one result set."""
    try:
        return service.compare(set_id)
    except ResultNotFoundError as e:
        raise HTTPException(status_code=404, detail="Result set not found") from e


@router.get("/sets/{set_id}/selected")
def selected_nodes(
    set_id: str,
    service: ResultsService = Depends(get_results_service),
    index: WorkloadIndex = Depends(get_workload_index),
) -> dict[str, dict]:
    """MV-candidate node ids each algorithm selected, for highlighting on the plan overview.

    ``consistent`` is False when the stored result was produced with a different node numbering
    than the current workload parse; its ``node_ids`` would not match the plans and are withheld.
    ``used`` maps each query id to the nodes that query actually uses. A selected MV is only used
    by some of the queries containing it, and never together with a node it contains, so the plan
    overview highlights ``used`` rather than every selected node present in a plan.
    """
    try:
        views = service.selected_views(set_id)
    except ResultNotFoundError as e:
        raise HTTPException(status_code=404, detail="Result set not found") from e
    query_ids = index.query_ids()
    out: dict[str, dict] = {}
    for algo, vs in views.items():
        consistent = index.views_consistent(vs)
        used: dict[str, list[str]] = {}
        if consistent:
            for v in vs:
                for q, _pos in v.get("usage_positions", []):
                    nodes = used.setdefault(query_ids[int(q)], [])
                    if v["node_id"] not in nodes:
                        nodes.append(v["node_id"])
        out[algo] = {
            "consistent": consistent,
            "count": len(vs),
            "node_ids": sorted({v["node_id"] for v in vs}) if consistent else [],
            "used": used,
        }
    return out
