#!/usr/bin/env python3
"""
マイグレーションプランのコストを計算（行数ベース推定版）

使い方:
    python experiments/small_test_ver2/migration/migration_cost_rows_based.py --query-set job_like
"""

import json
import pickle
import sys
import yaml
from pathlib import Path
from typing import Dict, List
import psycopg2

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings


class MigrationCostCalculatorRowsBased:
    """行数ベースの推定を使ったマイグレーションコスト計算"""
    
    def __init__(self, settings: Settings, query_set: str = "job_like"):
        """
        Args:
            settings: config.yamlから読み込んだSettings
            query_set: クエリセット名
        """
        self.settings = settings
        self.query_set = query_set
        
        # パス設定
        base_dir = Path(__file__).parent.parent
        self.migration_dir = base_dir / "04_migration" / query_set
        self.pickle_path = base_dir / "03_parsed" / query_set / "qp_class.pkl"
        
        # データロード
        self.qp = self._load_qp()
        self.plans = self._load_migration_plans()
        self.node_costs = {}  # {node_id: cost} - []プランのベースコスト
        self.costs = {}
    
    def _get_connection(self):
        """データベース接続を取得（config.yamlの設定を使用）"""
        return psycopg2.connect(
            host=self.settings.database.host,
            port=self.settings.database.port,
            dbname=self.settings.database.database,
            user=self.settings.database.user,
            password=self.settings.database.password
        )
    
    def _load_qp(self):
        """QueryParserをpickleファイルからロード"""
        if not self.pickle_path.exists():
            raise FileNotFoundError(f"qp_class.pkl not found: {self.pickle_path}")
        
        with open(self.pickle_path, 'rb') as f:
            qp = pickle.load(f)
        
        print(f"QueryParser loaded from: {self.pickle_path}")
        print(f"  - ノード数: {len(qp.node_list)}")
        print(f"  - non_leaf_nodes_info: {len(qp.qm.non_leaf_nodes_info)} ノード")
        
        return qp
    
    def _load_migration_plans(self) -> Dict[str, Dict[str, str]]:
        """マイグレーションプランをJSONファイルからロード"""
        plans_path = self.migration_dir / "migration_plans.json"
        
        if not plans_path.exists():
            raise FileNotFoundError(f"migration_plans.json not found: {plans_path}")
        
        with open(plans_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def extract_base_costs_with_explain(self) -> Dict[str, float]:
        """各ノードの[]プランに対してEXPLAINを実行し、ベースコストを取得
        
        Returns:
            {node_id: base_cost, ...}
        """
        print(f"\nEXPLAIN実行中（クエリセット: {self.query_set}）...")
        print("※ []プランのみEXPLAINを実行します\n")
        
        base_costs = {}
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                for node_id, plans in self.plans.items():
                    # []プランのSQLを取得
                    base_plan_sql = plans.get("[]")
                    
                    if not base_plan_sql or not base_plan_sql.startswith("CREATE MATERIALIZED VIEW"):
                        continue
                    
                    # CREATE MATERIALIZED VIEW部分を除去してSELECT文のみに
                    select_sql = self._extract_select_from_create_mv(base_plan_sql)
                    
                    # EXPLAINを実行
                    try:
                        cur.execute(f"EXPLAIN (FORMAT JSON) {select_sql}")
                        explain_result = cur.fetchone()[0]
                        
                        # Total Costを抽出
                        total_cost = explain_result[0]["Plan"]["Total Cost"]
                        base_costs[node_id] = total_cost
                        
                        print(f"  {node_id}: {total_cost:.2f}")
                    
                    except Exception as e:
                        print(f"  {node_id}: エラー - {e}")
                        base_costs[node_id] = 0.0
        
        self.node_costs = base_costs
        return base_costs
    
    def _extract_select_from_create_mv(self, create_mv_sql: str) -> str:
        """CREATE MATERIALIZED VIEW文からSELECT文を抽出
        
        Args:
            create_mv_sql: CREATE MATERIALIZED VIEW ... AS SELECT ...
        
        Returns:
            SELECT文のみ
        """
        # "AS"以降を抽出
        if " AS\n" in create_mv_sql:
            return create_mv_sql.split(" AS\n", 1)[1].strip()
        elif " AS " in create_mv_sql:
            return create_mv_sql.split(" AS ", 1)[1].strip()
        else:
            return create_mv_sql
    
    def calculate_all_costs(self) -> Dict[str, Dict[str, float]]:
        """すべてのマイグレーションコストを計算（行数ベース推定）"""
        print(f"\nマイグレーションコスト計算中（行数ベース推定）...")
        print("※ 依存MVありプランは行数から削減率を推定します\n")
        
        for node_id, plans in self.plans.items():
            self.costs[node_id] = {}
            base_cost = self.node_costs.get(node_id, 0.0)
            
            for plan_key, plan in plans.items():
                # 同じノードを再利用する場合（前の時刻と同じMV）
                if not plan.startswith("CREATE MATERIALIZED VIEW"):
                    self.costs[node_id][plan_key] = 0.0
                    continue
                
                # []プランの場合: ベースコスト
                if plan_key == "[]":
                    self.costs[node_id][plan_key] = base_cost
                    print(f"  {node_id}[{plan_key}]: {base_cost:.2f} (ベースコスト)")
                
                # 依存MVがある場合: 行数ベースの推定
                else:
                    dependencies = eval(plan_key)
                    
                    # 行数ベースの削減率を計算
                    reduction_factor = self._calculate_reduction_factor_by_rows(node_id, dependencies)
                    
                    # 推定コスト = ベースコスト × (1 - 削減率)
                    estimated_cost = base_cost * (1.0 - reduction_factor)
                    
                    # 最小コストを設定（完全に0にならないように）
                    min_cost = base_cost * 0.02  # ベースコストの2%
                    self.costs[node_id][plan_key] = max(estimated_cost, min_cost)
                    
                    print(f"  {node_id}[{plan_key}]: {self.costs[node_id][plan_key]:.2f} "
                          f"(削減率: {reduction_factor*100:.1f}%, 依存: {dependencies})")
        
        self._save_costs()
        print(f"\n完了: {len(self.costs)} ノード処理済み")
        return self.costs
    
    def _calculate_reduction_factor_by_rows(self, node_id: str, dependencies: List[str]) -> float:
        """依存MVによるコスト削減率を行数ベースで計算
        
        Args:
            node_id: ターゲットノードID
            dependencies: 依存MVのリスト
        
        Returns:
            削減率 (0.0 ~ 1.0)
        """
        # ターゲットノードの行数を取得
        target_rows = self._get_node_rows(node_id)
        
        if target_rows == 0:
            target_rows = 1  # ゼロ除算を回避
        
        total_reduction = 0.0
        
        for dep in dependencies:
            # 依存MVの行数を取得
            dep_rows = self._get_node_rows(dep)
            
            if dep_rows == 0:
                continue
            
            # 削減貢献度を計算
            # 依存MVの行数がターゲットの行数に占める割合
            contribution = min(dep_rows / target_rows, 0.95)  # 最大95%削減
            
            # 複数MVの相互作用を考慮（独立事象として扱う）
            # 削減率 = 1 - (1 - r1) * (1 - r2) * ...
            # 効率係数0.7をかける（MVの実際の削減効果は理論値の70%と仮定）
            total_reduction = 1 - (1 - total_reduction) * (1 - contribution * 0.7)
        
        # 最大98%まで削減
        return min(total_reduction, 0.98)
    
    def _get_node_rows(self, node_id: str) -> int:
        """ノードの推定行数を取得
        
        Args:
            node_id: ノードID
        
        Returns:
            推定行数
        """
        # non_leaf_nodes_infoから行数を取得
        if hasattr(self.qp.qm, 'non_leaf_nodes_info') and node_id in self.qp.qm.non_leaf_nodes_info:
            node_info = self.qp.qm.non_leaf_nodes_info[node_id]
            if hasattr(node_info, 'rows'):
                return int(node_info.rows)
        
        # 葉ノードの場合、サイズと幅から推定
        if node_id in self.qp.qm.leaf_nodes_map_r:
            return self._estimate_leaf_rows(node_id)
        
        # デフォルト値
        return 1
    
    def _estimate_leaf_rows(self, leaf_id: str) -> int:
        """葉ノードの推定行数を計算
        
        Args:
            leaf_id: 葉ノードID
        
        Returns:
            推定行数
        """
        # subquery_sizesとsubquery_widthsから推定
        size = self.qp.qm.subquery_sizes.get(leaf_id, 0)
        
        # widthが存在する場合
        if hasattr(self.qp.qm, 'subquery_widths'):
            width = self.qp.qm.subquery_widths.get(leaf_id, 1)
        else:
            # widthが存在しない場合、デフォルト値を使用
            width = 100  # 1行あたり平均100バイトと仮定
        
        if width == 0:
            width = 1
        
        # 行数 = サイズ / 幅
        estimated_rows = max(size // width, 1)
        
        return estimated_rows
    
    def _save_costs(self):
        """コスト情報をJSONファイルに保存"""
        output_path = self.migration_dir / "migration_costs_rows_based.json"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.costs, f, indent=2, ensure_ascii=False)
        
        print(f"\n保存完了: {output_path}")
    
    def compare_with_existing(self):
        """既存のコスト計算結果と比較"""
        existing_path = self.migration_dir / "migration_costs_with_ex.json"
        
        if not existing_path.exists():
            print(f"\n比較対象ファイルが見つかりません: {existing_path}")
            return
        
        with open(existing_path, 'r', encoding='utf-8') as f:
            existing_costs = json.load(f)
        
        print(f"\n既存手法との比較（{existing_path.name}）:")
        print("-" * 80)
        
        total_diff = 0.0
        count = 0
        
        for node_id in self.costs.keys():
            if node_id not in existing_costs:
                continue
            
            print(f"\n{node_id}:")
            
            for plan_key in self.costs[node_id].keys():
                if plan_key not in existing_costs[node_id]:
                    continue
                
                new_cost = self.costs[node_id][plan_key]
                old_cost = existing_costs[node_id][plan_key]
                diff = new_cost - old_cost
                
                if plan_key != "[]" and old_cost > 0:  # []プランと0.0は比較対象外
                    total_diff += abs(diff)
                    count += 1
                
                print(f"  {plan_key:30s}: 新={new_cost:8.2f}, 旧={old_cost:8.2f}, 差={diff:+8.2f}")
        
        if count > 0:
            avg_diff = total_diff / count
            print(f"\n平均絶対誤差 (MAE): {avg_diff:.2f}")
            print(f"比較対象プラン数: {count}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="マイグレーションプランのコスト計算（行数ベース推定）")
    parser.add_argument(
        "--query-set",
        type=str,
        default="job_like",
        help="使用するクエリセットの名前 (デフォルト: job_like)"
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="既存のコスト計算結果と比較"
    )
    
    args = parser.parse_args()
    
    # config.yamlから設定を読み込み（UTF-8で明示的に読み込み）
    config_path = Path(__file__).parent.parent / "config.yaml"
    
    # UTF-8でYAMLを読み込む
    with open(config_path, 'r', encoding='utf-8') as f:
        config_data = yaml.safe_load(f)
    
    # 一時ファイルに書き込んでからSettingsを読み込む
    temp_config = config_path.parent / '.temp_config.yaml'
    with open(temp_config, 'w', encoding='utf-8') as f:
        yaml.dump(config_data, f, allow_unicode=True)
    
    try:
        settings = Settings.from_yaml(str(temp_config))
    finally:
        if temp_config.exists():
            temp_config.unlink()
    
    # コスト計算実行
    calculator = MigrationCostCalculatorRowsBased(
        settings=settings,
        query_set=args.query_set
    )
    
    # ステップ1: []プランに対してEXPLAIN実行
    calculator.extract_base_costs_with_explain()
    
    # ステップ2: すべてのプランのコストを計算（行数ベース推定）
    calculator.calculate_all_costs()
    
    # ステップ3: 既存手法と比較（オプション）
    if args.compare:
        calculator.compare_with_existing()
