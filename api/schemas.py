"""Request/response schemas for the dashboard API."""

from typing import Any

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
