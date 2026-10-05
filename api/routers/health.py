"""Health endpoints."""

from fastapi import APIRouter, Depends

from api.deps import get_plan_service
from api.schemas import HealthResponse
from api.services.plan_service import PlanError, PlanService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(service: PlanService = Depends(get_plan_service)) -> HealthResponse:
    """Report API liveness and database connectivity."""
    try:
        service.ping()
    except PlanError as e:
        return HealthResponse(database=False, detail=str(e))
    return HealthResponse(database=True)
