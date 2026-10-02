import json
import psycopg2
import re
import time
from pathlib import Path
from typing import Dict, Any, Tuple, List


from config.settings import Settings

class SamplingMigrationCostCalculator:
    """サンプリングを使用してMVのサイズを推定するクラス"""

    TARGET_TABLES = [
        # === Fact Tables (巨大・最重要) ===
        ("cast_info", "ci"),
        ("movie_info", "mi"),
        ("movie_companies", "mc"),
        ("movie_keyword", "mk"),
        ("movie_info_idx", "mi_idx"),
        ("person_info", "pi"),

        # === Entity Tables (中心となる実体) ===
        ("title", "t"),
        ("name", "n"),

        # === Dictionary/Dimension Tables (フィルタ条件の要) ===
        ("keyword", "k"),
        ("info_type", "it"),
        ("company_name", "cn"),
        ("company_type", "ct"),
        ("kind_type", "kt"),
        ("role_type", "rt"),
        ("char_name", "chn"),
        ("aka_name", "an"),

        # === Additional Tables (追加) ===
        ("movie_link", "ml"),
        ("link_type", "lt"),
        ("complete_cast", "cc"),
        ("comp_cast_type", "cct"),
        ("aka_title", "at"),
    ]

    # 全件保持すべきテーブル（検索条件に使われる辞書・ディメンションテーブル）
    # これらをサンプリングすると、WHERE句でヒットしなくなり0件の原因になる
    FULL_RETENTION_TABLES = {
        # 極小テーブル（数行〜数百行）
        "info_type",      # 113行
        "kind_type",      # 7行
        "company_type",   # 4行
        "role_type",      # 12行
        "link_type",      # 18行
        "comp_cast_type", # 4行
        # ディメンションテーブル（検索条件として使われる）
        "keyword",        # WHERE句で頻繁に使用
        "company_name",   # WHERE句で頻繁に使用
        "aka_name",       # 別名検索で使用（94MB - 許容範囲）
        # name (456MB) と char_name (299MB) は大きすぎるため
        # DISTRIBUTION_KEYS でサンプリングする
    }

    # Universe Sampling用: Factテーブルのサンプリング基準キー（JOBスキーマに基づく）
    # 同じキー値を持つ行が全テーブルで一貫して保持/除外されるため、
    # 結合時の0件ヒットを回避できる
    DISTRIBUTION_KEYS = {
        # movie_id ベース（Fact Tables）
        "title": "id",
        "movie_info": "movie_id",
        "cast_info": "movie_id",
        "movie_companies": "movie_id",
        "movie_keyword": "movie_id",
        "movie_link": "movie_id",
        "movie_info_idx": "movie_id",
        "aka_title": "movie_id",
        "complete_cast": "movie_id",
        # person_id ベース
        "person_info": "person_id",
    }

    # Universe Sampling用: Factテーブルのサンプリング基準キー（JOBスキーマに基づく）
    # 同じキー値を持つ行が全テーブルで一貫して保持/除外されるため、
    # 結合時の0件ヒットを回避できる
    DISTRIBUTION_KEYS = {
        # movie_id ベース（Fact Tables）
        "title": "id",
        "movie_info": "movie_id",
        "cast_info": "movie_id",
        "movie_companies": "movie_id",
        "movie_keyword": "movie_id",
        "movie_link": "movie_id",
        "movie_info_idx": "movie_id",
        "aka_title": "movie_id",
        "complete_cast": "movie_id",
        # person_id ベース
        "person_info": "person_id",
        # 大きすぎるためFULL_RETENTIONから除外したテーブル
        "name": "id",           # 456MB - idでサンプリング
        "char_name": "id",      # 299MB - idでサンプリング
    }

    # サンプルテーブル作成時にインデックスを貼るカラム定義
    # これがないと結合時にNested Loopが爆発して遅くなる
    INDEX_DEFINITIONS = {
        "title": ["id"],
        "movie_info": ["movie_id"],
        "cast_info": ["movie_id", "person_id"],
        "movie_companies": ["movie_id"],
        "movie_keyword": ["movie_id", "keyword_id"],
        "movie_link": ["movie_id"],
        "movie_info_idx": ["movie_id"],
        "name": ["id"],
        "person_info": ["person_id"],
        "aka_name": ["person_id"],
        "keyword": ["id"],
        "company_name": ["id"],
        "aka_title": ["movie_id"],
        "complete_cast": ["movie_id"],
        "char_name": ["id"],
    }

    SAMPLING_RATE = 0.03
    SCALE_FACTOR = 1.0 / SAMPLING_RATE
    OVERHEAD_MULTIPLIER = 1.0
    # EXPLAIN-based size estimates are typically 64x smaller than actual sizes
    # (based on analysis of 22 root nodes from JOB workload)
    EXPLAIN_SIZE_CORRECTION_FACTOR = 50 # 64

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
        """Hybrid Universe Samplingを用いてサンプルテーブルを作成
        
        - Factテーブル: movie_id等のハッシュ値でUniverse Sampling
        - Dimensionテーブル: WHERE句で使われるため100%保持
        これにより、結合時の整合性を保ちつつ、検索条件の欠損による0件ヒットを回避できる。
        """
        # まず既存のサンプルテーブルを削除
        print("Dropping existing sample tables first...")
        self.drop_sample_tables(conn)
        
        print("Creating sample tables using Hybrid Universe Sampling...")
        print(f"  Fact tables: {self.SAMPLING_RATE*100}% (Universe on distribution key)")
        print(f"  Dimension tables: 100% (Full retention)")
        created_tables = []
        failed_tables = []
        
        # 100分率での閾値 (10%なら 10)
        threshold = int(self.SAMPLING_RATE * 100)
        
        for table, _ in self.TARGET_TABLES:
            sample_table = f"sample_{table}"
            
            # 1. 全件保持テーブル（Dimension/Small）
            if table in self.FULL_RETENTION_TABLES:
                print(f"  Creating {sample_table} (100% - Dimension/Small)")
                sql_text = f"CREATE TABLE {sample_table} AS SELECT * FROM {table};"
            
            # 2. Universe Sampling (Fact/Entity)
            else:
                dist_key = self.DISTRIBUTION_KEYS.get(table)
                
                if dist_key:
                    # Universe Sampling: 結合キーのハッシュ値でサンプリング
                    # key % 100 < threshold の行を全て取得
                    print(f"  Creating {sample_table} (Universe on {dist_key}, {threshold}%)")
                    sql_text = f"""
                    CREATE TABLE {sample_table} AS 
                    SELECT * FROM {table} 
                    WHERE ({dist_key} % 100) < {threshold};
                    """
                else:
                    # Distribution Keyがないテーブルは従来のBERNOULLIにフォールバック
                    rate = self.SAMPLING_RATE * 100
                    print(f"  Creating {sample_table} (BERNOULLI Fallback, {rate}%)")
                    sql_text = f"""
                    CREATE TABLE {sample_table} AS 
                    SELECT * FROM {table} TABLESAMPLE BERNOULLI ({rate});
                    """
            
            full_sql = f"{sql_text}\nANALYZE {sample_table};"
            if self._run_sql(conn, full_sql):
                created_tables.append(sample_table)
                
                # インデックス作成（パフォーマンス向上）
                if table in self.INDEX_DEFINITIONS:
                    for col in self.INDEX_DEFINITIONS[table]:
                        # インデックス名は衝突しないようにユニークにする
                        idx_name = f"idx_{sample_table}_{col}"
                        print(f"    Creating index {idx_name} on {sample_table}({col})...")
                        idx_sql = f"CREATE INDEX IF NOT EXISTS {idx_name} ON {sample_table} ({col});"
                        self._run_sql(conn, idx_sql)
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
        for table, _ in self.TARGET_TABLES:
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

    def _rewrite_query(self, query) -> Tuple[str, str]:
        """クエリ内の全ターゲットテーブルをサンプルテーブルに置換
        
        従来は最初の1テーブルのみ置換していたが、それでは片方が全件・片方がサンプル
        という状態になり、Universe Samplingの整合性が活かせない。
        全テーブルを置換することで、サンプル同士の結合となり、
        実行速度向上と整合性維持を両立できる。
        
        Returns:
            Tuple[str, str]: (置換後のクエリ, "multiple_tables" or None) 
            置換がなければ (None, None)
        """
        new_query = query
        replaced_any = False
        
        # テーブル名が部分文字列として含まれるケース（例: "movie_keyword" と "keyword"）
        # を正しく扱うため、長い名前から順に置換する
        sorted_tables = sorted(self.TARGET_TABLES, key=lambda x: len(x[0]), reverse=True)
        
        for table, _ in sorted_tables:
            sample_table = f"sample_{table}"
            
            # 正規表現: FROM/JOIN/, の直後にあるテーブル名だけを置換する
            # 単純な \b{table}\b だと、SELECT句のカラム名（例: title）まで置換してしまう
            # パターン: (境界 + FROM/JOIN/, + 空白) (テーブル名) (境界)
            pattern = re.compile(rf"(\b(?:FROM|JOIN|,)\s+)({table})\b", re.IGNORECASE)
            
            # クエリ内にテーブルが存在すれば置換
            if pattern.search(new_query):
                # \1 (FROM/JOIN/, ) はそのまま残し、\2 (テーブル名) を sample_table に変える
                new_query = pattern.sub(rf"\1{sample_table}", new_query)
                replaced_any = True
        
        if replaced_any:
            return new_query, "multiple_tables"
        return None, None
    
    def calculate_all_costs(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        if self.precomputed_costs_file:
            print(f"Using precomputed costs from: {self.precomputed_costs_file}")
            with open(self.precomputed_costs_file, 'r', encoding='utf-8') as f:
                self.costs = json.load(f)
            self.save_costs() # Ensure it's saved to the expected location for downstream phases
            return self.costs

        print("\n" + "="*70)
        print("Calculating migration costs using SAMPLING...")
        print("="*70)

        conn = self._get_connection()
        try:
            if not self.create_sample_tables(conn):
                print("Failed to create sample tables.")
                return {}

            total_nodes = len(self.plans)
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

                        size_source = "explain"  # デフォルトはEXPLAIN
                        if match:
                            select_query = match.group(1)
                            rewritten_query, used_table = self._rewrite_query(select_query)
                            
                            if rewritten_query:
                                rows, size = self._get_sample_estimate(conn, rewritten_query)
                                if rows > 0:
                                    est_rows = int(rows * self.SCALE_FACTOR)
                                    est_size = int(size * self.SCALE_FACTOR * self.OVERHEAD_MULTIPLIER)
                                    size_source = "sampling"  # サンプリング成功
                                    updated_count += 1
                                else:
                                    skipped_count += 1
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
