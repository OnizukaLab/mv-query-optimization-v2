"""
マイグレーションプランのコストを計算するスクリプト（EXPLAIN JSON使用版）
ちょっと値が違いすぎるかも、limitがくせ者
使い方:
    python experiments/small_test_ver2/migration/advanced_migration_costs.py --query-set job_like
    python experiments/small_test_ver2/migration/advanced_migration_costs.py --query-set explicit_join
"""

import json
import pickle
import sys
from pathlib import Path
from typing import Dict, List

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

class MigrationCostCalculator:
    """マイグレーションコストの計算"""
    
    def __init__(self, query_set: str = "job_like"):
        """
        Args:
            query_set: クエリセット名
        """
        self.query_set = query_set
        
        # パス設定
        base_dir = Path(__file__).parent.parent
        self.migration_dir = base_dir / "04_migration" / query_set
        self.pickle_path = base_dir / "03_parsed" / query_set / "qp_class.pkl"

        # データロード
        self.qp = self._load_qp()
        self.plans = self._load_migration_plans()
        self.node_costs=self.qp.qm.original_subquery_costs
        self.costs = {}
    
    def _load_qp(self):
        """QueryParserをpickleファイルからロード"""
        if not self.pickle_path.exists():
            raise FileNotFoundError(f"qp_class.pkl not found: {self.pickle_path}")
        with open(self.pickle_path, 'rb') as f:
            return pickle.load(f)
        
    def _load_migration_plans(self) -> Dict[str, Dict[str, str]]:
        """マイグレーションプランをJSONファイルからロード"""
        plans_path = self.migration_dir / "migration_plans.json"
        
        if not plans_path.exists():
            raise FileNotFoundError(f"migration_plans.json not found: {plans_path}")
        
        with open(plans_path, 'r', encoding='utf-8') as f:
            return json.load(f)
        

    def calculate_all_costs(self) -> Dict[str, Dict[str, float]]:
        """すべてのノードのマイグレーションコストを計算"""
        
        for node_id, plans in self.plans.items():
            self.costs[node_id] = {}

            for plan_key, plan in plans.items():
                if not plan.startswith("CREATE MATERIALIZED VIEW"):
                    self.costs[node_id][plan_key] = 0.0
                    continue

                # plan_keyを安全にパース（eval()の代わりにjson.loads()を使用）
                try:
                    if plan_key == "[]":
                        dependencies = []
                    else:
                        # Pythonのリスト表現をJSONに変換してパース
                        # "['leaf_1', 'leaf_2']" -> '["leaf_1", "leaf_2"]'
                        json_str = plan_key.replace("'", '"')
                        dependencies = json.loads(json_str)
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"警告: {node_id} の plan_key '{plan_key}' のパースに失敗: {e}")
                    dependencies = []

                # マイグレーションコスト = ターゲットコスト - 依存コストの合計
                target_cost = self.node_costs.get(node_id, 0.0)
                dependency_cost = sum(self.node_costs.get(dep, 0.0) for dep in dependencies)
                cost = target_cost - dependency_cost

                self.costs[node_id][plan_key] = cost

        self._save_costs()
        print(f"完了: {len(self.costs)} ノード処理済み")
        return self.costs
    
    def _save_costs(self):
        """コスト情報をJSONファイルに保存"""
        output_path = self.migration_dir / "migration_costs_without_ex.json"

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.costs, f, ensure_ascii=False, indent=2)

        print(f"マイグレーションコスト保存完了: {output_path}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="マイグレーションプランのコスト計算")
    parser.add_argument(
        "--query-set",
        type=str,
        default="job_like",
        help="使用するクエリセットの名前 (デフォルト: job_like)"
    )

    args = parser.parse_args()

    # コスト計算実行
    calculator = MigrationCostCalculator(query_set=args.query_set)
    calculator.calculate_all_costs()


