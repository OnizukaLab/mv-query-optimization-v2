"""Unit tests for the JOB query endpoints."""

import pytest

from api.services.query_service import QueryNotFoundError, QueryService

pytestmark = pytest.mark.unit


@pytest.fixture
def service(tmp_path):
    for qid in ["10a", "2b", "1a", "1b"]:
        (tmp_path / f"{qid}.sql").write_text(
            f"SELECT MIN(t.title) AS x FROM title AS t, movie_info AS mi WHERE t.id = mi.movie_id; -- {qid}\n"
        )
    (tmp_path / "notes.sql").write_text("not a query id")
    return QueryService(tmp_path)


def test_lists_in_natural_order_with_metadata(service):
    items = service.list_queries()
    assert [q["id"] for q in items] == ["1a", "1b", "2b", "10a"]
    assert items[0]["family"] == 1 and items[0]["tables"] == 2


def test_get_query_returns_sql(service):
    assert service.get_query("2b")["sql"].startswith("SELECT MIN")


@pytest.mark.parametrize("bad", ["../etc/passwd", "notes", "99z", "1", ""])
def test_unknown_or_unsafe_ids(service, bad):
    with pytest.raises(QueryNotFoundError):
        service.get_query(bad)
