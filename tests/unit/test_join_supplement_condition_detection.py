"""Tests for join-link alias detection used in join supplementation."""

from experiments.small_test_ver2.mv_generation.enhanced_mv_generator import EnhancedMVGenerator


def test_single_table_filter_is_not_treated_as_join():
    aliases = EnhancedMVGenerator._extract_linked_aliases_from_condition("t.id = 10")
    assert aliases == set()


def test_equality_join_is_treated_as_join():
    aliases = EnhancedMVGenerator._extract_linked_aliases_from_condition("t.id = mi.movie_id")
    assert aliases == {"t", "mi"}


def test_non_equi_join_is_treated_as_join():
    aliases = EnhancedMVGenerator._extract_linked_aliases_from_condition("t.ts > mi.ts")
    assert aliases == {"t", "mi"}


def test_function_wrapped_join_is_treated_as_join():
    aliases = EnhancedMVGenerator._extract_linked_aliases_from_condition(
        "UPPER(t.name) = UPPER(mi.name)"
    )
    assert aliases == {"t", "mi"}


def test_or_of_single_table_filters_is_not_treated_as_join():
    aliases = EnhancedMVGenerator._extract_linked_aliases_from_condition(
        "t.col IS NOT NULL OR mi.col IS NOT NULL"
    )
    assert aliases == set()


def test_add_table_alias_does_not_rewrite_string_literals():
    generator = EnhancedMVGenerator.__new__(EnhancedMVGenerator)
    condition = (
        "((note >= '(Berlin International Film Festival)'::text) "
        "AND (note <= 'otre'::text))"
    )

    fixed = generator._add_table_alias_to_filter(condition, "movie_info")

    assert "movie_info.note" in fixed
    assert "(movie_info.Berlin International Film Festival)" not in fixed
    assert "'(Berlin International Film Festival)'::text" in fixed
