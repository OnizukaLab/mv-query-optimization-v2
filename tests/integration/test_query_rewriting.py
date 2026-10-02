"""クエリ書き換えの統合テスト"""

from pathlib import Path

import pytest

from src.rewrite.query_rewriter import QueryRewriter


@pytest.mark.integration
class TestQueryRewritingIntegration:
    """クエリ書き換えの統合テスト"""

    def test_full_rewrite_flow(self, tmp_path):
        """完全な書き換えフロー"""

        # モックQueryManager
        class MockQM:
            leaf_nodes_map = {
                "leaf_1": {
                    "table_name": "title",
                    "alias": "t",
                    "conditions": "t.production_year > 2000",
                }
            }
            query_map = {
                1: {"original_sql": "SELECT t.title FROM title t WHERE t.production_year > 2000"}
            }

        qm = MockQM()
        rewriter = QueryRewriter(qm)

        # MV選択
        mv_selections = {1: ["leaf_1"]}

        # 書き換え
        output_dir = tmp_path / "rewritten"
        files = rewriter.rewrite_workload(mv_selections, str(output_dir))

        # 検証
        assert len(files) == 1
        assert Path(files[0]).exists()

        with open(files[0], encoding="utf-8") as f:
            content = f.read()
            assert "SELECT" in content

    def test_mv_generation_and_rewrite(self, tmp_path):
        """MV生成とクエリ書き換えの統合"""

        class MockQM:
            leaf_nodes_map = {
                ("Seq Scan", "title", "t", ""): "leaf_1"
            }
            leaf_nodes_map_r = {
                "leaf_1": ("Seq Scan", "title", "t", "")
            }
            relation_tables = {
                "leaf_1": "title"
            }
            query_map = {1: {"original_sql": "SELECT * FROM title t"}}

        qm = MockQM()
        rewriter = QueryRewriter(qm)

        # MV作成スクリプト生成
        mv_dir = tmp_path / "mvs"
        mv_files = rewriter.generate_mv_creation_scripts(["leaf_1"], mv_dir)

        assert len(mv_files) == 1
        assert Path(mv_files[0]).exists()

        # クエリ書き換え
        rewrite_dir = tmp_path / "rewritten"
        rewritten_files = rewriter.rewrite_workload({1: ["leaf_1"]}, str(rewrite_dir))

        assert len(rewritten_files) == 1
        assert Path(rewritten_files[0]).exists()
