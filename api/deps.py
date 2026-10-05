"""FastAPI dependencies."""

from api.services.plan_service import PlanService
from config.settings import get_settings


def get_plan_service() -> PlanService:
    """Build a PlanService from the global settings."""
    return PlanService(get_settings().database)
