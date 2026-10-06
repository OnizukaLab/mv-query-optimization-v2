"""Plan node (MV candidate) endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_workload_index
from api.services.workload_service import NodeNotFoundError, WorkloadIndex

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.get("/{node_id}")
def get_node(node_id: str, index: WorkloadIndex = Depends(get_workload_index)) -> dict[str, Any]:
    """Details of a node and the queries that contain it."""
    try:
        return index.node(node_id)
    except NodeNotFoundError as e:
        raise HTTPException(status_code=404, detail="Node not found") from e
