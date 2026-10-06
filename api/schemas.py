"""Request/response schemas for the dashboard API."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class PlanRequest(BaseModel):
    """Request body for fetching a query plan."""

    sql: str = Field(..., min_length=1, description="Single SQL statement to EXPLAIN")
    analyze: bool = Field(False, description="Run EXPLAIN ANALYZE (executes the query, read-only)")
    timeout_s: int = Field(30, ge=1, le=600, description="statement_timeout in seconds")


class PlanResponse(BaseModel):
    """EXPLAIN (FORMAT JSON) result."""

    plan: dict[str, Any] = Field(..., description="Root 'Plan' node as returned by PostgreSQL")
    planning_time_ms: float | None = None
    execution_time_ms: float | None = None
    analyzed: bool = False


class HealthResponse(BaseModel):
    """Service and database health."""

    api: str = "ok"
    database: bool
    detail: str | None = None


Algorithm = Literal["none", "normal", "bigsubs", "utility", "utility_capacity", "frequency"]
Phase = Literal[
    "query_parsing", "optimization", "sql_generation", "mv_creation", "query_rewriting", "benchmark"
]
WorkloadType = Literal["job", "ceb", "ceb-1a", "redbench", "redbench-job", "redbench-ceb"]


class ExperimentRequest(BaseModel):
    """Parameters for scripts/run_experiment.py."""

    algorithms: list[Algorithm] = Field(..., min_length=1)
    phases: list[Phase] = Field(..., min_length=1)
    storage_limit_mb: int = Field(50, ge=1, le=100_000)
    insert_queries: int = Field(1000, ge=0, le=1_000_000)
    workload_type: WorkloadType = "redbench-job"
    verbose: bool = False
