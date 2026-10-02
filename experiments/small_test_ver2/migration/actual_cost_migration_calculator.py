#!/usr/bin/env python3
"""
実測値ベースのマイグレーションコスト計算

parse_actual_costs.pyで生成されたpickleファイルから実測値を読み込み、
simple_migration_costs.jsonを生成します。

使い方:
    python experiments/small_test_ver2/migration/actual_cost_migration_calculator.py --query-set job_real
"""

import json
import pickle
import sys
from pathlib import Path
from typing import Dict, Any

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings


class ActualCostMigrationCalculator:
    """実測値からマイグレーションコストを生成するクラス
    
    job_real用の特別な処理を行います。pickleファイルから実測値を読み込み、
    simple_migration_plans.jsonの各ノードに対してコストを設定します。
    """

    def __init__(self, settings: Settings, query_set: str = "job_real"):
        """
        Args:
            settings: config.yamlから読み込んだSettings
            query_set: クエリセット名（通常は "job_real"）
        """
        self.settings = settings
        self.query_set = query_set
        
        # 実験ディレクトリ
        self.exp_dir = Path(__file__).parent.parent
        
        # pickleファイルのパス
        self.pickle_path = self.exp_dir / "03_parsed" / query_set / "qp_class.pkl"
        
        # マイグレーションプランファイルのパス
        self.plans_file = self.exp_dir / "04_migration" / query_set / "simple_migration_plans.json"
        
        # 出力ディレクトリのパス
        self.output_dir = self.plans_file.parent
        
        self.qp = None
        self.migration_plans = None
        self.costs = {}

    def _load_pickle(self) -> bool:
        """pickleファイルを読み込み"""
        if not self.pickle_path.exists():
            print(f"エラー: pickleファイルが見つかりません: {self.pickle_path}")
            print("先にparse_actual_costs.pyを実行してください")
            return False
        
        try:
            with open(self.pickle_path, 'rb') as f:
                self.qp = pickle.load(f)
            print(f"✓ pickleファイル読み込み完了: {self.qp.s_num}ノード")
            return True
        except Exception as e:
            print(f"エラー: pickleファイルの読み込みに失敗: {e}")
            return False

    def _load_migration_plans(self) -> bool:
        """マイグレーションプランを読み込み"""
        if not self.plans_file.exists():
            print(f"エラー: マイグレーションプランが見つかりません: {self.plans_file}")
            print("先にフェーズ4を実行してください")
            return False
        
        try:
            with open(self.plans_file, 'r', encoding='utf-8') as f:
                self.migration_plans = json.load(f)
            print(f"✓ マイグレーションプラン読み込み完了: {len(self.migration_plans)}個のノード")
            return True
        except Exception as e:
            print(f"エラー: マイグレーションプランの読み込みに失敗: {e}")
            return False

    def calculate_all_costs(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """実測値からマイグレーションコストを計算
        
        Returns:
            ノード名 -> {プランキー: {cost, utility, rows, width, size}} の辞書
            - cost: 作成コスト（実測値と同じ）
            - utility: 利得（実測値と同じ）
        """
        print("\n" + "="*70)
        print("実測値からマイグレーションコストを生成中...")
        print("="*70)
        
        # pickleファイルを読み込み
        if not self._load_pickle():
            return {}
        
        # マイグレーションプランを読み込み
        if not self._load_migration_plans():
            return {}
        
        print(f"✓ 実測値の取得準備完了")
        print(f"  - subquery_costs: {len(self.qp.qm.subquery_costs)}個")
        print(f"  - subquery_sizes: {len(self.qp.qm.subquery_sizes)}個")
        
        # 各ノードのコストを生成
        processed = 0
        total = len(self.migration_plans)
        
        for node_id, plans in self.migration_plans.items():
            processed += 1
            if processed % 100 == 0 or processed == total:
                print(f"  進捗: {processed}/{total} ({processed*100//total}%)")
            
            self.costs[node_id] = {}
            
            # 実測値を取得
            cost_val = self.qp.qm.subquery_costs.get(node_id, 0.0)
            size_val = self.qp.qm.subquery_sizes.get(node_id, 0)
            
            # rows と width を取得
            # non-leaf nodeの場合はnon_leaf_nodes_infoから取得
            if node_id in self.qp.qm.non_leaf_nodes_info:
                info = self.qp.qm.non_leaf_nodes_info[node_id]
                rows_val = int(info.rows)
                width_val = int(info.width)
            # leaf nodeの場合はデフォルト値を使用（sizeから逆算も可能だが、簡略化のため）
            else:
                # sizeを使って推定（width=1と仮定）
                rows_val = int(size_val) if size_val > 0 else 0
                width_val = 1
            
            # 2パターンのプランに対してコストを設定
            for plan_key in plans.keys():
                if plan_key == "[]":
                    # 依存MV無しで新規作成: 実測値を使用
                    # cost（作成コスト）とutility（利得）は同じ値
                    self.costs[node_id][plan_key] = {
                        "cost": float(cost_val),
                        "utility": float(cost_val),
                        "rows": int(rows_val),
                        "width": int(width_val),
                        "size": int(size_val)
                    }
                else:
                    # NON_MIGRATE: コストは0
                    self.costs[node_id][plan_key] = {
                        "cost": 0.0,
                        "utility": 0.0,
                        "rows": 0,
                        "width": 0,
                        "size": 0
                    }
        
        print(f"\n✓ 計算完了: {len(self.costs)}個のノード")
        print("="*70 + "\n")
        
        # コストをJSONファイルに保存
        self.save_costs()
        
        return self.costs
    
    def save_costs(self, output_file: str = "simple_migration_costs.json"):
        """計算したコストをJSONファイルに保存"""
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            output_path = self.output_dir / output_file
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.costs, f, indent=2, ensure_ascii=False)
            print(f"✓ マイグレーションコストを保存しました: {output_path}")
        except Exception as e:
            print(f"エラー: JSONファイルの保存に失敗しました: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="実測値ベースのマイグレーションコスト計算")
    parser.add_argument(
        "--query-set",
        type=str,
        default="job_real",
        help="使用するクエリセットの名前 (デフォルト: job_real)"
    )

    args = parser.parse_args()

    # Settingsを読み込み
    settings = Settings()
    
    # コスト計算クラスのインスタンス化
    calculator = ActualCostMigrationCalculator(settings, query_set=args.query_set)
    
    print("\n【実測値ベースのマイグレーションコスト計算】")
    print("  - pickleファイルから実測値を読み込み")
    print("  - cost と utility は同じ値を使用")
    costs = calculator.calculate_all_costs()
    
    if costs:
        print("\n✓ 処理完了")
    else:
        print("\n✗ 処理失敗")
        sys.exit(1)
