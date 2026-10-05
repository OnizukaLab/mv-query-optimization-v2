"""Experiment result endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_results_service
from api.services.results_service import ResultNotFoundError, ResultsService

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
