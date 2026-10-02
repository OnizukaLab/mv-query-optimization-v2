"""
行数と幅を利用したマイグレーションコスト推定

PostgreSQLのオプティマイザが内部で行っている計算式をシミュレーションして、
MVのマイグレーションコストを理論的に推定します。

使い方:
    python experiments/small_test_ver2/migration/row_width_based_costs.py --query-set job_like
    python experiments/small_test_ver2/migration/row_width_based_costs.py --query-set job
"""

import json
import math
import pickle
import sys
from pathlib import Path
from typing import Dict, Optional

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))


class RowWidthBasedCostCalculator:
    """行数と幅を利用したマイグレーションコスト推定"""
    
    # PostgreSQLのコストパラメータ（デフォルト値）
    SEQ_PAGE_COST = 1.0
    CPU_TUPLE_COST = 0.01
    BLOCK_SIZE = 8192
    TUPLE_OVERHEAD = 24  # ヘッダ情報の概算（バイト）
    
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
        self.costs = {}
        
        # 【高速化】ノードIDからインデックスへの辞書を事前作成（O(1)検索用）
        self.node_id_to_index = {node_id: i for i, node_id in enumerate(self.qp.node_list)}
    
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
    
    def _get_node_info(self, node_id: str) -> Optional[Dict]:
        """ノードの行数と幅情報を取得
        
        Args:
            node_id: ノードID
            
        Returns:
            {'rows': int, 'width': int, 'size': int} or None
        """
        # QueryManagerからノード情報を取得
        # qm に rows や width の情報があるか確認
        # 通常、qm.subquery_info や qm.node_stats などに格納されている
        if hasattr(self.qp.qm, 'subquery_info') and node_id in self.qp.qm.subquery_info:
            info = self.qp.qm.subquery_info[node_id]
            return {
                'rows': info.get('rows', 0),
                'width': info.get('width', 0),
                'size': info.get('rows', 0) * info.get('width', 0)
            }
        
        # フォールバック: b_j（サイズ情報）から推定
        # 【高速化】事前作成した辞書を使ってO(1)で検索
        if node_id in self.node_id_to_index:
            node_idx = self.node_id_to_index[node_id]
            if node_idx < len(self.qp.b_j):
                size = self.qp.b_j[node_idx]
                # 幅は推定（平均的な値として100バイトと仮定）
                # より正確にはQueryManagerから取得すべき
                estimated_width = 100
                rows = size / estimated_width if estimated_width > 0 else 0
                
                return {
                    'rows': int(rows),
                    'width': estimated_width,
                    'size': size
                }
        
        return None
    
    def calculate_seq_scan_cost(self, node_id: str) -> float:
        """
        Seq Scanコストを行数と幅から理論的に推定
        
        MVのマイグレーション（作成・全更新）にかかるI/Oコストの指標
        
        Args:
            node_id: ノードID
            
        Returns:
            推定コスト（PostgreSQLコスト単位）
        """
        node_info = self._get_node_info(node_id)
        
        if not node_info:
            return 0.0
        
        rows = node_info.get('rows', 0)
        width = node_info.get('width', 0)
        
        if rows <= 0 or width <= 0:
            return 0.0
        
        # 1行の実サイズ（幅 + ヘッダオーバーヘッド）
        row_size = width + self.TUPLE_OVERHEAD
        
        # 1ページあたりの行数
        tuples_per_page = self.BLOCK_SIZE // row_size
        if tuples_per_page < 1:
            tuples_per_page = 1
        
        # 必要なページ数
        pages = math.ceil(rows / tuples_per_page)
        
        # Seq Scanコスト = I/Oコスト + CPUコスト
        io_cost = pages * self.SEQ_PAGE_COST
        cpu_cost = rows * self.CPU_TUPLE_COST
        
        total_cost = io_cost + cpu_cost
        
        return total_cost
    
    def calculate_migration_cost(
        self,
        node_id: str,
        dependency_ids: list[str]
    ) -> float:
        """
        マイグレーションコストを計算
        
        マイグレーションコスト = ターゲットノードのコスト - 依存ノードのコスト合計
        
        Args:
            node_id: ターゲットノードID
            dependency_ids: 依存するノードIDのリスト
            
        Returns:
            マイグレーションコスト
        """
        # ターゲットノードのコスト
        target_cost = self.calculate_seq_scan_cost(node_id)
        
        # 依存ノードのコスト合計
        dependency_cost = sum(
            self.calculate_seq_scan_cost(dep_id)
            for dep_id in dependency_ids
        )
        
        # マイグレーションコスト（負になる場合は0に丸める）
        migration_cost = max(target_cost - dependency_cost, 0.0)
        
        return migration_cost
    
    def calculate_all_costs(self) -> Dict[str, Dict[str, float]]:
        """すべてのマイグレーションプランのコストを計算"""
        print(f"行数・幅ベースのコスト計算を開始...")
        
        processed_nodes = 0
        skipped_nodes = 0
        
        for node_id, plans in self.plans.items():
            self.costs[node_id] = {}
            
            # ノード情報の取得チェック
            node_info = self._get_node_info(node_id)
            if not node_info:
                # 情報がない場合はスキップ
                for plan_key in plans.keys():
                    self.costs[node_id][plan_key] = 0.0
                skipped_nodes += 1
                continue
            
            processed_nodes += 1
            
            for plan_key, plan in plans.items():
                # NON_MIGRATEや生成失敗のケース
                if not plan.startswith("CREATE MATERIALIZED VIEW"):
                    self.costs[node_id][plan_key] = 0.0
                    continue
                
                # plan_keyを安全にパース
                try:
                    if plan_key == "[]":
                        dependencies = []
                    else:
                        # "['leaf_1', 'leaf_2']" -> ["leaf_1", "leaf_2"]
                        json_str = plan_key.replace("'", '"')
                        dependencies = json.loads(json_str)
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"  警告: {node_id} の plan_key '{plan_key}' のパースに失敗: {e}")
                    dependencies = []
                
                # マイグレーションコストを計算
                cost = self.calculate_migration_cost(node_id, dependencies)
                self.costs[node_id][plan_key] = cost
        
        print(f"完了: {processed_nodes}ノード処理, {skipped_nodes}ノードスキップ")
        
        # 統計情報を表示
        self._print_statistics()
        
        # 結果を保存
        self._save_costs()
        
        return self.costs
    
    def _print_statistics(self):
        """コスト計算の統計情報を表示"""
        all_costs = []
        for node_costs in self.costs.values():
            all_costs.extend(node_costs.values())
        
        if not all_costs:
            return
        
        non_zero_costs = [c for c in all_costs if c > 0]
        
        print(f"\n--- コスト統計 ---")
        print(f"  総プラン数: {len(all_costs)}")
        print(f"  非ゼロコスト数: {len(non_zero_costs)}")
        
        if non_zero_costs:
            print(f"  最小コスト: {min(non_zero_costs):.2f}")
            print(f"  最大コスト: {max(non_zero_costs):.2f}")
            print(f"  平均コスト: {sum(non_zero_costs) / len(non_zero_costs):.2f}")
            print(f"  中央値: {sorted(non_zero_costs)[len(non_zero_costs)//2]:.2f}")
    
    def _save_costs(self):
        """コスト情報をJSONファイルに保存"""
        output_path = self.migration_dir / "migration_costs_row_width.json"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.costs, f, ensure_ascii=False, indent=2)
        
        print(f"\nマイグレーションコスト保存完了: {output_path}")
    
    def compare_with_other_methods(self):
        """他の手法との比較情報を出力"""
        # migration_costs_without_ex.json があれば比較
        without_ex_path = self.migration_dir / "migration_costs_without_ex.json"
        
        if not without_ex_path.exists():
            return
        
        print(f"\n--- 他手法との比較 ---")
        
        with open(without_ex_path, 'r', encoding='utf-8') as f:
            costs_without_ex = json.load(f)
        
        # サンプルノードで比較
        sample_nodes = list(self.costs.keys())[:5]
        
        for node_id in sample_nodes:
            if node_id not in costs_without_ex:
                continue
            
            print(f"\n{node_id}:")
            
            # "[]"プランのコストを比較
            if "[]" in self.costs[node_id] and "[]" in costs_without_ex[node_id]:
                row_width_cost = self.costs[node_id]["[]"]
                without_ex_cost = costs_without_ex[node_id]["[]"]
                
                print(f"  行数・幅ベース: {row_width_cost:.2f}")
                print(f"  差分計算ベース: {without_ex_cost:.2f}")
                
                if without_ex_cost > 0:
                    ratio = row_width_cost / without_ex_cost
                    print(f"  比率: {ratio:.2f}x")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="行数と幅を利用したマイグレーションコスト推定"
    )
    parser.add_argument(
        "--query-set",
        type=str,
        default="job_like",
        help="使用するクエリセットの名前 (デフォルト: job_like)"
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="他の手法との比較を表示"
    )
    
    args = parser.parse_args()
    
    # コスト計算実行
    calculator = RowWidthBasedCostCalculator(query_set=args.query_set)
    calculator.calculate_all_costs()
    
    # 比較表示（オプション）
    if args.compare:
        calculator.compare_with_other_methods()
