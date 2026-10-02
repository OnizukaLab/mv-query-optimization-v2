# マイグレーションプランを取得　MVを使用しないものだけSQL生成
import argparse
import psycopg2
import re 
import json
import pickle
import sys
from pathlib import Path
from itertools import combinations, product
from typing import List, Dict, Any

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from src.core.query_parser import QueryParser
from experiments.small_test_ver2.mv_generation.simple_mv_sql_generator import SimpleMVSQLGenerator

class GetMigrationPlans:
    """MVのマイグレーションプランを取得"""
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

        self.mvs: list | None = None
        self.time_ids: list | None = None

        self.sql: Dict[str, str] | None = None

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


    # 全ての子孫ノードを取得する(stackを使った深さ優先探索)
    def get_all_child_nodes(self, node_id: str) -> list[str]:

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
        # setで重複を排除してソート済みリストで返す
        return sorted(set(all_children))
    
    # def _filter_outermost_nodes(self, candidate_nodes: list[str]) -> list[str]:
    #     """包含関係にあるノードの中で、最も外側（親）のノードのみを返す"""
    #     if not self.qp or not hasattr(self.qp, 'qm'):
    #         return candidate_nodes
        
    #     # 各候補ノードの子孫ノードを取得
    #     descendants_map = {}
    #     for node in candidate_nodes:
    #         descendants_map[node] = set(self.get_all_child_nodes(node))
        
    #     # 他のノードに含まれていないノード（最も外側）のみを抽出
    #     outermost_nodes = []
        
    #     for node in candidate_nodes:
    #         is_contained = False
            
    #         # このノードが他のノードの子孫に含まれているかチェック
    #         for other_node in candidate_nodes:
    #             if node != other_node and node in descendants_map[other_node]:
    #                 is_contained = True
    #                 break
            
    #         # 他のノードに含まれていない場合のみ追加
    #         if not is_contained:
    #             outermost_nodes.append(node)
        
    #     return sorted(outermost_nodes)
    
    # # 作成したいノードのべき集合を取得
    # def enumerate_all_combinations(self, target_mv: str):
        
    #     #　作成したいMVとその子孫ノード
    #     dependent_nodes = [target_mv]
    #     dependent_nodes.extend(self.get_all_child_nodes(target_mv))

    #     # べき集合を生成
    #     all_mv_comb = []
    #     for r in range(len(dependent_nodes) + 1):
    #         for subset in combinations(dependent_nodes, r):
    #             all_mv_comb.append(sorted(subset))

    #     return all_mv_comb
    
    def _generate_valid_plans_recursively(self, node_id: str, memo: Dict[str, List[List[str]]] = None) -> List[List[str]]:
        """
        指定されたノード以下のサブツリーで、
        「包含関係にある場合は親を優先する（最も外側）」という条件を満たす
        有効な組み合わせのリストを再帰的に生成する。
        
        戻り値の例: [[Parent], [ChildA, ChildB], [ChildA], [ChildB], []]
        """
        if memo is None:
            memo = {}
        if node_id in memo:
            return memo[node_id]

        # 1. 子ノードを取得 (QueryParserの構造に依存)
        children = []
        if self.qp and hasattr(self.qp, 'qm') and node_id in self.qp.qm.non_leaf_nodes_info:
            children = self.qp.qm.non_leaf_nodes_info[node_id].children
        
        # --- 分岐B: このノードを選択しない（子孫に委ねる）場合の組み合わせ ---
        
        if not children:
            # 子がいない場合、"自分を選ばない" 選択肢は "空集合" のみ
            decomposed_plans = [[]]
        else:
            # 各子ノードの有効プランを取得
            child_plans_list = []
            for child in children:
                child_plans_list.append(self._generate_valid_plans_recursively(child, memo))
            
            # 子ノードごとのプランの直積をとる
            # 例: 子1候補=[[A],[]], 子2候補=[[B],[]] -> [[A,B], [A], [B], []]
            decomposed_plans = []
            for combo in product(*child_plans_list):
                # フラットなリストに結合
                flattened = []
                for item in combo:
                    flattened.extend(item)
                decomposed_plans.append(sorted(flattened))

        # --- 分岐A: このノード自身を選択する場合 ---
        # 親を選んだら子は選べないので、自分単体のリストになる
        myself_plan = [[node_id]]

        # 結果は A と B の合計
        # ※ childrenがない(Leaf)場合も、[[node_id], []] となり矛盾しない
        result = myself_plan + decomposed_plans
        
        memo[node_id] = result
        return result
    
    def generate_mv_sql_with_existing(self, node_id: str, existing_mvs: list[str]) -> str | None:
        """既存のMVを利用して新しいMVのSQLを作成（generate_mv_sqlを使用）"""
        if self.mv_sql_generator is None:
            print(f"  エラー: MVSQLGeneratorが初期化されていません")
            return None

        return self.mv_sql_generator.generate_mv_sql(
            node_id,
            existing_mvs,
        )
    
    # leaf_nodeのマイグレーションプラン
    def enumerate_leaf_migration_plans(
            self,
            target_mv: str
    ):
        mv_sqls = {}
        mv_sqls[str([target_mv])] = "NON_MIGRATE" # マイグレーションなし
        mv_sql = self.generate_mv_sql_with_existing(target_mv, [])
        if mv_sql:
            mv_sqls["[]"] = mv_sql

        return mv_sqls

    # non_leaf_nodeのマイグレーションプラン
    def enumerate_non_leaf_migration_plans(
            self,
            target_mv: str # non_leaf_nodeを想定
    ):
        # べき集合を取得
        # all_mv_comb = self.enumerate_all_combinations(target_mv)

        mv_sqls = {}
        seen = set()
        filtered_children = []

        filtered_children = self._generate_valid_plans_recursively(target_mv)

        # 包含関係を考慮し、重複も排除したMVの組み合わせを取得
        # for mv_set in all_mv_comb:
        #     filtered = self._filter_outermost_nodes(mv_set)
        #     filtered_tuple = tuple(filtered)
        #     if filtered_tuple not in seen:
        #         seen.add(filtered_tuple)
        #         filtered_children.append(filtered)

        # ここでtarget_mvとべき集合の一つを渡してMV作成SQLを取得
        for mv_candidate in filtered_children:
            if target_mv in mv_candidate:
                # マイグレーションなし
                mv_sqls[str(mv_candidate)] = "NON_MIGRATE"
                continue   
            # 新しい MV の SQL を生成、MV候補をキーにして保存
            if not mv_candidate:
                mv_sql = self.generate_mv_sql_with_existing(target_mv, mv_candidate)
                if mv_sql:
                    mv_sqls[str(mv_candidate)] = mv_sql
            else:
                mv_sqls[str(mv_candidate)] = "CREATE MATERIALIZED VIEW"

        return mv_sqls
    

    def save_migration_plans(
            self,
            filename: str = "migration_plans.json"
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

    
    # 全てのノードのマイグレーションプランを取得
    def get_migration_sqls(self):
        """全てのノードに対してマイグレーションプランを取得"""
        if not self.qp or not hasattr(self.qp, 'qm'):
            print("  エラー: QueryParserが初期化されていません")
            return
        
        self.sql = {}

        # 全てのノード（leaf + non_leaf）を取得
        all_nodes = list(self.qp.qm.leaf_nodes_map_r.keys()) + list(self.qp.qm.non_leaf_nodes_info.keys())

        print(f"\n処理対象ノード数: {len(all_nodes)}個")
        print(f"  - leaf_nodes: {len(self.qp.qm.leaf_nodes_map_r)}個")
        print(f"  - non_leaf_nodes: {len(self.qp.qm.non_leaf_nodes_info)}個")
        print("\nマイグレーションプラン生成中...")

        # 進捗表示用
        processed = 0
        total = len(all_nodes)

        # 各ノードのマイグレーションプランを取得
        for node in all_nodes:
            processed += 1
            if processed % 10 == 0 or processed == total:
                print(f"  進捗: {processed}/{total} ({processed*100//total}%)")
            
            # leaf_nodeの場合
            if node.startswith("leaf_"):
                self.sql[node] = self.enumerate_leaf_migration_plans(node)

            # non_leaf_nodeの場合
            elif node.startswith("non_leaf_"):
                self.sql[node] = self.enumerate_non_leaf_migration_plans(node)
        
        print(f"\n✓ 全{total}ノードの処理完了")
        # JSONファイルとして保存
        self.save_migration_plans()

if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(description="MVマイグレーションプラン列挙")
    parser.add_argument(
        "--query-set",
        type=str,
        default="job_like",
        help="使用するクエリセットの名前 (デフォルト: job_like)"
    )

    args = parser.parse_args()

    # Settingsを読み込んでdb_configを提供
    settings = Settings.from_yaml("experiments/small_test_ver2/config.yaml")
    migrator = GetMigrationPlans(settings=settings, query_set=args.query_set)

    migrator.get_migration_sqls()






        

            

        



