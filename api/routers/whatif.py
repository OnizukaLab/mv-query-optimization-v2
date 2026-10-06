"""What-if endpoints: plan a query with hypothetical MVs and list experiment selections."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_experiment_manager, get_whatif_service
from api.services.experiment_service import ExperimentManager
from api.services.plan_service import PlanError
from api.services.whatif_service import (
    InvalidSelectionError,
    LargeMVError,
    TooLargeError,
    WhatIfBusyError,
    WhatIfService,
)

router = APIRouter(prefix="/queries", tags=["what-if"])


class MVPlanRequest(BaseModel):
    """Which nodes to materialize for the query."""

    node_ids: list[str] = Field(..., min_length=1, max_length=50)
    analyze: bool = False
    confirm_large: bool = False
    force: bool = Field(False, description="Ignore the cached result")


class NodeWhatIfRequest(BaseModel):
    """Options for the per-node what-if."""

    analyze: bool = Field(False, description="Also execute each query before/after (slow)")
    confirm_large: bool = False
    force: bool = False


nodes_router = APIRouter(prefix="/nodes", tags=["what-if"])


@nodes_router.post("/{node_id}/whatif")
def node_whatif(
    node_id: str,
    req: NodeWhatIfRequest,
    service: WhatIfService = Depends(get_whatif_service),
    experiments: ExperimentManager = Depends(get_experiment_manager),
) -> dict[str, Any]:
    """Materialize one node transiently and compare all queries containing it."""
    if any(j["status"] == "running" for j in experiments.list_summaries()):
        raise HTTPException(status_code=409, detail="An experiment is running; what-if is paused")
    try:
        return service.node_whatif(
            node_id, analyze=req.analyze, confirm_large=req.confirm_large, force=req.force
        )
    except InvalidSelectionError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except LargeMVError as e:
        raise HTTPException(
            status_code=409, detail={"code": "large_mv", "size_bytes": e.size_bytes, "message": str(e)}
        ) from e
    except TooLargeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except WhatIfBusyError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except PlanError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@nodes_router.get("/{node_id}/estimate")
def node_estimate(node_id: str, service: WhatIfService = Depends(get_whatif_service)) -> dict[str, Any]:
    """Planner estimate of the node's MV size (rows x width)."""
    try:
        return service.estimate_mv(node_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail="Node not found") from e


@router.get("/{query_id}/mv-sets")
def mv_sets(query_id: str, service: WhatIfService = Depends(get_whatif_service)) -> list[dict[str, Any]]:
    """MV selections from past experiments that apply to this query."""
    try:
        return service.selections_for_query(query_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail="Query not found") from e


@router.post("/{query_id}/mv-plan")
def mv_plan(
    query_id: str,
    req: MVPlanRequest,
    service: WhatIfService = Depends(get_whatif_service),
    experiments: ExperimentManager = Depends(get_experiment_manager),
) -> dict[str, Any]:
    """Plan the query rewritten onto the selected MVs (created transiently, then rolled back)."""
    if any(j["status"] == "running" for j in experiments.list_summaries()):
        raise HTTPException(status_code=409, detail="An experiment is running; what-if is paused")
    try:
        return service.plan_with_mvs(
            query_id, req.node_ids, analyze=req.analyze, confirm_large=req.confirm_large, force=req.force
        )
    except InvalidSelectionError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except LargeMVError as e:
        raise HTTPException(
            status_code=409, detail={"code": "large_mv", "size_bytes": e.size_bytes, "message": str(e)}
        ) from e
    except TooLargeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except WhatIfBusyError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except PlanError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
