"""パフォーマンステスト

実行: pytest tests/performance/ -m performance
"""

import time

import pytest


@pytest.mark.performance
class TestOptimizationPerformance:
    """最適化のパフォーマンステスト"""

    def test_query_rewriter_performance(self, tmp_path, mock_query_manager):
        """QueryRewriterのパフォーマンス"""
        from src.rewrite.query_rewriter import QueryRewriter

        rewriter = QueryRewriter(mock_query_manager)

        # 複数クエリの書き換え
        mv_selections = {i: ["leaf_1"] for i in range(1, 11)}

        start = time.time()

        output_dir = tmp_path / "rewritten"
        files = rewriter.rewrite_workload(mv_selections, str(output_dir))

        elapsed = time.time() - start

        # 10クエリを1秒以内に処理
        assert elapsed < 1.0, f"Too slow: {elapsed:.2f}s"
        assert len(files) <= 10

    def test_mv_generator_performance(self, tmp_path, mock_query_manager):
        """MVGeneratorのパフォーマンス"""
        from src.rewrite.mv_generator import MVGenerator

        generator = MVGenerator()

        # 複数MV生成
        mv_nodes = [f"leaf_{i}" for i in range(1, 21)]

        start = time.time()

        output_dir = tmp_path / "mvs"
        generator.generate_mv_scripts(mv_nodes, mock_query_manager, str(output_dir))

        elapsed = time.time() - start

        # 20MVを1秒以内に生成
        assert elapsed < 1.0, f"Too slow: {elapsed:.2f}s"

    @pytest.mark.slow
    def test_large_workload_performance(self, tmp_path, mock_query_manager):
        """大規模ワークロードのパフォーマンス"""
        from src.rewrite.query_rewriter import QueryRewriter

        rewriter = QueryRewriter(mock_query_manager)

        # 100クエリのシミュレーション
        mv_selections = {i: ["leaf_1", "leaf_2"] for i in range(1, 101)}

        start = time.time()

        output_dir = tmp_path / "large_rewritten"
        files = rewriter.rewrite_workload(mv_selections, str(output_dir))

        elapsed = time.time() - start

        # 100クエリを10秒以内に処理
        assert elapsed < 10.0, f"Too slow: {elapsed:.2f}s"

        print(f"\nProcessed {len(files)} queries in {elapsed:.2f}s")
        print(f"Average: {elapsed/len(files):.4f}s per query")


@pytest.mark.performance
class TestSQLParserPerformance:
    """SQLParserのパフォーマンステスト"""

    def test_parse_complex_query_performance(self):
        """複雑なクエリの解析パフォーマンス"""
        from src.rewrite.sql_parser import SQLParser

        parser = SQLParser()

        # 複雑なSQL
        complex_sql = """
        SELECT u.name, o.total, p.product_name
        FROM users u
        INNER JOIN orders o ON u.id = o.user_id
        INNER JOIN products p ON o.product_id = p.id
        WHERE u.age > 20 AND o.total > 1000 AND p.category = 'electronics'
        GROUP BY u.name, o.total, p.product_name
        ORDER BY o.total DESC
        LIMIT 100
        """

        start = time.time()

        # 1000回解析
        for _ in range(1000):
            parser.extract_from_clause(complex_sql)
            parser.extract_where_clause(complex_sql)
            from_clause = parser.extract_from_clause(complex_sql)
            parser.extract_tables(from_clause)

        elapsed = time.time() - start

        # 1000回を1秒以内に処理
        assert elapsed < 1.0, f"Too slow: {elapsed:.2f}s"

        print(f"\n1000 parses in {elapsed:.2f}s ({elapsed*1000:.2f}μs per parse)")
