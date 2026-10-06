"""Workload query endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_query_service, get_workload_index
from api.services.query_service import QueryNotFoundError, QueryService
from api.services.workload_service import NodeNotFoundError, WorkloadIndex

router = APIRouter(prefix="/queries", tags=["queries"])


@router.get("")
def list_queries(service: QueryService = Depends(get_query_service)) -> list[dict[str, Any]]:
    """JOB queries in natural order."""
    return service.list_queries()


@router.get("/{query_id}")
def get_query(query_id: str, service: QueryService = Depends(get_query_service)) -> dict[str, Any]:
    """Original SQL of one query."""
    try:
        return service.get_query(query_id)
    except QueryNotFoundError as e:
        raise HTTPException(status_code=404, detail="Query not found") from e


@router.get("/{query_id}/snapshot")
def get_snapshot(
    query_id: str, index: WorkloadIndex = Depends(get_workload_index)
) -> dict[str, Any]:
    """Stored plan with node ids (MV candidates) and how many queries share each node."""
    try:
        return index.snapshot(query_id)
    except NodeNotFoundError as e:
        raise HTTPException(status_code=404, detail="Query not found") from e
