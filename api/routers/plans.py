"""Query plan endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_plan_service
from api.schemas import PlanRequest, PlanResponse
from api.services.plan_service import InvalidQueryError, PlanError, PlanService

router = APIRouter(prefix="/plans", tags=["plans"])


@router.post("", response_model=PlanResponse)
def create_plan(req: PlanRequest, service: PlanService = Depends(get_plan_service)) -> PlanResponse:
    """Run EXPLAIN (FORMAT JSON) for the submitted query."""
    try:
        result = service.get_plan(req.sql, analyze=req.analyze, timeout_s=req.timeout_s)
    except InvalidQueryError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except PlanError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return PlanResponse(
        plan=result["Plan"],
        planning_time_ms=result.get("Planning Time"),
        execution_time_ms=result.get("Execution Time"),
        analyzed=req.analyze,
    )
