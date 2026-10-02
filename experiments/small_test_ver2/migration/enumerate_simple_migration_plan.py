# 2パターンのみのマイグレーションプランを取得 (マイグレーション無し、依存MV無しでマイグレーション)
import argparse
import pickle
import json
import sys
from pathlib import Path
from typing import Dict

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from src.core.query_parser import QueryParser
from experiments.small_test_ver2.mv_generation.simple_mv_sql_generator import SimpleMVSQLGenerator

class GetSimpleMigrationPlans:
    """MVのマイグレーションプランを2パターンのみ取得"""
    def __init__(
            self,
            settings: Settings | None = None,
            query_set: str = "job_like",
    ):
        self.settings = settings
        self.query_set = query_set

        # 03_parsed/{queryset}/qp_class.pklから読み込み
        self.parser_file = Path(__file__).parent.parent / "03_parsed" / self.query_set / "qp_class.pkl"

        # 読み込んだデータを保持
        self.qp: QueryParser | None = None
        self.sql: Dict[str, Dict[str, str]] | None = None

        self.mv_sql_generator: SimpleMVSQLGenerator | None = None
        self.schema_provider = None  # 再利用するSchemaProvider

        if self.parser_file and self.parser_file.exists():
            self.load_pickle()
            if self.qp:
                # db_configをsettingsから取得してSimpleMVSQLGeneratorに渡す
                db_config = None
                if self.settings and hasattr(self.settings, 'database'):
                    db_config = {
                        'host': self.settings.database.host,
                        'port': self.settings.database.port,
                        'database': self.settings.database.database,
                        'user': self.settings.database.user,
                        'password': self.settings.database.password,
                    }
                # SchemaProviderを1回だけ作成（DB接続を再利用）
                from src.rewrite.schema_provider import SchemaProvider
                self.schema_provider = SchemaProvider(db_config)
                self.mv_sql_generator = SimpleMVSQLGenerator(self.qp, db_config)

    def load_pickle(self) -> None:
        try:
            with open(self.parser_file, 'rb') as f:
                self.qp = pickle.load(f, encoding='bytes')
        except Exception as e:
            print(f"pickle ファイルの読み込みに失敗しました: {e}")
            self.qp = None

    def generate_mv_sql_with_existing(self, node_id: str, existing_mvs: list[str]) -> str | None:
        """既存のMVを利用して新しいMVのSQLを作成"""
        if self.mv_sql_generator is None:
            print(f"  エラー: MVSQLGeneratorが初期化されていません")
            return None

        return self.mv_sql_generator.generate_mv_sql(
            node_id,
            existing_mvs,
        )

    def enumerate_simple_migration_plans(self, target_mv: str) -> Dict[str, str]:
        """
        2パターンのみのマイグレーションプランを生成
        1. マイグレーション無し (自身が既に存在する)
        2. 依存MV無しでマイグレーション (空リストから新規作成)
        """
        mv_sqls = {}
        
        # パターン1: マイグレーション無し
        mv_sqls[str([target_mv])] = "NON_MIGRATE"
        
        # パターン2: 依存MV無しでマイグレーション
        mv_sql = self.generate_mv_sql_with_existing(target_mv, [])
        if mv_sql:
            mv_sqls["[]"] = mv_sql

        return mv_sqls

    def save_migration_plans(
            self,
            filename: str = "simple_migration_plans.json"
    ):
        if not self.sql:
            print("エラー: マイグレーションプランが生成されていません")
            return
        
        # 出力dirのパス (parent.parent で small_test_ver2 に移動)
        output_dir = Path(__file__).parent.parent / "04_migration" / self.query_set
        output_dir.mkdir(parents=True, exist_ok=True)
        # ファイルパス
        output_file = output_dir / filename

        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.sql, f, indent=2, ensure_ascii=False)
            print(f"マイグレーションプランを保存しました: {output_file}")
        except Exception as e:
            print(f"JSONファイルの保存に失敗しました: {e}")
    
    def get_migration_sqls(self):
        """全てのノードに対して2パターンのマイグレーションプランを取得"""
        if not self.qp or not hasattr(self.qp, 'qm'):
            print("  エラー: QueryParserが初期化されていません")
            return
        
        self.sql = {}

        # 全てのノード（leaf + non_leaf）を取得
        all_nodes = list(self.qp.qm.leaf_nodes_map_r.keys()) + list(self.qp.qm.non_leaf_nodes_info.keys())

        print(f"\n処理対象ノード数: {len(all_nodes)}個")
        print(f"  - leaf_nodes: {len(self.qp.qm.leaf_nodes_map_r)}個")
        print(f"  - non_leaf_nodes: {len(self.qp.qm.non_leaf_nodes_info)}個")
        print("\nマイグレーションプラン生成中（2パターンのみ）...")

        # 進捗表示用
        processed = 0
        total = len(all_nodes)

        # 各ノードのマイグレーションプランを取得
        for node in all_nodes:
            processed += 1
            if processed % 10 == 0 or processed == total:
                print(f"  進捗: {processed}/{total} ({processed*100//total}%)")
            
            # 全ノードに対して2パターンのみ生成
            self.sql[node] = self.enumerate_simple_migration_plans(node)
        
        print(f"\n✓ 全{total}ノードの処理完了")
        # JSONファイルとして保存
        self.save_migration_plans()

if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(description="MVマイグレーションプラン列挙（2パターンのみ）")
    parser.add_argument(
        "--query-set",
        type=str,
        default="job_like",
        help="使用するクエリセットの名前 (デフォルト: job_like)"
    )

    args = parser.parse_args()

    # Settingsを読み込んでdb_configを提供
    settings = Settings.from_yaml("experiments/small_test_ver2/config.yaml")
    migrator = GetSimpleMigrationPlans(settings=settings, query_set=args.query_set)

    migrator.get_migration_sqls()
