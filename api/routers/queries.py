"""Workload query endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_query_service
from api.services.query_service import QueryNotFoundError, QueryService

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
