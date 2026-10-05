"""FastAPI dependencies."""

from functools import lru_cache
from pathlib import Path

from api.services.experiment_service import PROJECT_ROOT, ExperimentManager
from api.services.plan_service import PlanService
from api.services.results_service import ResultsService
from config.settings import get_settings


def get_plan_service() -> PlanService:
    """Build a PlanService from the global settings."""
    return PlanService(get_settings().database)


@lru_cache
def get_experiment_manager() -> ExperimentManager:
    """Process-wide experiment manager (single running experiment)."""
    return ExperimentManager()


def get_results_service() -> ResultsService:
    """ResultsService rooted at the configured output directory."""
    out = Path(get_settings().paths.output_dir)
    return ResultsService(out if out.is_absolute() else PROJECT_ROOT / out)
