"""
プラン構造解析とコスト置換法による安全なマイグレーションコスト推定

MVを一切作成せずに、EXPLAINのみでMV使用時のコストを高精度に推定します。
元のクエリプランの構造を解析し、MVに置き換わる部分のコストを理論値で置換します。

使い方:
    python experiments/small_test_ver2/migration/safe_migration_costs.py --query-set job_like
    python experiments/small_test_ver2/migration/safe_migration_costs.py --query-set job --use-seq-scan
"""

import argparse
import json
import math
import pickle
import psycopg2
import sys
from pathlib import Path
from typing import Dict, List, Set, Optional, Any

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings


class SafeMigrationCostEstimator:
    """プラン構造解析によるMVマイグレーションコスト推定"""
    
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
        self.json_dir = base_dir / "02_json" / query_set

        # データロード
        self.qp = self._load_qp()
        self.plans = self._load_migration_plans()
        self.costs = {}
        
        # 設定読み込み
        config_path = base_dir / "config.yaml"
        self.settings = Settings.from_yaml(str(config_path))
    
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
    
    def _get_connection(self):
        """データベース接続を取得"""
        return psycopg2.connect(
            host=self.settings.database.host,
            port=self.settings.database.port,
            dbname=self.settings.database.database,
            user=self.settings.database.user,
            password=self.settings.database.password
        )
    
    def _extract_select_from_create_mv(self, sql: str) -> str:
        """CREATE MATERIALIZED VIEW文からSELECT文を抽出"""
        import re
        if not sql or not isinstance(sql, str):
            return ""
        
        if sql in ["NON_MIGRATE", "CREATE MATERIALIZED VIEW (generation failed)"]:
            return ""
        
        match = re.search(r'CREATE\s+MATERIALIZED\s+VIEW\s+\S+\s*AS\s*(.*)', sql, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""
    
    def measure_mv_spec(self, mv_sql: str) -> tuple[float, float, float, Optional[Dict]]:
        """
        ステップ1: MVのスペック（行数・幅・ベースコスト・プラン）を測定
        
        Returns:
            (rows, width, base_cost, plan_tree): 行数、幅、元のコスト、プラン全体
        """
        select_sql = self._extract_select_from_create_mv(mv_sql)
        if not select_sql:
            return 0.0, 0.0, 0.0, None
        
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SET enable_bitmapscan = off")
                    explain_query = f"EXPLAIN (FORMAT JSON) {select_sql}"
                    cursor.execute(explain_query)
                    result = cursor.fetchone()
                    
                    if result and result[0]:
                        plan = result[0][0]['Plan']
                        rows = float(plan.get('Plan Rows', 0))
                        width = float(plan.get('Plan Width', 0))
                        base_cost = float(plan.get('Total Cost', 0))
                        return rows, width, base_cost, plan
        except Exception:
            pass
        
        return 0.0, 0.0, 0.0, None
    
    def calculate_theoretical_scan_cost(self, rows: float, width: float, use_index: bool = True) -> float:
        """
        ステップ2: MVの理論スキャンコストを計算
        
        Args:
            rows: 行数
            width: 行幅
            use_index: True=Index Scan, False=Seq Scan
        
        Returns:
            推定されたスキャンコスト
        """
        if rows <= 0 or width <= 0:
            return 0.0

        # ページ数（I/O量）の推定
        row_size = width + self.TUPLE_OVERHEAD
        tuples_per_page = self.BLOCK_SIZE // row_size
        if tuples_per_page < 1:
            tuples_per_page = 1
        
        pages = math.ceil(rows / tuples_per_page)

        if not use_index:
            # Seq Scan: 全ページI/O + 全行CPU
            io_cost = pages * self.SEQ_PAGE_COST
            cpu_cost = rows * self.CPU_TUPLE_COST
            return io_cost + cpu_cost
        else:
            # Index Scan: ランダムアクセスI/O + 選択的CPU
            selectivity = 0.01  # 選択率1%を仮定
            
            index_pages = math.ceil(math.log2(rows)) if rows > 1 else 1
            touched_pages = math.ceil(pages * selectivity)
            touched_rows = math.ceil(rows * selectivity)
            
            io_cost = (index_pages + touched_pages) * self.RANDOM_PAGE_COST
            cpu_cost = touched_rows * self.CPU_INDEX_TUPLE_COST
            
            return io_cost + cpu_cost
    
    def get_tables_in_plan_node(self, plan_node: Dict) -> Set[str]:
        """
        プランノード以下に含まれるテーブル名の集合を返す
        
        Args:
            plan_node: EXPLAINのJSONプランノード
        
        Returns:
            テーブル名の集合
        """
        tables = set()
        if "Relation Name" in plan_node:
            tables.add(plan_node["Relation Name"])
        
        if "Plans" in plan_node:
            for child in plan_node["Plans"]:
                tables.update(self.get_tables_in_plan_node(child))
        
        return tables
    
    def get_node_tables(self, node_id: str) -> Set[str]:
        """
        QueryManagerから指定ノードが参照するテーブル集合を取得
        
        Args:
            node_id: ノードID
        
        Returns:
            テーブル名の集合
        """
        qm = self.qp.qm
        
        # ノードがLeafの場合
        if node_id in qm.leaf_nodes:
            relation = qm.relation_tables.get(node_id, "")
            return {relation} if relation else set()
        
        # Non-Leafの場合: 子ノードのテーブルを再帰的に収集
        tables = set()
        children = qm.graph.get(node_id, [])
        
        for child_id in children:
            tables.update(self.get_node_tables(child_id))
        
        return tables
    
    def find_node_cost_by_tables(self, plan_root: Dict, target_tables: Set[str]) -> Optional[float]:
        """
        プランツリーから指定されたテーブル集合と完全一致するノードを探し、そのコストを返す
        
        Args:
            plan_root: EXPLAINのJSONプランルート
            target_tables: 探索対象のテーブル集合
        
        Returns:
            一致するノードのTotal Cost、見つからない場合はNone
        """
        if not plan_root or not target_tables:
            return None
        
        # 幅優先探索でノードを巡回
        queue = [plan_root]
        
        while queue:
            node = queue.pop(0)
            node_tables = self.get_tables_in_plan_node(node)
            
            # 完全一致チェック
            if node_tables == target_tables:
                return float(node.get("Total Cost", 0.0))
            
            # 子ノードを探索キューに追加
            if "Plans" in node:
                queue.extend(node["Plans"])
        
        return None
    
    def calculate_contextual_replaced_cost(self, target_plan_tree: Dict, dependency_ids: List[str]) -> float:
        """
        ターゲットプラン内で依存MVに対応するノードを探索し、そのコストの合計を計算
        
        Args:
            target_plan_tree: ターゲットMVのEXPLAINプラン（MVなし）
            dependency_ids: 依存MVのノードIDリスト
        
        Returns:
            依存MVに対応するノードのコスト合計
        """
        if not target_plan_tree or not dependency_ids:
            return 0.0
        
        qm = self.qp.qm
        has_original_costs = hasattr(qm, 'original_subquery_costs')
        total_replaced_cost = 0.0
        
        for dep_id in dependency_ids:
            # 依存MVのテーブル集合を取得
            dep_tables = self.get_node_tables(dep_id)
            
            if not dep_tables:
                # テーブル情報が取得できない場合はフォールバック
                fallback_cost = qm.original_subquery_costs.get(dep_id, 0.0) if has_original_costs else 0.0
                total_replaced_cost += fallback_cost
                continue
            
            # プラン内でテーブル集合が一致するノードを探索
            cost = self.find_node_cost_by_tables(target_plan_tree, dep_tables)
            
            if cost is not None:
                # 一致するノードが見つかった場合
                total_replaced_cost += cost
            else:
                # 見つからない場合はoriginal_subquery_costsで代替
                fallback_cost = qm.original_subquery_costs.get(dep_id, 0.0) if has_original_costs else 0.0
                total_replaced_cost += fallback_cost
        
        return total_replaced_cost
    
    def calculate_all_costs(self) -> Dict[str, Dict[str, float]]:
        """すべてのノードのマイグレーションコストを計算"""
        qm = self.qp.qm
        has_original_costs = hasattr(qm, 'original_subquery_costs')
        
        for node_id, plans in self.plans.items():
            self.costs[node_id] = {}

            for plan_key, plan_sql in plans.items():
                # NON_MIGRATEや生成失敗の場合はコスト0
                if not plan_sql.startswith("CREATE MATERIALIZED VIEW"):
                    self.costs[node_id][plan_key] = 0.0
                    continue
                
                # plan_keyをパース
                try:
                    if plan_key == "[]":
                        dependencies = []
                    else:
                        json_str = plan_key.replace("'", '"')
                        dependencies = json.loads(json_str)
                except (json.JSONDecodeError, ValueError):
                    dependencies = []

                # ステップ1: ターゲットMVのプラン測定（MVを使わない場合のプラン）
                target_rows, target_width, target_total_cost, target_plan_tree = self.measure_mv_spec(plan_sql)
                
                if target_total_cost == 0.0 or not target_plan_tree:
                    # 測定失敗時はスキップ（コスト0）
                    self.costs[node_id][plan_key] = 0.0
                    continue
                
                if not dependencies:
                    # ベースプラン（依存なし）: 測定した全体コストをそのまま使用
                    self.costs[node_id][plan_key] = target_total_cost
                    continue
                
                # ステップ2: プラン内で依存MVに対応するノードを探索し、コストを取得
                replaced_cost = self.calculate_contextual_replaced_cost(target_plan_tree, dependencies)
                
                # ステップ3: 依存MVのスキャンコスト計算
                total_mv_scan_cost = 0.0
                
                for dep_node_id in dependencies:
                    # 依存MVのSQL取得
                    if dep_node_id not in self.plans or "[]" not in self.plans[dep_node_id]:
                        continue
                    
                    dep_mv_sql = self.plans[dep_node_id]["[]"]
                    
                    # MVスペック測定
                    rows, width, _, _ = self.measure_mv_spec(dep_mv_sql)
                    
                    if rows > 0 and width > 0:
                        # 理論スキャンコスト計算
                        mv_scan_cost = self.calculate_theoretical_scan_cost(
                            rows, width, use_index=not self.use_seq_scan
                        )
                        total_mv_scan_cost += mv_scan_cost
                
                # 最終コスト計算: (元の全体コスト - 置き換わる部分のコスト) + MVスキャンコスト
                processing_cost = max(target_total_cost - replaced_cost, 0.0)
                final_cost = processing_cost + total_mv_scan_cost
                
                self.costs[node_id][plan_key] = final_cost

        self._save_costs()
        return self.costs
    
    def _save_costs(self):
        """コスト情報をJSONファイルに保存"""
        scan_mode = "seq_scan" if self.use_seq_scan else "index_scan"
        output_path = self.migration_dir / f"safe_migration_costs_{scan_mode}.json"

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.costs, f, ensure_ascii=False, indent=2)

        print(f"✓ コスト保存完了: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="安全なマイグレーションコスト推定（プラン構造解析とコスト置換法）"
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
    estimator = SafeMigrationCostEstimator(
        query_set=args.query_set,
        use_seq_scan=args.use_seq_scan
    )
    estimator.calculate_all_costs()


if __name__ == "__main__":
    main()
