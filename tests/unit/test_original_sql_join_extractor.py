"""Tests for original SQL join extractor utilities."""

from experiments.small_test_ver2.mv_generation.original_sql_join_extractor import (
    extract_aliases_from_sql,
    extract_equijoin_conditions,
)


def test_extract_equijoin_conditions_from_where_clause():
    sql = """
    SELECT u.id, o.id
    FROM users AS u, orders AS o
    WHERE u.id = o.user_id
      AND u.age > 20;
    """

    conditions = extract_equijoin_conditions(sql)

    assert ("u", "id", "o", "user_id") in conditions


def test_extract_equijoin_conditions_from_join_on_clause():
    sql = """
    SELECT u.id, o.id
    FROM users AS u
    INNER JOIN orders AS o ON u.id = o.user_id
    LEFT JOIN payments AS p ON o.id = p.order_id
    WHERE u.age > 20;
    """

    conditions = extract_equijoin_conditions(sql)

    assert ("u", "id", "o", "user_id") in conditions
    assert ("o", "id", "p", "order_id") in conditions


def test_extract_equijoin_conditions_with_quoted_identifiers():
    sql = '''
    SELECT "u"."id", "o"."id"
    FROM "users" AS "u"
    JOIN "orders" AS "o" ON "u"."id" = "o"."user_id"
    WHERE "o"."status" = 'paid';
    '''

    conditions = extract_equijoin_conditions(sql)

    assert ("u", "id", "o", "user_id") in conditions


def test_extract_aliases_from_join_syntax_without_where():
    sql = """
    SELECT u.id, o.id
    FROM users u
    JOIN orders o ON u.id = o.user_id;
    """

    aliases = extract_aliases_from_sql(sql)

    assert aliases == {"u": "users", "o": "orders"}
