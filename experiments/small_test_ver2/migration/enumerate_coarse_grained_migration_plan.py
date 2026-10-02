# 粗粒度マイグレーションプランを取得（Aggregate, Hash Join, Sort, Materializeノードのみ）
import argparse
import psycopg2
import re 
import json
import pickle
import sys
from pathlib import Path
from itertools import combinations, product
from typing import List, Dict, Any, Set

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from src.core.query_parser import QueryParser
from experiments.small_test_ver2.mv_generation.simple_mv_sql_generator import SimpleMVSQLGenerator

class CoarseGrainedMigrationPlanner:
    """粗粒度でのMVマイグレーションプラン生成（重要ノードのみ）"""
    
    # MV候補として考慮する重要なノードタイプ
    INTERESTING_NODE_TYPES = {
        'Aggregate',
        'Hash Join', 
        'Sort',
        'Materialize'
    }
    
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

        self.sql: Dict[str, str] | None = None

        self.mv_sql_generator: SimpleMVSQLGenerator | None = None
        self.schema_provider = None  # 再利用するSchemaProvider

        # 重要ノードのセット
        self.interesting_nodes: Set[str] = set()

        if self.parser_file and self.parser_file.exists():
            self.load_pickle()
            if self.qp:
                # 重要ノードを抽出
                self._identify_interesting_nodes()
                
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
        """QueryParserをpickleファイルからロード"""
        try:
            with open(self.parser_file, 'rb') as f:
                self.qp = pickle.load(f, encoding='bytes')
            print(f"✓ QueryParserをロード: {self.parser_file}")
        except Exception as e:
            print(f"✗ pickle ファイルの読み込みに失敗しました: {e}")
            self.qp = None

    def _identify_interesting_nodes(self) -> None:
        """重要なノードタイプ（Aggregate, Hash Join, Sort, Materialize）を識別"""
        if not self.qp or not hasattr(self.qp, 'qm'):
            return
        
        print("\n" + "="*70)
        print("重要ノードを識別中...")
        print(f"対象ノードタイプ: {', '.join(sorted(self.INTERESTING_NODE_TYPES))}")
        print("="*70)
        
        # non_leaf_nodesから重要なノードを抽出
        for node_id, node_info in self.qp.qm.non_leaf_nodes_info.items():
            node_type = node_info.operator
            
            # 重要なノードタイプに該当するかチェック
            if node_type in self.INTERESTING_NODE_TYPES:
                self.interesting_nodes.add(node_id)
                print(f"  ✓ {node_id}: {node_type}")
        
        print(f"\n識別された重要ノード数: {len(self.interesting_nodes)}個")
        print("="*70 + "\n")

    def get_all_child_nodes(self, node_id: str) -> list[str]:
        """全ての子孫ノードを取得する(stackを使った深さ優先探索)"""
        if not self.qp or not hasattr(self.qp, 'qm'):
            return []
        
        all_children = []
        stack = [node_id]

        while stack:
            current = stack.pop()
            if current in self.qp.qm.non_leaf_nodes_info:
                children = self.qp.qm.non_leaf_nodes_info[current].children
                all_children.extend(children)
                stack.extend(children)
        
        return sorted(set(all_children))
    
    def _get_interesting_descendants(self, node_id: str) -> Set[str]:
        """指定ノードの子孫のうち、重要ノードのみを取得"""
        all_descendants = self.get_all_child_nodes(node_id)
        return self.interesting_nodes.intersection(all_descendants)
    
    def _generate_valid_plans_recursively(
        self, 
        node_id: str, 
        memo: Dict[str, List[List[str]]] = None
    ) -> List[List[str]]:
        """
        指定されたノード以下のサブツリーで、重要ノードのみを考慮した
        有効な組み合わせのリストを再帰的に生成する
        
        戻り値の例: [[Parent], [ChildA, ChildB], [ChildA], [ChildB], []]
        """
        if memo is None:
            memo = {}
        if node_id in memo:
            return memo[node_id]

        # 1. 子ノードを取得
        children = []
        if self.qp and hasattr(self.qp, 'qm') and node_id in self.qp.qm.non_leaf_nodes_info:
            all_children = self.qp.qm.non_leaf_nodes_info[node_id].children
            # 重要ノードのみをフィルタ
            children = [c for c in all_children if c in self.interesting_nodes]
        
        # 分岐B: このノードを選択しない（子孫に委ねる）場合の組み合わせ
        if not children:
            # 子がいない場合、"自分を選ばない" 選択肢は "空集合" のみ
            decomposed_plans = [[]]
        else:
            # 各子ノードの有効プランを取得
            child_plans_list = []
            for child in children:
                child_plans_list.append(self._generate_valid_plans_recursively(child, memo))
            
            # 子ノードごとのプランの直積をとる
            decomposed_plans = []
            for combo in product(*child_plans_list):
                # フラットなリストに結合
                flattened = []
                for item in combo:
                    flattened.extend(item)
                decomposed_plans.append(sorted(flattened))

        # 分岐A: このノード自身を選択する場合
        myself_plan = [[node_id]]

        # 結果は A と B の合計
        result = myself_plan + decomposed_plans
        
        memo[node_id] = result
        return result
    
    def generate_mv_sql_with_existing(self, node_id: str, existing_mvs: list[str]) -> str | None:
        """既存のMVを利用して新しいMVのSQLを作成"""
        if self.mv_sql_generator is None:
            print(f"  エラー: MVSQLGeneratorが初期化されていません")
            return None

        return self.mv_sql_generator.generate_mv_sql(
            node_id,
            existing_mvs,
        )
    
    def enumerate_node_migration_plans(self, target_mv: str) -> Dict[str, str]:
        """
        指定ノードのマイグレーションプランを生成
        重要ノードのみを考慮した組み合わせを生成
        """
        mv_sqls = {}
        
        # このノード自身が含まれる場合はマイグレーションなし
        mv_sqls[str([target_mv])] = "NON_MIGRATE"
        
        # 重要な子孫ノードのみを考慮した組み合わせを生成
        filtered_children = self._generate_valid_plans_recursively(target_mv)
        
        for mv_candidate in filtered_children:
            if target_mv in mv_candidate:
                # 自分自身が含まれる場合はスキップ（既に追加済み）
                continue
            
            # 新しい MV の SQL を生成
            if not mv_candidate:
                # 依存MVなし（ベースプラン）
                mv_sql = self.generate_mv_sql_with_existing(target_mv, mv_candidate)
                if mv_sql:
                    mv_sqls[str(mv_candidate)] = mv_sql
            else:
                # 依存MVあり（プレースホルダー）
                mv_sqls[str(mv_candidate)] = "CREATE MATERIALIZED VIEW"

        return mv_sqls
    
    def save_migration_plans(self, filename: str = "migration_plans.json"):
        """マイグレーションプランをJSONファイルに保存"""
        if not self.sql:
            print("エラー: マイグレーションプランが生成されていません")
            return
        
        # 出力dirのパス
        output_dir = Path(__file__).parent.parent / "04_migration" / self.query_set
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / filename

        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.sql, f, indent=2, ensure_ascii=False)
            print(f"\n✓ マイグレーションプランを保存しました: {output_file}")
            
            # 統計情報を表示
            total_plans = sum(len(plans) for plans in self.sql.values())
            print(f"  - 対象ノード数: {len(self.sql)}個")
            print(f"  - 総プラン数: {total_plans}個")
            
        except Exception as e:
            print(f"✗ JSONファイルの保存に失敗しました: {e}")
    
    def get_migration_sqls(self):
        """重要ノードに対してマイグレーションプランを取得"""
        if not self.qp or not hasattr(self.qp, 'qm'):
            print("  エラー: QueryParserが初期化されていません")
            return
        
        if not self.interesting_nodes:
            print("  エラー: 重要ノードが識別されていません")
            return
        
        self.sql = {}

        print(f"\n" + "="*70)
        print(f"粗粒度マイグレーションプラン生成中...")
        print(f"対象ノード数: {len(self.interesting_nodes)}個")
        print("="*70 + "\n")

        # 進捗表示用
        processed = 0
        total = len(self.interesting_nodes)

        # 各重要ノードのマイグレーションプランを取得
        for node_id in sorted(self.interesting_nodes):
            processed += 1
            
            node_type = self.qp.qm.non_leaf_nodes_info[node_id].operator
            print(f"[{processed}/{total}] {node_id} ({node_type})")
            
            self.sql[node_id] = self.enumerate_node_migration_plans(node_id)
            
            print(f"  → {len(self.sql[node_id])}個のプラン生成")
        
        print(f"\n" + "="*70)
        print(f"✓ 全{total}ノードの処理完了")
        print("="*70)
        
        # JSONファイルとして保存
        self.save_migration_plans()


def main():
    parser = argparse.ArgumentParser(
        description="粗粒度MVマイグレーションプラン列挙（Aggregate, Hash Join, Sort, Materializeのみ）"
    )
    parser.add_argument(
        "--query-set",
        type=str,
        default="job_like",
        help="使用するクエリセットの名前 (デフォルト: job_like)"
    )

    args = parser.parse_args()

    # Settingsを読み込んでdb_configを提供
    settings = Settings.from_yaml("experiments/small_test_ver2/config.yaml")
    planner = CoarseGrainedMigrationPlanner(settings=settings, query_set=args.query_set)

    planner.get_migration_sqls()


if __name__ == "__main__":
    main()
