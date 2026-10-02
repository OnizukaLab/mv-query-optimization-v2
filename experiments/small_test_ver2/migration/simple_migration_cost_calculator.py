# シンプルな2パターンのみのマイグレーションコスト計算

# python experiments/small_test_ver2/migration/simple_migration_cost_calculator.py --query-set job

import json
import psycopg2
import yaml
import sys
import os
import re
from pathlib import Path
from typing import Dict, Any, Optional

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings

class SimpleMigrationCostCalculator:
    """シンプルなマイグレーションプラン（2パターンのみ）のコストを計算するクラス
        
        simple_migration_plans.jsonから各SQLを読み込み、EXPLAINでtotalcostを取得。
        2パターン: 1) NON_MIGRATE (マイグレーション無し), 2) [] (依存MV無し)
    """

    def __init__(self, settings: Settings, query_set: str = "job_like"):
        """
        Args:
            settings: config.yamlから読み込んだSettings
            query_set: クエリセット名
        """
        self.settings = settings
        self.query_set = query_set
        
        # JSONファイルのパス設定
        self.json_file_path = Path(__file__).parent.parent / "04_migration" / query_set / "simple_migration_plans.json"
        
        # 出力ディレクトリのパス
        self.output_dir = self.json_file_path.parent
        
        self.plans = self._load_plans()
        self.costs = {}

    def _load_plans(self) -> Dict[str, Any]:
        with open(self.json_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
        
    def _get_connection(self):
        """データベース接続を取得（config.yamlの設定を使用）"""
        return psycopg2.connect(
            host=self.settings.database.host,
            port=self.settings.database.port,
            dbname=self.settings.database.database,
            user=self.settings.database.user,
            password=self.settings.database.password
        )
    

    def _explain_sql(self, cursor, sql: str) -> tuple[float, int, int]:
        """SQLをEXPLAINし、totalcost、rows、widthを取得
        
        Args:
            cursor: データベースカーソル（接続の使い回し用）
            sql: 実行するSQL
            
        Returns:
            (totalcost, plan_rows, plan_width) のタプル、エラー時は(0.0, 0, 0)
        """
        if not sql or sql.strip() == "" or not isinstance(sql, str):
            return (0.0, 0, 0)
        
        # "NON_MIGRATE" は実際のSQLではないので0を返す
        if sql == "NON_MIGRATE":
            return (0.0, 0, 0)
        
        # CREATE MATERIALIZED VIEWの場合、正規表現でSELECT部分を抽出
        # re.DOTALLで改行も含めてマッチ
        match = re.search(r'CREATE\s+MATERIALIZED\s+VIEW\s+\S+\s+AS\s+(.*)', sql, re.IGNORECASE | re.DOTALL)
        if match:
            sql = match.group(1).strip()
        else:
            # "AS" が見つからない場合はエラー
            print(f"  CREATE文のパースエラー: {sql[:80]}...")
            return (0.0, 0, 0)
        
        try:
            # EXPLAIN を実行
            explain_query = f"EXPLAIN (FORMAT JSON) {sql}"
            cursor.execute(explain_query)
            result = cursor.fetchone()

            if result and result[0]:
                # JSON形式の結果からtotal_cost、plan_rows、plan_widthを取得
                plan = result[0][0]  # 最初のプラン
                plan_data = plan.get('Plan', {})
                total_cost = float(plan_data.get('Total Cost', 0.0))
                plan_rows = int(plan_data.get('Plan Rows', 0))
                plan_width = int(plan_data.get('Plan Width', 0))
                return (total_cost, plan_rows, plan_width)
            else:
                return (0.0, 0, 0)
        except Exception as e:
            print(f"  エラー: EXPLAINの実行失敗 - {e}")
            print(f"  SQL: {sql[:100]}...")
            return (0.0, 0, 0)
        

    def calculate_all_costs(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """すべてのマイグレーションプラン（2パターンのみ）のコストを計算
        
        Returns:
            ノード名 -> {プランキー: {cost, utility, rows, width, size}} の辞書
            - cost: 作成コスト（読み取り + 書き込み）
            - utility: 利得（EXPLAINのTotal Cost = 読み取りコストのみ）
        """
        print("\n" + "="*70)
        print("マイグレーションコストを計算中（書き込みコスト含む）...")
        print("="*70)
        
        total_nodes = len(self.plans)
        processed = 0
        
        # データベース接続を1回だけ開く（全EXPLAIN実行で使い回し）
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # Phase 1と同じ設定を適用（推定精度向上）
                    cursor.execute("SET enable_bitmapscan = off;")
                    cursor.execute("SET default_statistics_target = 1000;")
                    cursor.execute("SET random_page_cost = 1.1;")
                    
                    # simple_migration_plans.jsonから読み込んだ順序を保持（leaf → non_leaf, ID昇順）
                    for node, plans in self.plans.items():
                        processed += 1
                        if processed % 10 == 0 or processed == total_nodes:
                            print(f"  進捗: {processed}/{total_nodes} ({processed*100//total_nodes}%)")
                        
                        self.costs[node] = {}
                        
                        # 2パターンのみ処理（順番を保証するためソート）
                        for plan_key in sorted(plans.keys()):
                            sql = plans[plan_key]
                            
                            if plan_key == "[]":
                                # 依存MV無しでマイグレーション
                                total_cost, rows, width = self._explain_sql(cursor, sql)
                                size = rows * width
                                
                                # 書き込みコストを計算
                                # ページ書き込みコスト = (サイズ / ページサイズ) * SEQ_PAGE_COST
                                # タプル処理コスト = 行数 * CPU_TUPLE_COST
                                write_pages = (size // 8192) + 1 if size > 0 else 0
                                write_cost = (write_pages * 1.0) + (rows * 0.01)
                                
                                # 作成コスト = 読み取りコスト + 書き込みコスト
                                creation_cost = total_cost + write_cost
                                
                                self.costs[node][plan_key] = {
                                    "cost": creation_cost,      # 作成コスト（読み取り + 書き込み）
                                    "utility": total_cost,      # 利得（EXPLAINコスト = 読み取りのみ）
                                    "rows": rows,
                                    "width": width,
                                    "size": size
                                }
                            else:
                                # NON_MIGRATE パターン (str([target_mv])の形式)
                                # SQLは "NON_MIGRATE" 文字列なので、コストとサイズは0
                                self.costs[node][plan_key] = {
                                    "cost": 0.0,
                                    "utility": 0.0,
                                    "rows": 0,
                                    "width": 0,
                                    "size": 0
                                }

            print(f"\n✓ 計算完了: {len(self.costs)}個のノード")
            print("="*70 + "\n")
            
        except Exception as e:
            print(f"\nエラー: データベース接続に失敗しました - {e}")
            raise
        
        # コストをJSONファイルに保存
        self.save_costs()
        
        return self.costs
    
    def save_costs(self, output_file: str = "simple_migration_costs.json"):
        """計算したコストをJSONファイルに保存"""
        try:
            output_path = self.output_dir / output_file
            with open(output_path, 'w', encoding='utf-8') as f:
                # 読み込み順序を保持（sort_keysを使わない）
                json.dump(self.costs, f, indent=2, ensure_ascii=False)
            print(f"マイグレーションコストを保存しました: {output_path}")
        except Exception as e:
            print(f"JSONファイルの保存に失敗しました: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="シンプルマイグレーションプラン（2パターン）のコスト計算")
    parser.add_argument(
        "--query-set",
        type = str,
        default = "job_like",
        help = "使用するクエリセットの名前 (デフォルト: job_like)"
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
    
    # コスト計算クラスのインスタンス化
    calculator = SimpleMigrationCostCalculator(settings, query_set=args.query_set)
    
    # シンプルなマイグレーションプランでは既存MVを使わないため、
    # MV作成とANALYZEは不要。直接コスト計算を実行。
    print("\n【シンプルマイグレーションコスト計算】")
    print("  - NON_MIGRATE: コスト = 0")
    print("  - []: 依存MV無しでEXPLAIN実行")
    costs = calculator.calculate_all_costs()
    
    print("\n✓ 処理完了")
