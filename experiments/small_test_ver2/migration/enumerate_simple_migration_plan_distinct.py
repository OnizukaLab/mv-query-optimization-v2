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
from experiments.small_test_ver2.mv_generation.original_sql_join_extractor import (
    extract_select_column_refs,
    extract_equijoin_conditions,
    extract_where_column_refs,
)

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
                self._ensure_original_query_column_refs()
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

    def _ensure_original_query_column_refs(self) -> None:
        """Load SELECT/JOIN/WHERE refs from original SQL when missing in legacy pickle."""
        if not self.qp or not hasattr(self.qp, 'qm'):
            return

        qm = self.qp.qm
        has_select = isinstance(getattr(qm, 'original_query_select_columns', None), dict) and bool(getattr(qm, 'original_query_select_columns', {}))
        has_join = isinstance(getattr(qm, 'original_query_join_conditions', None), dict) and bool(getattr(qm, 'original_query_join_conditions', {}))
        has_where = isinstance(getattr(qm, 'original_query_where_columns', None), dict) and bool(getattr(qm, 'original_query_where_columns', {}))
        if has_select and has_join and has_where:
            return

        if not isinstance(getattr(qm, 'original_query_select_columns', None), dict):
            setattr(qm, 'original_query_select_columns', {})
        if not isinstance(getattr(qm, 'original_query_join_conditions', None), dict):
            setattr(qm, 'original_query_join_conditions', {})
        if not isinstance(getattr(qm, 'original_query_where_columns', None), dict):
            setattr(qm, 'original_query_where_columns', {})

        loaded_select = 0
        loaded_join = 0
        loaded_where = 0
        sql_dir = Path(__file__).parent.parent / "01_queries" / self.query_set
        query_files = getattr(self.qp, 'query_files', [])
        if not sql_dir.exists() or not query_files:
            print("  [WARN] 列参照補完: SQLファイル情報が不足のためスキップ")
            return

        for i, stem in enumerate(query_files):
            sql_path = sql_dir / f"{stem}.sql"
            if not sql_path.exists():
                continue
            try:
                with open(sql_path, 'r', encoding='utf-8') as f:
                    sql_text = f.read()

                if not qm.original_query_select_columns.get(i):
                    refs = extract_select_column_refs(sql_text)
                    if refs:
                        qm.original_query_select_columns[i] = refs
                        loaded_select += 1

                if not qm.original_query_join_conditions.get(i):
                    joins = extract_equijoin_conditions(sql_text)
                    if joins:
                        qm.original_query_join_conditions[i] = joins
                        loaded_join += 1

                if not qm.original_query_where_columns.get(i):
                    where_refs = extract_where_column_refs(sql_text)
                    if where_refs:
                        qm.original_query_where_columns[i] = where_refs
                        loaded_where += 1
            except Exception as e:
                print(f"  [WARN] 列参照補完失敗 ({sql_path}): {e}")

        print(
            f"  [INFO] 列参照補完: "
            f"SELECT={loaded_select}, JOIN={loaded_join}, WHERE={loaded_where}"
        )

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

        # required_columns推定が空だったため全列フォールバックした回数を表示
        if self.mv_sql_generator and hasattr(self.mv_sql_generator, "mv_generator"):
            mv_gen = self.mv_sql_generator.mv_generator
            if hasattr(mv_gen, "get_fallback_stats"):
                stats = mv_gen.get_fallback_stats()
                total_fb = stats.get("total", 0)
                by_node = stats.get("by_node", {})
                by_reason = stats.get("by_reason", {})
                root_keep_total = stats.get("root_preserve_total", 0)
                print("\nフォールバック集計 (required_columnsが空 -> 全列選択):")
                print(f"  合計回数: {total_fb}")
                if by_node:
                    top_nodes = sorted(by_node.items(), key=lambda x: x[1], reverse=True)[:10]
                    print("  上位ノード:")
                    for node_id, cnt in top_nodes:
                        print(f"    - {node_id}: {cnt}")
                else:
                    print("  ノード別フォールバック: なし")
                if by_reason:
                    print("  理由別:")
                    for reason, cnt in sorted(by_reason.items(), key=lambda x: x[1], reverse=True):
                        print(f"    - {reason}: {cnt}")
                print(f"  ルート安全策による全列保持: {root_keep_total}")

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
