#!/usr/bin/env python3
"""
指定したノードのマイグレーションプランをSQL込みで生成

使い方:
    python experiments/small_test_ver2/migration/enumerate_partial_migration_plan.py --query-set job --nodes non_leaf_100 non_leaf_200
    python experiments/small_test_ver2/migration/enumerate_partial_migration_plan.py --query-set job --nodes leaf_50
"""

import argparse
import json
import pickle
import sys
from pathlib import Path
from itertools import product
from typing import List, Dict

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from src.core.query_parser import QueryParser
from experiments.small_test_ver2.mv_generation.simple_mv_sql_generator import SimpleMVSQLGenerator


class PartialMigrationPlanGenerator:
    """指定したノードのマイグレーションプランを生成（SQL込み）"""
    
    def __init__(self, settings: Settings | None = None, query_set: str = "job_like"):
        self.settings = settings
        self.query_set = query_set
        
        # 03_parsed/{queryset}/qp_class.pklから読み込み
        self.parser_file = Path(__file__).parent.parent / "03_parsed" / self.query_set / "qp_class.pkl"
        
        # 読み込んだデータを保持
        self.qp: QueryParser | None = None
        self.mv_sql_generator: SimpleMVSQLGenerator | None = None
        self.schema_provider = None
        
        if self.parser_file and self.parser_file.exists():
            self.load_pickle()
            if self.qp:
                # db_configをsettingsから取得
                db_config = None
                if self.settings and hasattr(self.settings, 'database'):
                    db_config = {
                        'host': self.settings.database.host,
                        'port': self.settings.database.port,
                        'database': self.settings.database.database,
                        'user': self.settings.database.user,
                        'password': self.settings.database.password,
                    }
                # SchemaProviderを作成
                from src.rewrite.schema_provider import SchemaProvider
                self.schema_provider = SchemaProvider(db_config)
                self.mv_sql_generator = SimpleMVSQLGenerator(self.qp, db_config)
    
    def load_pickle(self) -> None:
        """pickleファイルからQueryParserを読み込み"""
        try:
            with open(self.parser_file, 'rb') as f:
                self.qp = pickle.load(f, encoding='bytes')
            print(f"✓ QueryParser読み込み成功: {self.parser_file}")
        except Exception as e:
            print(f"✗ pickleファイルの読み込みに失敗: {e}")
            self.qp = None
    
    def get_all_child_nodes(self, node_id: str) -> list[str]:
        """全ての子孫ノードを取得（深さ優先探索）"""
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
    
    def _generate_valid_plans_recursively(self, node_id: str, memo: Dict[str, List[List[str]]] = None) -> List[List[str]]:
        """
        指定されたノード以下のサブツリーで、
        包含関係を考慮した有効な組み合わせを再帰的に生成
        """
        if memo is None:
            memo = {}
        if node_id in memo:
            return memo[node_id]
        
        # 子ノードを取得
        children = []
        if self.qp and hasattr(self.qp, 'qm') and node_id in self.qp.qm.non_leaf_nodes_info:
            children = self.qp.qm.non_leaf_nodes_info[node_id].children
        
        # このノードを選択しない場合の組み合わせ
        if not children:
            decomposed_plans = [[]]
        else:
            child_plans_list = []
            for child in children:
                child_plans_list.append(self._generate_valid_plans_recursively(child, memo))
            
            decomposed_plans = []
            for combo in product(*child_plans_list):
                flattened = []
                for item in combo:
                    flattened.extend(item)
                decomposed_plans.append(sorted(flattened))
        
        # このノード自身を選択する場合
        myself_plan = [[node_id]]
        
        result = myself_plan + decomposed_plans
        memo[node_id] = result
        return result
    
    def generate_mv_sql_with_existing(self, node_id: str, existing_mvs: list[str]) -> str | None:
        """既存のMVを利用して新しいMVのSQLを作成"""
        if self.mv_sql_generator is None:
            print(f"  エラー: MVSQLGeneratorが初期化されていません")
            return None
        
        return self.mv_sql_generator.generate_mv_sql(node_id, existing_mvs)
    
    def enumerate_leaf_migration_plans(self, target_mv: str) -> Dict[str, str]:
        """leafノードのマイグレーションプランを生成（SQL込み）"""
        mv_sqls = {}
        
        # マイグレーションなし（既存のMVを使用）
        mv_sqls[str([target_mv])] = "NON_MIGRATE"
        
        # 依存なしで作成
        mv_sql = self.generate_mv_sql_with_existing(target_mv, [])
        if mv_sql:
            mv_sqls["[]"] = mv_sql
        
        return mv_sqls
    
    def enumerate_non_leaf_migration_plans(self, target_mv: str) -> Dict[str, str]:
        """non_leafノードのマイグレーションプランを生成（SQL込み）"""
        mv_sqls = {}
        
        # 包含関係を考慮した有効な組み合わせを取得
        filtered_children = self._generate_valid_plans_recursively(target_mv)
        
        for mv_candidate in filtered_children:
            if target_mv in mv_candidate:
                # マイグレーションなし
                mv_sqls[str(mv_candidate)] = "NON_MIGRATE"
                continue
            
            # 新しいMVのSQLを生成
            if not mv_candidate:
                # 依存MVなしで作成
                mv_sql = self.generate_mv_sql_with_existing(target_mv, mv_candidate)
                if mv_sql:
                    mv_sqls[str(mv_candidate)] = mv_sql
            else:
                # 依存MVありで作成（実際のSQLを生成）
                mv_sql = self.generate_mv_sql_with_existing(target_mv, mv_candidate)
                if mv_sql:
                    mv_sqls[str(mv_candidate)] = mv_sql
                else:
                    # 生成失敗時はプレースホルダー
                    mv_sqls[str(mv_candidate)] = "CREATE MATERIALIZED VIEW (generation failed)"
        
        return mv_sqls
    
    def generate_partial_plans(self, node_ids: List[str]) -> tuple[Dict[str, Dict[str, str]], str]:
        """指定したノードのマイグレーションプランを生成
        
        Returns:
            (plans_dict, suggested_filename): プランの辞書とノードIDを含む推奨ファイル名
        """
        if not self.qp or not hasattr(self.qp, 'qm'):
            print("✗ エラー: QueryParserが初期化されていません")
            return {}, "partial_migration_plans.json"
        
        result = {}
        total = len(node_ids)
        
        print(f"\n指定されたノード数: {total}個")
        print("マイグレーションプラン生成中（SQL込み）...\n")
        
        for i, node_id in enumerate(node_ids, 1):
            print(f"  [{i}/{total}] {node_id} を処理中...")
            
            # ノードの存在確認
            is_leaf = node_id in self.qp.qm.leaf_nodes_map_r
            is_non_leaf = node_id in self.qp.qm.non_leaf_nodes_info
            
            if not (is_leaf or is_non_leaf):
                print(f"    ⚠ 警告: {node_id} が見つかりません")
                continue
            
            # マイグレーションプランを生成
            if is_leaf:
                result[node_id] = self.enumerate_leaf_migration_plans(node_id)
                print(f"    ✓ leafノード: {len(result[node_id])}個のプラン生成")
            else:
                result[node_id] = self.enumerate_non_leaf_migration_plans(node_id)
                print(f"    ✓ non_leafノード: {len(result[node_id])}個のプラン生成")
        
        print(f"\n✓ 全{total}ノードの処理完了")
        
        # ファイル名を生成（ノードIDを含める）
        node_ids_str = "_".join(node_ids[:5])  # 最初の5個まで使用
        if len(node_ids) > 5:
            node_ids_str += f"_and_{len(node_ids) - 5}_more"
        suggested_filename = f"partial_migration_{node_ids_str}.json"
        
        return result, suggested_filename
    
    def save_partial_plans(self, plans: Dict[str, Dict[str, str]], filename: str = "partial_migration_plans.json"):
        """マイグレーションプランをJSONファイルに保存"""
        if not plans:
            print("✗ エラー: 保存するプランがありません")
            return
        
        # 出力dirのパス
        output_dir = Path(__file__).parent.parent / "04_migration" / self.query_set
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # ファイルパス
        output_file = output_dir / filename
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(plans, f, indent=2, ensure_ascii=False)
            print(f"\n✓ マイグレーションプランを保存: {output_file}")
            print(f"  - ノード数: {len(plans)}個")
            
            # 統計情報を表示
            total_plans = sum(len(node_plans) for node_plans in plans.values())
            sql_plans = sum(
                1 for node_plans in plans.values() 
                for plan_sql in node_plans.values() 
                if plan_sql not in ["NON_MIGRATE", "CREATE MATERIALIZED VIEW (generation failed)"]
            )
            print(f"  - 総プラン数: {total_plans}個")
            print(f"  - SQL生成済み: {sql_plans}個")
            
        except Exception as e:
            print(f"✗ JSONファイルの保存に失敗: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="指定したノードのマイグレーションプランを生成（SQL込み）"
    )
    parser.add_argument(
        "--query-set",
        type=str,
        default="job_like",
        help="使用するクエリセット名 (デフォルト: job_like)"
    )
    parser.add_argument(
        "--nodes",
        type=str,
        nargs='+',
        required=True,
        help="マイグレーションプランを生成するノードID（例: non_leaf_100 leaf_50）"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="partial_migration_plans.json",
        help="出力ファイル名 (デフォルト: partial_migration_plans.json)"
    )
    
    args = parser.parse_args()
    
    # Settingsを読み込み
    settings = Settings.from_yaml("experiments/small_test_ver2/config.yaml")
    
    # ジェネレーターを初期化
    generator = PartialMigrationPlanGenerator(settings=settings, query_set=args.query_set)
    
    # 指定されたノードのプランを生成
    plans, suggested_filename = generator.generate_partial_plans(args.nodes)
    
    # ファイル名が指定されていない場合は、自動生成された名前を使用
    output_filename = args.output if args.output != "partial_migration_plans.json" else suggested_filename
    
    # JSONファイルに保存
    if plans:
        generator.save_partial_plans(plans, filename=output_filename)
