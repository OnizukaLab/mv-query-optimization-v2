#!/usr/bin/env python3
"""
マイグレーションプランのコストを計算（EXPLAIN使用版・MV作成なし）

使い方:
    python experiments/small_test_ver2/migration/migration_cost_with_limited_ex.py --query-set job_like
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


class MigrationCostCalculatorWithExplain:
    """EXPLAIN（MV作成なし）を使ったマイグレーションコスト計算"""
    
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
        self.node_costs = {}  # {node_id: cost}
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
            return pickle.load(f)
    
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
        print(f"EXPLAIN実行中（クエリセット: {self.query_set}）...")
        
        base_costs = {}
        
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                for node_id, plans in self.plans.items():
                    # []プランのSQLを取得
                    base_plan_sql = plans.get("[]")
                    
                    if not base_plan_sql or not base_plan_sql.startswith("CREATE MATERIALIZED VIEW"):
                        continue
                    
                    # CREATE MATERIALIZED VIEW部分を除去してSELECT文のみに
                    # 例: "CREATE MATERIALIZED VIEW leaf_1 AS\nSELECT ..." -> "SELECT ..."
                    select_sql = self._extract_select_from_create_mv(base_plan_sql)
                    
                    # EXPLAINを実行（Bitmap Scanを無効化）
                    try:
                        cur.execute("SET enable_bitmapscan = off")
                        cur.execute(f"EXPLAIN (FORMAT JSON) {select_sql}")
                        explain_result = cur.fetchone()[0]
                        
                        # Total Costを抽出
                        total_cost = explain_result[0]["Plan"]["Total Cost"]
                        base_costs[node_id] = total_cost
                        
                        print(f"  {node_id}: {total_cost:.2f}")
                    
                    except Exception as e:
                        print(f"  {node_id}: エラー - {e}")
                        base_costs[node_id] = 0.0
                        # トランザクションをロールバックして aborted 状態を解除
                        conn.rollback()
        
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
        """すべてのマイグレーションコストを計算"""
        print(f"\nマイグレーションコスト計算中...")
        
        for node_id, plans in self.plans.items():
            self.costs[node_id] = {}
            
            for plan_key, plan in plans.items():
                # 同じノードを再利用する場合
                if not plan.startswith("CREATE MATERIALIZED VIEW"):
                    self.costs[node_id][plan_key] = 0.0
                    continue
                
                # []プランの場合: ベースコスト
                if plan_key == "[]":
                    self.costs[node_id][plan_key] = self.node_costs.get(node_id, 0.0)
                
                # 依存MVありの場合: ターゲットコスト - 依存コストの合計
                else:
                    dependencies = eval(plan_key)
                    target_cost = self.node_costs.get(node_id, 0.0)
                    dependency_cost = sum(self.node_costs.get(dep, 0.0) for dep in dependencies)
                    self.costs[node_id][plan_key] = target_cost - dependency_cost
        
        self._save_costs()
        print(f"完了: {len(self.costs)} ノード処理済み")
        return self.costs
    
    def _save_costs(self):
        """コスト情報をJSONファイルに保存"""
        output_path = self.migration_dir / "migration_costs_with_ex.json"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.costs, f, indent=2, ensure_ascii=False)
        
        print(f"保存完了: {output_path}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="マイグレーションプランのコスト計算（EXPLAIN使用）")
    parser.add_argument(
        "--query-set",
        type=str,
        default="job_like",
        help="使用するクエリセットの名前 (デフォルト: job_like)"
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
    calculator = MigrationCostCalculatorWithExplain(
        settings=settings,
        query_set=args.query_set
    )
    
    # ステップ1: []プランに対してEXPLAIN実行
    calculator.extract_base_costs_with_explain()
    
    # ステップ2: すべてのプランのコストを計算
    calculator.calculate_all_costs()