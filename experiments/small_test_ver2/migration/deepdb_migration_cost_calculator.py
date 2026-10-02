# DeepDB を使用したマイグレーションコスト計算
#
# DeepDB のカーディナリティ推定を使って MV サイズを推定するコスト計算クラス
#
# Usage:
#   python experiments/small_test_ver2/migration/deepdb_migration_cost_calculator.py --query-set job

import json
import psycopg2
import yaml
import sys
import re
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from experiments.small_test_ver2.migration.deepdb_estimator import DeepDBEstimator

logger = logging.getLogger(__name__)


class DeepDBMigrationCostCalculator:
    """DeepDB を使用したマイグレーションコスト計算クラス
    
    DeepDB の SPN アンサンブルを使ってカーディナリティを推定し、
    PostgreSQL の EXPLAIN から幅を取得してサイズを計算します。
    
    SimpleMigrationCostCalculator と同じインターフェースを提供しますが、
    行数推定に DeepDB を使用します。
    
    Attributes:
        settings: config.yaml の Settings オブジェクト
        query_set: クエリセット名
        deepdb: DeepDBEstimator インスタンス
    """
    
    # デフォルトのパス設定（相対パス: migration/ から deepdb_full/deepdb/ へ）
    DEFAULT_ENSEMBLE_PATH = "../../../deepdb_full/deepdb/run/imdb-all-job/spn_ensembles/ensemble_join_3_budget_5_10000000.pkl"
    DEFAULT_CSV_PATH = "../../../deepdb_full/deepdb/csv/{}.csv"
    
    def __init__(
        self, 
        settings: Settings, 
        query_set: str = "job_like",
        ensemble_path: Optional[str] = None,
        csv_path: Optional[str] = None
    ):
        """
        Args:
            settings: config.yaml から読み込んだ Settings
            query_set: クエリセット名
            ensemble_path: アンサンブルファイルのパス（Noneの場合はデフォルト）
            csv_path: CSV ファイルのパステンプレート（Noneの場合はデフォルト）
        """
        self.settings = settings
        self.query_set = query_set
        
        # JSONファイルのパス設定
        self.base_dir = Path(__file__).parent.parent
        self.json_file_path = self.base_dir / "04_migration" / query_set / "simple_migration_plans.json"
        self.output_dir = self.json_file_path.parent
        
        # DeepDB のパス解決
        self.ensemble_path = self._resolve_path(ensemble_path or self.DEFAULT_ENSEMBLE_PATH)
        self.csv_path = self._resolve_path(csv_path or self.DEFAULT_CSV_PATH)
        
        # DeepDB Estimator の初期化（遅延ロード）
        self._deepdb = None
        
        # データベース接続（遅延ロード、再利用）
        self._conn = None
        
        # プランとコスト
        self.plans = self._load_plans()
        self.costs = {}
        
        # 統計情報
        self.stats = {
            "total_queries": 0,
            "deepdb_success": 0,
            "deepdb_fallback": 0,
            "explain_errors": 0
        }
    
    def _resolve_path(self, path: str) -> str:
        """相対パスを絶対パスに解決"""
        p = Path(path)
        if not p.is_absolute():
            p = Path(__file__).parent / path
        return str(p.resolve())
    
    @property
    def deepdb(self) -> DeepDBEstimator:
        """DeepDB Estimator を取得（遅延ロード）"""
        if self._deepdb is None:
            logger.info(f"Loading DeepDB estimator from {self.ensemble_path}")
            self._deepdb = DeepDBEstimator(self.ensemble_path, self.csv_path)
        return self._deepdb
    
    def _load_plans(self) -> Dict[str, Any]:
        """マイグレーションプランを読み込み"""
        with open(self.json_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _get_connection(self):
        """データベース接続を作成（内部用）"""
        return psycopg2.connect(
            host=self.settings.database.host,
            port=self.settings.database.port,
            dbname=self.settings.database.database,
            user=self.settings.database.user,
            password=self.settings.database.password
        )
    
    @property
    def connection(self):
        """データベース接続を取得（キャッシュ、再利用）"""
        if self._conn is None or self._conn.closed:
            self._conn = self._get_connection()
        return self._conn
    
    def close(self):
        """データベース接続を閉じる"""
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
            self._conn = None
    
    def _extract_select_sql(self, sql: str) -> Optional[str]:
        """CREATE MATERIALIZED VIEW から SELECT 部分を抽出"""
        if not sql or sql.strip() == "" or not isinstance(sql, str):
            return None
        
        if sql == "NON_MIGRATE":
            return None
        
        match = re.search(
            r'CREATE\s+MATERIALIZED\s+VIEW\s+\S+\s+AS\s+(.*)', 
            sql, 
            re.IGNORECASE | re.DOTALL
        )
        if match:
            return match.group(1).strip()
        
        return None
    
    def _get_explain_info(self, sql: str) -> Tuple[int, int, float]:
        """PostgreSQL EXPLAIN から rows, width, cost を取得
        
        Args:
            sql: SELECT 文
            
        Returns:
            (rows, width, cost) のタプル
        """
        try:
            with self.connection.cursor() as cursor:
                explain_query = f"EXPLAIN (FORMAT JSON) {sql}"
                cursor.execute(explain_query)
                result = cursor.fetchone()
                
                if result and result[0]:
                    plan = result[0][0]
                    plan_data = plan.get('Plan', {})
                    rows = int(plan_data.get('Plan Rows', 0))
                    width = int(plan_data.get('Plan Width', 0))
                    cost = float(plan_data.get('Total Cost', 0.0))
                    return (rows, width, cost)
                return (0, 0, 0.0)
        except Exception as e:
            logger.warning(f"EXPLAIN error: {e}")
            self.stats["explain_errors"] += 1
            return (0, 0, 0.0)
    
    def _estimate_size(self, sql: str) -> Dict[str, Any]:
        """MV の SELECT SQL からサイズを推定
        
        1回の EXPLAIN で rows, width, cost を取得。
        DeepDB が成功した場合は rows のみ DeepDB の値を使用。
        
        Args:
            sql: SELECT 文
            
        Returns:
            {rows, width, size, cost, source} の辞書
        """
        self.stats["total_queries"] += 1
        
        # PostgreSQL EXPLAIN で rows, width, cost を1回で取得
        pg_rows, width, cost = self._get_explain_info(sql)
        
        # DeepDB でカーディナリティを推定
        try:
            rows = self.deepdb.estimate_cardinality(sql)
            source = "deepdb"
            self.stats["deepdb_success"] += 1
        except Exception as e:
            logger.warning(f"DeepDB estimation failed, falling back to PostgreSQL: {e}")
            rows = pg_rows
            source = "postgresql"
            self.stats["deepdb_fallback"] += 1
        
        # サイズ計算
        size = rows * width
        
        return {
            "rows": rows,
            "width": width,
            "size": size,
            "cost": cost,
            "source": source
        }
    
    def calculate_all_costs(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """すべてのマイグレーションプランのコストを計算
        
        Returns:
            ノード名 -> {プランキー: {cost, rows, width, size, source}} の辞書
        """
        print("\n" + "="*70)
        print("DeepDB マイグレーションコストを計算中...")
        print("="*70)
        
        total_nodes = len(self.plans)
        processed = 0
        
        for node, plans in self.plans.items():
            processed += 1
            if processed % 10 == 0 or processed == total_nodes:
                print(f"  進捗: {processed}/{total_nodes} ({processed*100//total_nodes}%)")
            
            self.costs[node] = {}
            
            for plan_key in sorted(plans.keys()):
                sql = plans[plan_key]
                
                if plan_key == "[]":
                    # 依存MV無しでマイグレーション
                    select_sql = self._extract_select_sql(sql)
                    if select_sql:
                        result = self._estimate_size(select_sql)
                        self.costs[node][plan_key] = {
                            "cost": result["cost"],
                            "rows": result["rows"],
                            "width": result["width"],
                            "size": result["size"],
                            "source": result["source"]
                        }
                    else:
                        self.costs[node][plan_key] = {
                            "cost": 0.0,
                            "rows": 0,
                            "width": 0,
                            "size": 0,
                            "source": "error"
                        }
                # NON_MIGRATE パターンはスキップ（出力しない）
        
        print(f"\n✓ 計算完了: {len(self.costs)}個のノード")
        self._print_stats()
        print("="*70 + "\n")
        
        # コストを保存
        self.save_costs()
        
        # データベース接続を閉じる
        self.close()
        
        return self.costs
    
    def _print_stats(self):
        """統計情報を表示"""
        print(f"\n統計情報:")
        print(f"  総クエリ数: {self.stats['total_queries']}")
        print(f"  DeepDB 成功: {self.stats['deepdb_success']}")
        print(f"  PostgreSQL フォールバック: {self.stats['deepdb_fallback']}")
        print(f"  EXPLAIN エラー: {self.stats['explain_errors']}")
    
    def save_costs(self, output_file: str = "simple_migration_costs.json"):
        """計算したコストを JSON ファイルに保存"""
        try:
            output_path = self.output_dir / output_file
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.costs, f, indent=2, ensure_ascii=False)
            print(f"マイグレーションコストを保存しました: {output_path}")
        except Exception as e:
            print(f"JSON ファイルの保存に失敗しました: {e}")
    
    def compare_with_postgresql(self) -> Dict[str, Any]:
        """PostgreSQL 推定と DeepDB 推定を比較
        
        Returns:
            比較結果の辞書
        """
        print("\n" + "="*70)
        print("PostgreSQL vs DeepDB 推定値の比較")
        print("="*70)
        
        comparisons = []
        
        for node, plans in self.plans.items():
            for plan_key, sql in plans.items():
                if plan_key != "[]":
                    continue
                    
                select_sql = self._extract_select_sql(sql)
                if not select_sql:
                    continue
                
                # PostgreSQL 推定
                pg_rows, pg_width, _ = self._get_explain_info(select_sql)
                
                # DeepDB 推定
                try:
                    deepdb_rows = self.deepdb.estimate_cardinality(select_sql)
                    deepdb_width = pg_width  # 幅は共通
                except Exception as e:
                    deepdb_rows = 0
                    deepdb_width = pg_width
                
                # 差分計算
                if pg_rows > 0:
                    ratio = deepdb_rows / pg_rows
                else:
                    ratio = 0.0
                
                comparisons.append({
                    "node": node,
                    "pg_rows": pg_rows,
                    "deepdb_rows": deepdb_rows,
                    "ratio": ratio,
                    "pg_size": pg_rows * pg_width,
                    "deepdb_size": deepdb_rows * deepdb_width
                })
        
        # 統計
        if comparisons:
            ratios = [c["ratio"] for c in comparisons if c["ratio"] > 0]
            if ratios:
                avg_ratio = sum(ratios) / len(ratios)
                max_ratio = max(ratios)
                min_ratio = min(ratios)
                
                print(f"\n比較統計:")
                print(f"  比較ノード数: {len(comparisons)}")
                print(f"  平均比率 (DeepDB/PG): {avg_ratio:.4f}")
                print(f"  最大比率: {max_ratio:.4f}")
                print(f"  最小比率: {min_ratio:.4f}")
        
        return {
            "comparisons": comparisons,
            "avg_ratio": avg_ratio if ratios else 0.0
        }


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="DeepDB マイグレーションコスト計算")
    parser.add_argument(
        "--query-set",
        type=str,
        default="job_like",
        help="使用するクエリセットの名前 (デフォルト: job_like)"
    )
    parser.add_argument(
        "--ensemble-path",
        type=str,
        default=None,
        help="アンサンブルファイルのパス"
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="PostgreSQL と DeepDB の推定値を比較"
    )
    
    args = parser.parse_args()
    
    # ロギング設定
    logging.basicConfig(level=logging.INFO)
    
    # config.yaml から設定を読み込み
    config_path = Path(__file__).parent.parent / "config.yaml"
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config_data = yaml.safe_load(f)
    
    temp_config = config_path.parent / '.temp_config.yaml'
    with open(temp_config, 'w', encoding='utf-8') as f:
        yaml.dump(config_data, f, allow_unicode=True)
    
    try:
        settings = Settings.from_yaml(str(temp_config))
    finally:
        if temp_config.exists():
            temp_config.unlink()
    
    # コスト計算
    calculator = DeepDBMigrationCostCalculator(
        settings, 
        query_set=args.query_set,
        ensemble_path=args.ensemble_path
    )
    
    print("\n【DeepDB マイグレーションコスト計算】")
    print(f"  - アンサンブル: {calculator.ensemble_path}")
    print(f"  - クエリセット: {args.query_set}")
    
    if args.compare:
        calculator.compare_with_postgresql()
    else:
        costs = calculator.calculate_all_costs()
    
    print("\n✓ 処理完了")
