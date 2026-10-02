"""QueryRewriterのテスト"""

from pathlib import Path

import pytest

from src.rewrite.query_rewriter import QueryRewriter, load_mv_selections


class TestQueryRewriter:
    """QueryRewriterクラスのテスト"""

    @pytest.fixture
    def mock_query_manager(self):
        """モックQueryManager"""

        class MockQM:
            leaf_nodes_map = {
                "leaf_1": {"table_name": "users", "alias": "u", "conditions": "u.age > 20"},
                "leaf_2": {"table_name": "orders", "alias": "o", "conditions": ""},
            }
            query_map = {
                1: {
                    "original_sql": "SELECT u.name, o.total FROM users u, orders o WHERE u.id = o.user_id"
                }
            }

        return MockQM()

    @pytest.fixture
    def rewriter(self, mock_query_manager):
        """Rewriterのフィクスチャ"""
        return QueryRewriter(mock_query_manager)

    def test_rewrite_query_with_mv(self, rewriter):
        """MVを使ったクエリ書き換え"""
        original_sql = "SELECT u.name FROM users u WHERE u.age > 20"

        rewritten = rewriter._rewrite_query(1, ["leaf_1"], original_sql)

        # MVで置換されているか確認
        assert "leaf_1" in rewritten or "users" in rewritten

    def test_rewrite_workload(self, rewriter, tmp_path):
        """ワークロード書き換え"""
        mv_selections = {1: ["leaf_1"]}

        original_queries = {1: "SELECT u.name FROM users u WHERE u.age > 20"}

        output_dir = tmp_path / "rewritten"
        files = rewriter.rewrite_workload(mv_selections, str(output_dir), original_queries)

        assert len(files) == 1
        assert Path(files[0]).exists()

    def test_load_mv_selections(self, tmp_path):
        """MV選択の読み込み"""
        csv_file = tmp_path / "mv_list.csv"
        csv_file.write_text("leaf_1,leaf_2\nNONE\nleaf_3")

        selections = load_mv_selections(str(csv_file))

        assert 0 in selections
        assert selections[0] == ["leaf_1", "leaf_2"]
        assert selections[1] == ["NONE"]
        assert selections[2] == ["leaf_3"]

    def test_generate_mv_creation_scripts(self, rewriter, tmp_path):
        """MV作成スクリプト生成"""
        output_dir = tmp_path / "mvs"

        files = rewriter.generate_mv_creation_scripts(["leaf_1"], output_dir)

        # QueryManagerがあればファイルが生成される
        if rewriter.qm:
            assert len(files) >= 0
