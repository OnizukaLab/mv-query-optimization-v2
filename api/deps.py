"""FastAPI dependencies."""

from functools import lru_cache

from api.services.experiment_service import ExperimentManager
from api.services.plan_service import PlanService
from config.settings import get_settings


def get_plan_service() -> PlanService:
    """Build a PlanService from the global settings."""
    return PlanService(get_settings().database)


@lru_cache
def get_experiment_manager() -> ExperimentManager:
    """Process-wide experiment manager (single running experiment)."""
    return ExperimentManager()
