"""Unit tests for the plan API (no database required)."""

import pytest
from fastapi.testclient import TestClient

from api.deps import get_plan_service
from api.main import app
from api.services.plan_service import InvalidQueryError, PlanError, validate_sql

pytestmark = pytest.mark.unit


class FakeService:
    def __init__(self, error: Exception | None = None):
        self.error = error

    def get_plan(self, sql, analyze=False, timeout_s=30):
        if self.error:
            raise self.error
        return {"Plan": {"Node Type": "Seq Scan"}, "Planning Time": 0.1}

    def ping(self):
        if self.error:
            raise self.error


@pytest.fixture
def client():
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_validate_accepts_select():
    assert validate_sql("SELECT 1;") == "SELECT 1"
    assert validate_sql("WITH a AS (SELECT 1) SELECT * FROM a").startswith("WITH")


@pytest.mark.parametrize("sql", ["", "SELECT 1; SELECT 2", "DROP TABLE t", "DELETE FROM t"])
def test_validate_rejects(sql):
    with pytest.raises(InvalidQueryError):
        validate_sql(sql)


def test_create_plan_ok(client):
    app.dependency_overrides[get_plan_service] = lambda: FakeService()
    r = client.post("/plans", json={"sql": "SELECT 1"})
    assert r.status_code == 200
    assert r.json()["plan"]["Node Type"] == "Seq Scan"


def test_create_plan_invalid_is_422(client):
    app.dependency_overrides[get_plan_service] = lambda: FakeService(InvalidQueryError("bad"))
    assert client.post("/plans", json={"sql": "x"}).status_code == 422


def test_create_plan_db_error_is_400(client):
    app.dependency_overrides[get_plan_service] = lambda: FakeService(PlanError("boom"))
    assert client.post("/plans", json={"sql": "SELECT 1"}).status_code == 400


def test_health_reports_db_down(client):
    app.dependency_overrides[get_plan_service] = lambda: FakeService(PlanError("down"))
    body = client.get("/health").json()
    assert body["api"] == "ok" and body["database"] is False
