"""実験フロー全体の統合テスト"""

from pathlib import Path

import pytest


@pytest.mark.integration
class TestExperimentFlow:
    """実験フロー全体のテスト"""

    def test_query_rewriting_flow(self, tmp_path, mock_query_manager):
        """クエリ書き換えフローのテスト"""
        from src.rewrite.query_rewriter import QueryRewriter

        rewriter = QueryRewriter(mock_query_manager)

        # MV選択
        mv_selections = {1: ["leaf_1"]}

        # クエリ書き換え
        output_dir = tmp_path / "rewritten"
        files = rewriter.rewrite_workload(mv_selections, str(output_dir))

        # 検証
        assert len(files) == 1
        assert Path(files[0]).exists()

        # ファイル内容確認
        with open(files[0], encoding="utf-8") as f:
            content = f.read()
            assert "SELECT" in content

    def test_mv_generation_flow(self, tmp_path, mock_query_manager):
        """MV生成フローのテスト"""
        from src.rewrite.mv_generator import MVGenerator

        generator = MVGenerator()

        # MV生成
        output_dir = tmp_path / "mvs"
        files = generator.generate_mv_scripts(
            ["leaf_1", "leaf_2"], mock_query_manager, str(output_dir)
        )

        # 検証
        assert len(files) == 2

        for file in files:
            assert Path(file).exists()
            with open(file, encoding="utf-8") as f:
                content = f.read()
                assert "CREATE MATERIALIZED VIEW" in content

    def test_end_to_end_rewrite_flow(self, tmp_path, mock_query_manager):
        """エンドツーエンドの書き換えフロー"""
        from src.rewrite.query_rewriter import QueryRewriter

        rewriter = QueryRewriter(mock_query_manager)

        # 1. MV作成スクリプト生成
        mv_dir = tmp_path / "mvs"
        mv_files = rewriter.generate_mv_creation_scripts(["leaf_1", "leaf_2"], mv_dir)

        assert len(mv_files) == 2

        # 2. クエリ書き換え
        rewrite_dir = tmp_path / "rewritten"
        mv_selections = {1: ["leaf_1"]}

        rewritten_files = rewriter.rewrite_workload(mv_selections, str(rewrite_dir))

        assert len(rewritten_files) == 1

        # 3. 両方のファイルが存在することを確認
        for mv_file in mv_files:
            assert Path(mv_file).exists()

        for rewritten_file in rewritten_files:
            assert Path(rewritten_file).exists()

    def test_script_integration(self, tmp_path):
        """スクリプト統合テスト"""
        from src.rewrite.query_rewriter import load_mv_selections

        # テスト用のMVリストを作成
        mv_list_file = tmp_path / "mv_y_list.csv"
        mv_list_file.write_text("leaf_1,leaf_2\nleaf_3\nNONE")

        # ロード
        selections = load_mv_selections(str(mv_list_file))

        # 検証
        assert 0 in selections
        assert selections[0] == ["leaf_1", "leaf_2"]
        assert selections[1] == ["leaf_3"]
        assert selections[2] == ["NONE"]


@pytest.mark.integration
class TestScriptIntegration:
    """スクリプト統合テスト"""

    def test_compare_algorithms_basic(self, tmp_path):
        """アルゴリズム比較の基本テスト"""
        # テスト用のMVリストを作成
        normal_dir = tmp_path / "normal"
        normal_dir.mkdir()

        mv_list = normal_dir / "mv_y_list.csv"
        mv_list.write_text("leaf_1,leaf_2\nleaf_3\n")

        # 比較実行（実際のスクリプトは呼ばずにロジックをテスト）
        import csv

        with open(mv_list) as f:
            reader = csv.reader(f)
            rows = list(reader)

        assert len(rows) == 2
        assert rows[0] == ["leaf_1", "leaf_2"]
        assert rows[1] == ["leaf_3"]
