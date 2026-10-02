"""MVGeneratorのテスト"""

from pathlib import Path

import pytest

from src.rewrite.mv_generator import MVGenerator
from src.rewrite.schema import get_table_columns, validate_table


class TestSchema:
    """スキーマ定義のテスト"""

    def test_get_table_columns(self):
        """テーブルカラムの取得"""
        columns = get_table_columns("title")
        assert "id" in columns
        assert "title" in columns
        assert "production_year" in columns

    def test_unknown_table(self):
        """未知のテーブルでエラー"""
        with pytest.raises(KeyError):
            get_table_columns("unknown_table")

    def test_validate_table(self):
        """テーブルの検証"""
        assert validate_table("title") is True
        assert validate_table("unknown") is False


class TestMVGenerator:
    """MVGeneratorクラスのテスト"""

    @pytest.fixture
    def generator(self):
        """ジェネレーターのフィクスチャ"""
        return MVGenerator()

    def test_generate_leaf_mv(self, generator):
        """リーフノード用MV生成"""

        # モックQueryManager
        class MockQM:
            leaf_nodes_map_r = {
                "leaf_1": ("Seq Scan", "title", "t", "t.production_year > 2000")
            }

        qm = MockQM()
        sql = generator._generate_leaf_mv("leaf_1", qm)

        assert "CREATE MATERIALIZED VIEW leaf_1" in sql
        assert "title" in sql.lower()
        assert "production_year > 2000" in sql

    def test_generate_mv_scripts(self, generator, tmp_path):
        """MVスクリプト生成"""

        class MockQM:
            leaf_nodes_map_r = {
                "leaf_1": ("Seq Scan", "title", "t", "")
            }

        qm = MockQM()
        output_dir = tmp_path / "mvs"

        files = generator.generate_mv_scripts(["leaf_1"], qm, str(output_dir))

        assert len(files) == 1
        assert Path(files[0]).exists()

        with open(files[0], encoding="utf-8") as f:
            content = f.read()
            assert "CREATE MATERIALIZED VIEW" in content

    def test_save_create_sqls(self, generator, tmp_path):
        """SQL保存"""
        mv_data = [
            {
                "view_id": "mv_test_1",
                "create_sql": "CREATE MATERIALIZED VIEW mv_test_1 AS SELECT * FROM users;",
            }
        ]

        output_dir = tmp_path / "output"
        generator.save_create_sqls(mv_data, output_dir)

        sql_file = output_dir / "mv_test_1.sql"
        assert sql_file.exists()
        assert "CREATE MATERIALIZED VIEW" in sql_file.read_text()
