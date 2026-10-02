import json
import psycopg2
import re
import time
from pathlib import Path
from typing import Dict, Any, Tuple, List
from multiprocessing import Pool, cpu_count
from functools import partial

from config.settings import Settings

class SamplingMigrationCostCalculator:
    """サンプリングを使用してMVのサイズを推定するクラス"""

    # テーブル設定: {table_name: (alias, sampling_rate)}
    # サンプリング率は母集団サイズに応じて段階的に設定
    # 優先度順（多側テーブル優先）に並べる
    TARGET_TABLES = {
        # === 1. 巨大Fact Tables (10% サンプリング) ===
        "cast_info": ("ci", 0.01),          # 3.8GB, 36M行 - title/name/char_nameの多側
        "movie_info": ("mi", 0.01),          # 1.9GB, 15M行 - titleの多側
        
        # === 2. 中規模Fact Tables (20% サンプリング) ===
        "movie_keyword": ("mk", 0.05),       # 361MB, 4.5M行 - title/keywordの多側
        "movie_companies": ("mc", 0.05),     # 282MB, 2.6M行 - title/company_nameの多側
        "person_info": ("pi", 0.05),         # 550MB, 3.0M行 - nameの多側
        "movie_info_idx": ("mi_idx", 0.05),  # 123MB, 1.4M行 - titleの多側
        "aka_name": ("an", 0.05),            # 125MB, 901K行 - nameの多側
        
        # === 3. 小規模Fact Tables (50% サンプリング) ===
        "aka_title": ("at", 1.0),           # 67MB, 361K行 - titleの多側
        "complete_cast": ("cc", 1.0),       # 11MB, 135K行 - titleの多側
        "movie_link": ("ml", 1.0),          # 3MB, 30K行 - titleの多側
        
        # === 4. Entity/Dimension Tables (30% サンプリング) ===
        "title": ("t", 0.10),                # 368MB, 2.5M行 - マスタテーブル
        "name": ("n", 0.10),                 # 552MB, 4.2M行 - マスタテーブル
        "char_name": ("chn", 0.10),          # 373MB, 3.1M行 - ディメンションテーブル
        
        # === 5. 小規模Dictionary Tables (50% サンプリング) ===
        "company_name": ("cn", 1.0),        # 31MB, 235K行 - ディメンションテーブル
        "keyword": ("k", 1.0),              # 12MB, 134K行 - ディメンションテーブル
        
        # === 6. Type Tables (100% サンプリング = 全件) ===
        "info_type": ("it", 1.0),            # 24kB, 113行
        "kind_type": ("kt", 1.0),            # 24kB, 7行
        "company_type": ("ct", 1.0),         # 24kB, 4行
        "role_type": ("rt", 1.0),            # 24kB, 12行
        "link_type": ("lt", 1.0),            # 24kB, 18行
        "comp_cast_type": ("cct", 1.0),      # 24kB, 4行
    }
    
    # テーブル優先度順リスト（_rewrite_queryで使用）
    TABLE_PRIORITY = [
        "cast_info", "movie_info", "movie_keyword", "movie_companies",
        "person_info", "movie_info_idx", "aka_name", "aka_title",
        "complete_cast", "movie_link", "title", "name", "char_name",
        "company_name", "keyword", "info_type", "kind_type",
        "company_type", "role_type", "link_type", "comp_cast_type"
    ]

    # デフォルト設定（互換性のため残す）
    SAMPLING_RATE = 0.10  # 未使用（各テーブルが個別レートを持つ）
    SCALE_FACTOR = 1.0 / SAMPLING_RATE  # 未使用
    OVERHEAD_MULTIPLIER = 1.0
    # EXPLAIN-based size estimates are typically 64x smaller than actual sizes
    # (based on analysis of 22 root nodes from JOB workload)
    EXPLAIN_SIZE_CORRECTION_FACTOR = 1 # 64

    def __init__(self, settings: Settings, query_set: str = "job_like", precomputed_costs_file: str = None):
        self.settings = settings
        self.query_set = query_set
        self.json_file_path = Path(__file__).parent.parent / "04_migration" / query_set / "simple_migration_plans.json"
        self.output_dir = self.json_file_path.parent
        self.plans = self._load_plans()
        self.costs = {}
        self.precomputed_costs_file = precomputed_costs_file

    def _load_plans(self) -> Dict[str, Any]:
        with open(self.json_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _get_connection(self):
        return psycopg2.connect(
            host=self.settings.database.host,
            port=self.settings.database.port,
            dbname=self.settings.database.database,
            user=self.settings.database.user,
            password=self.settings.database.password
        )

    def _run_sql(self, conn, sql_text):
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql_text)
            conn.commit()
            return True
        except Exception as e:
            print(f"Error running SQL: {sql_text}")
            print(str(e))
            conn.rollback()
            return False

    def create_sample_tables(self, conn):
        """サンプルテーブルを作成（ハッシュベースのCorrelated Samplingを採用しZero-tuple問題を防止）"""
        print("Dropping existing sample tables first...")
        self.drop_sample_tables(conn)
        
        print("Creating sample tables...")
        created_tables = []
        failed_tables = []
        
        for table, (alias, sampling_rate) in self.TARGET_TABLES.items():
            sample_table = f"sample_{table}"
            rate_percent = sampling_rate * 100
            print(f"  Creating {sample_table} ({rate_percent:.0f}% of {table})")
            
            # ハッシュベースサンプリングによるテーブル作成
            # 結合キーになりやすいカラムを優先してハッシュキーとして選定する
            hash_key = None
            if table in ["cast_info", "movie_info", "movie_keyword", "movie_companies", "movie_info_idx", "complete_cast", "movie_link", "aka_title"]:
                hash_key = "movie_id"
            elif table in ["person_info", "aka_name"]:
                hash_key = "person_id"
            elif table in ["title", "name", "char_name", "company_name", "keyword"]:
                hash_key = "id"
            
            if hash_key and sampling_rate < 1.0:
                # Correlated Sampling (同じIDは確実にすべてのテーブルで選ばれる/落とされる)
                sql_text = f"""
                CREATE TABLE {sample_table} AS 
                SELECT * FROM {table} 
                WHERE mod(abs(hashtext({hash_key}::text)), 100) < {rate_percent};
                """
            elif sampling_rate < 1.0:
                # 結合キーが無いか不明な場合はBERNOULLI
                sql_text = f"""
                CREATE TABLE {sample_table} AS SELECT * FROM {table} TABLESAMPLE BERNOULLI ({rate_percent});
                """
            else:
                # 100%の場合は全件コピー
                sql_text = f"""
                CREATE TABLE {sample_table} AS SELECT * FROM {table};
                """
                
            if self._run_sql(conn, sql_text):
                created_tables.append(sample_table)
                
                # 最低限必要なJOIN用インデックスを付与
                index_sqls = []
                if table in ["title", "name", "char_name", "company_name", "keyword"]:
                    index_sqls.append(f"CREATE INDEX ON {sample_table}(id);")
                if table in ["cast_info", "movie_info", "movie_keyword", "movie_companies", "movie_info_idx", "complete_cast", "movie_link", "aka_title"]:
                    index_sqls.append(f"CREATE INDEX ON {sample_table}(movie_id);")
                if table in ["cast_info", "person_info", "aka_name"]:
                    index_sqls.append(f"CREATE INDEX ON {sample_table}(person_id);")
                if table == "movie_keyword":
                    index_sqls.append(f"CREATE INDEX ON {sample_table}(keyword_id);")
                if table == "movie_companies":
                    index_sqls.append(f"CREATE INDEX ON {sample_table}(company_id);")
                if table == "cast_info":
                    index_sqls.append(f"CREATE INDEX ON {sample_table}(person_role_id);")
                    index_sqls.append(f"CREATE INDEX ON {sample_table}(role_id);")
                
                for idx_sql in index_sqls:
                    self._run_sql(conn, idx_sql)
                
                self._run_sql(conn, f"ANALYZE {sample_table};")
            else:
                print(f"  Failed to create {sample_table}")
                failed_tables.append(sample_table)
        
        # 作成されたテーブルを確認
        print(f"\nSample table creation summary:")
        print(f"  Created: {len(created_tables)}/{len(self.TARGET_TABLES)}")
        if failed_tables:
            print(f"  Failed: {failed_tables}")
            return False
        
        # データベースで実際に存在するか確認
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'sample_%'")
                existing = {row[0] for row in cursor.fetchall()}
                missing = [t for t in created_tables if t not in existing]
                if missing:
                    print(f"  Warning: Some tables missing in DB: {missing}")
                    return False
                print(f"  All {len(created_tables)} sample tables verified in database.")
        except Exception as e:
            print(f"  Error verifying tables: {e}")
            conn.rollback()
        
        return True

    def drop_sample_tables(self, conn):
        print("Dropping sample tables...")
        for table in self.TARGET_TABLES.keys():
            sample_table = f"sample_{table}"
            self._run_sql(conn, f"DROP TABLE IF EXISTS {sample_table};")

    def _get_sample_estimate(self, conn, query) -> Tuple[int, int]:
        query = query.strip().rstrip(';')
        wrapped_query = f"""
        SELECT count(*), sum(pg_column_size(sub)) 
        FROM ({query}) as sub;
        """
        try:
            with conn.cursor() as cursor:
                cursor.execute(wrapped_query)
                result = cursor.fetchone()
                if result and len(result) >= 2:
                    rows = int(result[0]) if result[0] else 0
                    size = int(result[1]) if result[1] else 0
                    return rows, size
            return 0, 0
        except Exception as e:
            print(f"Error executing sample query: {e}")
            print(f"  Query: {query[:200]}...")
            conn.rollback()  # トランザクションをロールバックしてエラー状態を解除
            return 0, 0

    def _rewrite_query(self, query) -> Tuple[str, List[str], float]:
        """クエリ内のテーブルを可能な限りすべてサンプルテーブルに置換
        
        Returns:
            Tuple[str, List[str], float]: (置換後のクエリ, 置換したテーブル名のリスト, 総合スケールファクタ) 
            マッチしない場合は (None, [], 1.0)
        """
        new_query = query
        replaced_tables = set()
        
        for table in self.TABLE_PRIORITY:
            # FROM/JOIN句のテーブル参照にマッチ
            pattern = re.compile(
                rf"(?:FROM|JOIN|,)\s+{table}\s+(?:AS\s+)?(\w+)\b",
                re.IGNORECASE
            )
            
            def replace_func(match):
                alias = match.group(1)
                prefix = match.group(0).split()[0]  # FROM, JOIN, or ,
                sample_table = f"sample_{table}"
                replaced_tables.add(table)
                return f"{prefix} {sample_table} AS {alias}"

            modified_query = pattern.sub(replace_func, new_query)
            if modified_query != new_query:
                new_query = modified_query
        
        if not replaced_tables:
            return None, [], 1.0
            
        # Correlated Sampling (ハッシュベース) を使用する場合は、
        # JOIN時の一致率が保たれるため、「最も小さいサンプリング率（最も強い圧縮）」を基準のスケールファクタとするのが実態に近くなる。
        # 単純なBERNOULLIの乗算（1/(0.1*0.1) = 100）だと過大評価になるため修正。
        min_sampling_rate = 1.0
        for table in replaced_tables:
            rate = self.TARGET_TABLES[table][1]
            if rate < min_sampling_rate:
                min_sampling_rate = rate
                
        total_scale_factor = 1.0 / min_sampling_rate
        
        return new_query, list(replaced_tables), total_scale_factor
    
    @staticmethod
    def _process_single_node(args: Tuple[str, Dict, Settings, str, float, float]) -> Tuple[str, Dict[str, Dict[str, Any]]]:
        """単一ノードの処理（並列実行用の静的メソッド）"""
        node, plans, settings, query_set, sampling_rate, scale_factor = args
        
        # 新しい接続を作成（各プロセスで独立した接続が必要）
        conn = psycopg2.connect(
            host=settings.database.host,
            port=settings.database.port,
            dbname=settings.database.database,
            user=settings.database.user,
            password=settings.database.password
        )
        
        node_costs = {}
        overhead_multiplier = 1.2
        # テーブル設定: 辞書形式で各テーブルに個別サンプリング率を設定
        target_tables = {
            # === 1. 巨大Fact Tables (10% サンプリング) ===
            "cast_info": ("ci", 0.10),
            "movie_info": ("mi", 0.10),
            # === 2. 中規模Fact Tables (20% サンプリング) ===
            "movie_keyword": ("mk", 0.20),
            "movie_companies": ("mc", 0.20),
            "person_info": ("pi", 0.20),
            "movie_info_idx": ("mi_idx", 0.20),
            "aka_name": ("an", 0.20),
            # === 3. 小規模Fact Tables (50% サンプリング) ===
            "aka_title": ("at", 0.50),
            "complete_cast": ("cc", 0.50),
            "movie_link": ("ml", 0.50),
            # === 4. Entity/Dimension Tables (30% サンプリング) ===
            "title": ("t", 0.30),
            "name": ("n", 0.30),
            "char_name": ("chn", 0.30),
            # === 5. 小規模Dictionary Tables (50% サンプリング) ===
            "company_name": ("cn", 0.50),
            "keyword": ("k", 0.50),
            # === 6. Type Tables (100% サンプリング) ===
            "info_type": ("it", 1.0),
            "kind_type": ("kt", 1.0),
            "company_type": ("ct", 1.0),
            "role_type": ("rt", 1.0),
            "link_type": ("lt", 1.0),
            "comp_cast_type": ("cct", 1.0),
        }
        
        # テーブル優先度順リスト
        table_priority = [
            "cast_info", "movie_info", "movie_keyword", "movie_companies",
            "person_info", "movie_info_idx", "aka_name", "aka_title",
            "complete_cast", "movie_link", "title", "name", "char_name",
            "company_name", "keyword", "info_type", "kind_type",
            "company_type", "role_type", "link_type", "comp_cast_type"
        ]
        
        try:
            for plan_key in sorted(plans.keys()):
                sql = plans[plan_key]
                
                if plan_key == "[]":
                    est_rows = 0
                    est_size = 0
                    cost = 0.0
                    
                    # EXPLAIN でコストを取得
                    try:
                        with conn.cursor() as cursor:
                            select_part = sql
                            if "CREATE MATERIALIZED VIEW" in sql:
                                match_create = re.search(r"AS\s+(SELECT.*)", sql, re.IGNORECASE | re.DOTALL)
                                if match_create:
                                    select_part = match_create.group(1)
                            
                            cursor.execute(f"EXPLAIN (FORMAT JSON) {select_part}")
                            res = cursor.fetchone()
                            if res:
                                plan = res[0][0]['Plan']
                                cost = float(plan.get('Total Cost', 0.0))
                                est_rows = int(plan.get('Plan Rows', 0))
                                width = int(plan.get('Plan Width', 0))
                                est_size = est_rows * width
                    except Exception:
                        pass
                    
                    # サンプリングでサイズを推定
                    size_source = "explain"  # デフォルトはEXPLAIN
                    match = re.search(r"AS\s+(SELECT.*);", sql, re.IGNORECASE | re.DOTALL)
                    if not match:
                        match = re.search(r"AS\s+(SELECT.*)", sql, re.IGNORECASE | re.DOTALL)
                    
                    if match:
                        select_query = match.group(1)
                        
                        # クエリを書き換え（すべての対象テーブルを置換）
                        matched_tables = set()
                        rewritten_query = select_query
                        
                        for table in table_priority:
                            # FROM/JOIN句のテーブル参照にマッチ
                            pattern = re.compile(
                                rf"(?:FROM|JOIN|,)\s+{table}\s+(?:AS\s+)?(\w+)\b",
                                re.IGNORECASE
                            )
                            def replace_func(match):
                                alias = match.group(1)
                                prefix = match.group(0).split()[0]
                                sample_table = f"sample_{table}"
                                matched_tables.add(table)
                                return f"{prefix} {sample_table} AS {alias}"

                            modified_query = pattern.sub(replace_func, rewritten_query)
                            if modified_query != rewritten_query:
                                rewritten_query = modified_query
                        
                        if matched_tables:
                            min_sampling_rate = 1.0
                            for table in matched_tables:
                                rate = target_tables[table][1]
                                if rate < min_sampling_rate:
                                    min_sampling_rate = rate
                                    
                            total_scale_factor_parallel = 1.0 / min_sampling_rate
                            
                            # サンプルからサイズを取得
                            wrapped_query = f"""
                            SELECT count(*), sum(pg_column_size(sub)) 
                            FROM ({rewritten_query}) as sub;
                            """
                            try:
                                with conn.cursor() as cursor:
                                    cursor.execute("SET statement_timeout = '10s';")
                                    cursor.execute(wrapped_query)
                                    result = cursor.fetchone()
                                    if result and len(result) >= 2:
                                        rows = int(result[0]) if result[0] else 0
                                        size = int(result[1]) if result[1] else 0
                                        if rows > 0:
                                            est_rows = int(rows * total_scale_factor_parallel)
                                            est_size = int(size * total_scale_factor_parallel * overhead_multiplier)
                                            size_source = "sampling"  # サンプリング成功
                            except Exception:
                                pass

                    
                    # EXPLAINベースの場合、サイズを補正（実測との乖離を考慮）
                    if size_source == "explain" and est_size > 0:
                        correction = SamplingMigrationCostCalculator.EXPLAIN_SIZE_CORRECTION_FACTOR
                        est_size = int(est_size * correction)
                        est_rows = int(est_rows * correction)
                    
                    # EXPLAINのコストをutilityとし、作成コスト=読み取り+書き込みを計算
                    # 書き込みコスト = ページ書き込み + タプル処理
                    write_pages = (est_size // 8192) + 1 if est_size > 0 else 0
                    write_cost = (write_pages * 1.0) + (est_rows * 0.01)  # SEQ_PAGE_COST + CPU_TUPLE_COST
                    creation_cost = cost + write_cost  # 読み取り + 書き込み
                    
                    node_costs[plan_key] = {
                        "cost": creation_cost,  # 作成コスト（読み取り + 書き込み）
                        "utility": cost,  # 利得（EXPLAINコスト = 読み取りのみ）
                        "rows": est_rows,
                        "width": int(est_size / est_rows) if est_rows > 0 else 0,
                        "size": est_size,
                        "size_source": size_source  # "sampling" or "explain"
                    }
                else:
                    node_costs[plan_key] = {
                        "cost": 0.0,
                        "utility": 0.0,
                        "rows": 0,
                        "width": 0,
                        "size": 0
                    }
        
        finally:
            conn.close()
        
        return node, node_costs

    def calculate_all_costs(self, use_parallel: bool = False, max_workers: int = None) -> Dict[str, Dict[str, Dict[str, Any]]]:
        if self.precomputed_costs_file:
            print(f"Using precomputed costs from: {self.precomputed_costs_file}")
            with open(self.precomputed_costs_file, 'r', encoding='utf-8') as f:
                self.costs = json.load(f)
            self.save_costs() # Ensure it's saved to the expected location for downstream phases
            return self.costs

        print("\n" + "="*70)
        print(f"Calculating migration costs using SAMPLING ({'PARALLEL' if use_parallel else 'SEQUENTIAL'})...")
        print("="*70)

        conn = self._get_connection()
        try:
            if not self.create_sample_tables(conn):
                print("Failed to create sample tables.")
                return {}

            total_nodes = len(self.plans)
            
            if use_parallel:
                # 並列処理
                if max_workers is None:
                    max_workers = min(cpu_count(), total_nodes)
                
                print(f"  Using {max_workers} workers for parallel processing...")
                
                # 各ノードの処理用の引数を準備
                process_args = [
                    (node, plans, self.settings, self.query_set, self.SAMPLING_RATE, self.SCALE_FACTOR)
                    for node, plans in self.plans.items()
                ]
                
                # 並列実行
                with Pool(processes=max_workers) as pool:
                    results = []
                    for i, result in enumerate(pool.imap_unordered(self._process_single_node, process_args)):
                        results.append(result)
                        if (i + 1) % 10 == 0 or (i + 1) == total_nodes:
                            print(f"  Progress: {i + 1}/{total_nodes} ({(i + 1)*100//total_nodes}%)")
                
                # 結果をマージ
                for node, node_costs in results:
                    self.costs[node] = node_costs
                
                print(f"\nProcessed {total_nodes} MVs with parallel sampling.")
            
            else:
                # 逐次処理（元の実装）
                processed = 0
                updated_count = 0
                skipped_count = 0

                for node, plans in self.plans.items():
                    processed += 1
                    if processed % 10 == 0 or processed == total_nodes:
                        print(f"  Progress: {processed}/{total_nodes} ({processed*100//total_nodes}%)")

                    self.costs[node] = {}

                    for plan_key in sorted(plans.keys()):
                        sql = plans[plan_key]

                        if plan_key == "[]":
                            # Extract SELECT part
                            match = re.search(r"AS\s+(SELECT.*);", sql, re.IGNORECASE | re.DOTALL)
                            if not match:
                                match = re.search(r"AS\s+(SELECT.*)", sql, re.IGNORECASE | re.DOTALL)
                            
                            est_rows = 0
                            est_size = 0
                            cost = 0.0
                            
                            # EXPLAIN でコストを取得
                            try:
                                with conn.cursor() as cursor:
                                    select_part = sql
                                    if "CREATE MATERIALIZED VIEW" in sql:
                                        match_create = re.search(r"AS\s+(SELECT.*)", sql, re.IGNORECASE | re.DOTALL)
                                        if match_create:
                                            select_part = match_create.group(1)
                                    
                                    cursor.execute(f"EXPLAIN (FORMAT JSON) {select_part}")
                                    res = cursor.fetchone()
                                    if res:
                                        plan = res[0][0]['Plan']
                                        cost = float(plan.get('Total Cost', 0.0))
                                        # Fallback values
                                        est_rows = int(plan.get('Plan Rows', 0))
                                        width = int(plan.get('Plan Width', 0))
                                        est_size = est_rows * width
                            except Exception:
                                conn.rollback()  # トランザクションをロールバック

                            select_query = match.group(1) if match else sql
                            size_source = "explain"

                            # クエリを書き換え（すべての対象テーブルを置換）
                            rewritten_query, matched_tables, total_scale_factor_seq = self._rewrite_query(select_query)
                        
                            if rewritten_query and matched_tables:
                                # サンプルからサイズを取得
                                wrapped_query = f"""
                                SELECT count(*), sum(pg_column_size(sub)) 
                                FROM ({rewritten_query}) as sub;
                                """
                                try:
                                    with conn.cursor() as cursor:
                                        cursor.execute("SET statement_timeout = '10s';")
                                        cursor.execute(wrapped_query)
                                        result = cursor.fetchone()
                                        if result and len(result) >= 2:
                                            rows = int(result[0]) if result[0] else 0
                                            size = int(result[1]) if result[1] else 0
                                            if rows > 0:
                                                est_rows = int(rows * total_scale_factor_seq)
                                                est_size = int(size * total_scale_factor_seq * self.OVERHEAD_MULTIPLIER)
                                                size_source = "sampling"  # サンプリング成功
                                                updated_count += 1
                                            else:
                                                skipped_count += 1
                                        else:
                                            skipped_count += 1
                                except psycopg2.errors.QueryCanceled:
                                    skipped_count += 1
                                    pass # タイムアウト時は黙ってEXPLAINにフォールバック
                                except Exception:
                                    skipped_count += 1
                                    pass
                            else:
                                skipped_count += 1
                                
                            # EXPLAINベースの場合、サイズを補正（実測との乖離を考慮）
                            if size_source == "explain" and est_size > 0:
                                est_size = int(est_size * self.EXPLAIN_SIZE_CORRECTION_FACTOR)
                                est_rows = int(est_rows * self.EXPLAIN_SIZE_CORRECTION_FACTOR)
                            
                            # EXPLAINのコストをutilityとし、作成コスト=読み取り+書き込みを計算
                            # 書き込みコスト = ページ書き込み + タプル処理
                            write_pages = (est_size // 8192) + 1 if est_size > 0 else 0
                            write_cost = (write_pages * 1.0) + (est_rows * 0.01)  # SEQ_PAGE_COST + CPU_TUPLE_COST
                            creation_cost = cost + write_cost  # 読み取り + 書き込み
                            
                            self.costs[node][plan_key] = {
                                "cost": creation_cost,  # 作成コスト（読み取り + 書き込み）
                                "utility": cost,  # 利得（EXPLAINコスト = 読み取りのみ）
                                "rows": est_rows,
                                "width": int(est_size / est_rows) if est_rows > 0 else 0,
                                "size": est_size,
                                "size_source": size_source  # "sampling" or "explain"
                            }
                        else:
                            self.costs[node][plan_key] = {
                                "cost": 0.0,
                                "utility": 0.0,
                                "rows": 0,
                                "width": 0,
                                "size": 0
                            }
                
                print(f"\nProcessed {updated_count} MVs with sampling, Skipped/Fallback {skipped_count} MVs.")
            self.drop_sample_tables(conn)
            
        finally:
            conn.close()

        self.save_costs()
        return self.costs

    def save_costs(self, output_file: str = "simple_migration_costs.json"):
        try:
            output_path = self.output_dir / output_file
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.costs, f, indent=2, ensure_ascii=False)
            print(f"Migration costs saved to: {output_path}")
        except Exception as e:
            print(f"Failed to save JSON file: {e}")
