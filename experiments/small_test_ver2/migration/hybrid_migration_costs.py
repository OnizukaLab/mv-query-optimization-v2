"""
ハイブリッド・マイグレーションコスト計算スクリプト

PostgreSQLのコストモデルをシミュレーションして、MVスキャンコストを理論的に推定します。
統計情報（rows, width）から物理ページ数とCPUコストを算出し、
差分置換法（元コスト - 依存コスト + MVスキャンコスト）で最終コストを計算します。

使い方:
    python experiments/small_test_ver2/migration/hybrid_migration_costs.py --query-set job_like
    python experiments/small_test_ver2/migration/hybrid_migration_costs.py --query-set job --use-seq-scan
"""

import argparse
import json
import math
import pickle
import sys
from pathlib import Path
from typing import Dict

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))


class HybridMigrationCostCalculator:
    """ハイブリッド方式でのマイグレーションコスト計算"""
    
    # PostgreSQL標準パラメータ
    SEQ_PAGE_COST = 1.0
    RANDOM_PAGE_COST = 4.0
    CPU_TUPLE_COST = 0.01
    CPU_INDEX_TUPLE_COST = 0.005
    BLOCK_SIZE = 8192
    TUPLE_OVERHEAD = 24
    
    def __init__(self, query_set: str = "job_like", use_seq_scan: bool = False):
        """
        Args:
            query_set: クエリセット名
            use_seq_scan: True=Seq Scan, False=Index Scan（デフォルト）
        """
        self.query_set = query_set
        self.use_seq_scan = use_seq_scan
        
        # パス設定
        base_dir = Path(__file__).parent.parent
        self.migration_dir = base_dir / "04_migration" / query_set
        self.pickle_path = base_dir / "03_parsed" / query_set / "qp_class.pkl"

        # データロード
        self.qp = self._load_qp()
        self.plans = self._load_migration_plans()
        self.costs = {}
    
    def _load_qp(self):
        """QueryParserをpickleファイルからロード"""
        if not self.pickle_path.exists():
            raise FileNotFoundError(f"qp_class.pkl not found: {self.pickle_path}")
        
        print(f"✓ QueryParserをロード: {self.pickle_path}")
        with open(self.pickle_path, 'rb') as f:
            return pickle.load(f)
        
    def _load_migration_plans(self) -> Dict[str, Dict[str, str]]:
        """マイグレーションプランをJSONファイルからロード"""
        plans_path = self.migration_dir / "migration_plans.json"
        
        if not plans_path.exists():
            raise FileNotFoundError(f"migration_plans.json not found: {plans_path}")
        
        print(f"✓ マイグレーションプランをロード: {plans_path}")
        with open(plans_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def calculate_mv_scan_cost(self, node_id: str, use_index: bool = True) -> float:
        """
        統計情報からMVのスキャンコストを理論的に推定する
        
        Args:
            node_id: 対象のノードID
            use_index: True=Index Scan(高速), False=Seq Scan(低速)として計算
        
        Returns:
            推定されたスキャンコスト
        """
        # 1. QueryManagerから統計情報を取得
        qm = self.qp.qm
        if not hasattr(qm, 'subquery_sizes') or node_id not in qm.subquery_sizes:
            return 0.0

        size = qm.subquery_sizes.get(node_id, 0)
        width = qm.subquery_widths.get(node_id, 100)  # デフォルト100
        if width == 0:
            width = 1
        
        rows = size / width
        if rows <= 0:
            return 0.0

        # 2. ページ数（I/O量）の推定
        row_size = width + self.TUPLE_OVERHEAD
        tuples_per_page = self.BLOCK_SIZE // row_size
        if tuples_per_page < 1:
            tuples_per_page = 1
        
        pages = math.ceil(rows / tuples_per_page)

        # 3. コスト計算
        if not use_index:
            # Seq Scan: 全ページI/O + 全行CPU
            io_cost = pages * self.SEQ_PAGE_COST
            cpu_cost = rows * self.CPU_TUPLE_COST
            return io_cost + cpu_cost
        else:
            # Index Scan: ランダムアクセスI/O + 選択的CPU
            # 選択率(selectivity)を1%と仮定（平均的なフィルタ効果）
            selectivity = 0.01
            
            # インデックスの深さ + アクセスするリーフページ
            index_pages = math.ceil(math.log2(rows)) if rows > 1 else 1
            touched_pages = math.ceil(pages * selectivity)
            touched_rows = math.ceil(rows * selectivity)
            
            io_cost = (index_pages + touched_pages) * self.RANDOM_PAGE_COST
            cpu_cost = touched_rows * self.CPU_INDEX_TUPLE_COST
            
            return io_cost + cpu_cost
    
    def calculate_all_costs(self) -> Dict[str, Dict[str, float]]:
        """すべてのノードのマイグレーションコストを計算"""
        
        print("\n" + "="*70)
        print("ハイブリッド・コスト推定を実行中...")
        print(f"スキャンモード: {'Seq Scan' if self.use_seq_scan else 'Index Scan'}")
        print("="*70)
        
        qm = self.qp.qm
        
        # 統計情報の存在確認
        has_sizes = hasattr(qm, 'subquery_sizes')
        has_widths = hasattr(qm, 'subquery_widths')
        has_original_costs = hasattr(qm, 'original_subquery_costs')
        
        print(f"\n統計情報:")
        print(f"  - subquery_sizes: {'✓' if has_sizes else '✗'}")
        print(f"  - subquery_widths: {'✓' if has_widths else '✗'}")
        print(f"  - original_subquery_costs: {'✓' if has_original_costs else '✗'}")
        
        if not (has_sizes and has_widths and has_original_costs):
            print("\n警告: 必要な統計情報が不足しています")
        
        print(f"\n処理中: {len(self.plans)}ノード")
        
        for node_id, plans in self.plans.items():
            self.costs[node_id] = {}
            
            # ターゲットノードの「元のコスト」（MVなしのEXPLAIN値）
            target_original_cost = qm.original_subquery_costs.get(node_id, 0.0) if has_original_costs else 0.0

            for plan_key, plan in plans.items():
                # NON_MIGRATEや生成失敗の場合はコスト0
                if not plan.startswith("CREATE MATERIALIZED VIEW"):
                    self.costs[node_id][plan_key] = 0.0
                    continue
                
                # plan_keyをパース
                try:
                    if plan_key == "[]":
                        dependencies = []
                    else:
                        # Pythonのリスト表現をJSONに変換してパース
                        json_str = plan_key.replace("'", '"')
                        dependencies = json.loads(json_str)
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"  警告: {node_id} の plan_key '{plan_key}' のパースに失敗: {e}")
                    dependencies = []

                if not dependencies:
                    # Base Plan: 元のコストをそのまま使用
                    self.costs[node_id][plan_key] = target_original_cost
                    continue

                # 1. 依存ノードの「元のコスト」合計 (これらはMV化で不要になるので引く)
                dep_original_sum = sum(
                    qm.original_subquery_costs.get(dep, 0.0) if has_original_costs else 0.0
                    for dep in dependencies
                )

                # 2. 依存ノードの「MVスキャンコスト」合計 (これらが新たに発生するので足す)
                dep_scan_sum = sum(
                    self.calculate_mv_scan_cost(dep, use_index=not self.use_seq_scan)
                    for dep in dependencies
                )

                # 3. ハイブリッド計算: (ターゲット - 依存元) + 依存スキャン
                # 処理コストが負になる場合は0に補正（フィルタで行数が減りすぎた場合など）
                processing_cost = max(target_original_cost - dep_original_sum, 0.0)
                
                final_cost = processing_cost + dep_scan_sum
                
                self.costs[node_id][plan_key] = final_cost

        self._save_costs()
        self._print_statistics()
        
        print("\n" + "="*70)
        print(f"✓ 完了: {len(self.costs)}ノード処理済み")
        print("="*70 + "\n")
        
        return self.costs
    
    def _save_costs(self):
        """コスト情報をJSONファイルに保存"""
        scan_mode = "seq_scan" if self.use_seq_scan else "index_scan"
        output_path = self.migration_dir / f"hybrid_migration_costs_{scan_mode}.json"

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.costs, f, ensure_ascii=False, indent=2)

        print(f"\n✓ マイグレーションコスト保存完了: {output_path}")
    
    def _print_statistics(self):
        """コスト統計を表示"""
        all_costs = []
        for node_costs in self.costs.values():
            all_costs.extend(node_costs.values())
        
        if not all_costs:
            return
        
        print(f"\nコスト統計:")
        print(f"  - 総プラン数: {len(all_costs)}")
        print(f"  - 最小コスト: {min(all_costs):.2f}")
        print(f"  - 最大コスト: {max(all_costs):.2f}")
        print(f"  - 平均コスト: {sum(all_costs) / len(all_costs):.2f}")
        
        # ゼロコストのプラン数
        zero_costs = sum(1 for c in all_costs if c == 0.0)
        if zero_costs > 0:
            print(f"  - ゼロコストプラン: {zero_costs}個")


def main():
    parser = argparse.ArgumentParser(
        description="ハイブリッド方式でのマイグレーションコスト計算"
    )
    parser.add_argument(
        "--query-set",
        type=str,
        default="job_like",
        help="使用するクエリセットの名前 (デフォルト: job_like)"
    )
    parser.add_argument(
        "--use-seq-scan",
        action="store_true",
        help="Seq Scanモードで計算（デフォルトはIndex Scan）"
    )

    args = parser.parse_args()

    # コスト計算実行
    calculator = HybridMigrationCostCalculator(
        query_set=args.query_set,
        use_seq_scan=args.use_seq_scan
    )
    calculator.calculate_all_costs()


if __name__ == "__main__":
    main()
