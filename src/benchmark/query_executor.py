"""クエリ実行とベンチマーク機能"""

import time
from pathlib import Path
from typing import Optional
import logging

import psycopg2
from psycopg2.extensions import QueryCanceledError

from config.settings import Settings

logger = logging.getLogger(__name__)


class QueryExecutor:
    """クエリ実行管理クラス"""
    
    def __init__(self, settings: Settings):
        """初期化
        
        Args:
            settings: 設定オブジェクト
        """
        self.settings = settings
        self.db_config = settings.database
        self.connection = None
    
    def _get_connection(self):
        """データベース接続を取得または作成"""
        if self.connection is None or self.connection.closed:
            self.connection = psycopg2.connect(
                host=self.db_config.host,
                port=self.db_config.port,
                user=self.db_config.user,
                password=self.db_config.password,
                database=self.db_config.database
            )
        return self.connection
    
    def execute_query_file(
        self, 
        query_file: Path, 
        timeout_minutes: int = 30
    ) -> dict:
        """SQLファイルを実行
        
        Args:
            query_file: 実行するSQLファイルのパス
            timeout_minutes: タイムアウト時間（分）
            
        Returns:
            実行結果の辞書 {'success': bool, 'time': float, 'error': str}
        """
        start_time = time.time()
        
        # SQLファイルを読み込み
        try:
            with open(query_file, 'r', encoding='utf-8') as f:
                query = f.read().strip()
        except Exception as e:
            logger.error(f"Error reading {query_file.name}: {e}")
            return {
                'success': False,
                'time': 0.0,
                'error': str(e)
            }
        
        # セミコロンがない場合は追加（CEBクエリなど）
        if query and not query.endswith(';'):
            query = query + ';'
        
        if not query:
            logger.warning(f"Empty query in {query_file.name}")
            return {
                'success': False,
                'time': 0.0,
                'error': 'Empty query'
            }
        
        # クエリを実行
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # タイムアウトを設定
            timeout_ms = timeout_minutes * 60 * 1000
            cursor.execute(f"SET statement_timeout = '{timeout_ms}'")
            
            logger.debug(f"Executing: {query_file.name}")
            
            # クエリを実行
            cursor.execute(query)
            
            # 結果を取得（実際にクエリを実行するために重要）
            try:
                results = cursor.fetchall()
                row_count = len(results)
            except psycopg2.ProgrammingError:
                # 結果を返さないクエリ（CREATE, INSERTなど）
                row_count = cursor.rowcount
            
            conn.commit()
            cursor.close()
            
            elapsed = time.time() - start_time
            
            return {
                'success': True,
                'time': elapsed,
                'error': None,
                'row_count': row_count
            }
                
        except QueryCanceledError:
            elapsed = time.time() - start_time
            logger.warning(f"Query {query_file.name} timed out after {timeout_minutes} minutes")
            if self.connection:
                self.connection.rollback()
            return {
                'success': False,
                'time': elapsed,
                'error': f'Timeout after {timeout_minutes} minutes'
            }
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Error executing {query_file.name}: {e}")
            if self.connection:
                self.connection.rollback()
            return {
                'success': False,
                'time': elapsed,
                'error': str(e)
            }
    
    # IMDB (JOB/CEB) で使用されるテーブル一覧
    IMDB_TABLES = [
        'title',
        'kind_type', 
        'movie_info',
        'movie_info_idx',
        'info_type',
        'cast_info',
        'role_type',
        'name',
        'aka_name',
        'aka_title',
        'char_name',
        'company_name',
        'company_type',
        'complete_cast',
        'comp_cast_type',
        'keyword',
        'link_type',
        'movie_companies',
        'movie_keyword',
        'movie_link',
        'person_info',
    ]
    
    def _warmup_tables(self) -> float:
        """pg_prewarm で IMDB テーブルを PostgreSQL バッファキャッシュに強制ロード。

        COUNT(*) スキャンは OS キャッシュには効くが shared_buffers には載らない。
        pg_prewarm を使うことで確実に shared_buffers へロードし、
        実験間のキャッシュ状態の差異による性能ばらつきを防ぐ。
        pg_prewarm が使えないテーブルは COUNT(*) でフォールバック。
        """
        logger.info("=" * 50)
        logger.info("Starting cache warmup (pg_prewarm)...")
        logger.info("=" * 50)

        warmup_start = time.time()
        conn = self._get_connection()
        cursor = conn.cursor()

        # pg_prewarm 拡張を有効化（未インストールでも CREATE IF NOT EXISTS で安全）
        try:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_prewarm")
            conn.commit()
            use_prewarm = True
        except Exception:
            conn.rollback()
            use_prewarm = False

        warmed_tables = []
        for table in self.IMDB_TABLES:
            try:
                table_start = time.time()
                if use_prewarm:
                    # 'read' モード: テーブルページを全て OS ページキャッシュに読み込む。
                    # shared_buffers (128MB) は大テーブルには小さすぎるため 'buffer' は効果薄。
                    # 'read' は OS キャッシュ (数 GB) を利用するため movie_info/cast_info
                    # のような GB 級テーブルも保持でき、実験間のキャッシュ差異を排除できる。
                    cursor.execute(f"SELECT pg_prewarm('{table}', 'read')")
                    pages = cursor.fetchone()[0]
                    conn.commit()
                    table_elapsed = time.time() - table_start
                    logger.info(f"  [Warmup] {table}: {pages:,} pages read-prewarm ({table_elapsed:.2f}s)")
                else:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    table_elapsed = time.time() - table_start
                    logger.info(f"  [Warmup] {table}: {count:,} rows scan ({table_elapsed:.2f}s)")
                warmed_tables.append(table)
            except Exception as e:
                logger.debug(f"  [Warmup] {table}: skipped ({e})")
                conn.rollback()

        cursor.close()
        warmup_elapsed = time.time() - warmup_start
        logger.info(f"✓ Warmup completed: {len(warmed_tables)} tables in {warmup_elapsed:.2f}s")
        logger.info("=" * 50)
        return warmup_elapsed
    
    def _warmup_queries(
        self,
        query_files: list,
        timeout_minutes: int = 30,
        verbose: bool = False
    ) -> float:
        """キャッシュウォームアップのためクエリを事前実行（結果は計測に含めない）。

        _warmup_tables (pg_prewarm) はシーケンシャルスキャンパターンを温めるが、
        30a.sql のような random access (index scan) パターンには不十分。
        全クエリのドライランにより実際のアクセスパターンで OS キャッシュを温める。
        
        Args:
            query_files: クエリファイルのリスト
            timeout_minutes: タイムアウト時間（分）
            verbose: 詳細ログを出力するか
            
        Returns:
            ウォームアップにかかった時間（秒）
        """
        logger.info("=" * 50)
        logger.info("Starting cache warmup (results will not be counted)...")
        logger.info("=" * 50)
        
        warmup_start = time.time()
        
        for idx, query_file in enumerate(query_files, 1):
            query_start = time.time()
            result = self.execute_query_file(query_file, timeout_minutes)
            query_elapsed = time.time() - query_start
            
            if verbose:
                logger.info(f"  [Warmup {idx}/{len(query_files)}] {query_file.name} - {query_elapsed:.2f}s")
            else:
                # 進捗を1%ごと、または最低でも10件ごとに表示
                step = max(1, min(len(query_files) // 100, 10))
                if idx == 1 or idx == len(query_files) or idx % step == 0:
                    elapsed_total = time.time() - warmup_start
                    status = "OK" if result.get('success') else f"FAIL: {result.get('error', 'unknown')[:30]}"
                    logger.info(f"  [Warmup] {idx}/{len(query_files)} ({idx * 100 // len(query_files)}%) - {query_elapsed:.2f}s - {status}")
        
        warmup_elapsed = time.time() - warmup_start
        logger.info(f"✓ Warmup completed in {warmup_elapsed:.2f}s")
        logger.info("=" * 50)
        
        return warmup_elapsed

    def execute_benchmark(
        self, 
        query_dir: Path,
        timeout_minutes: int = 30,
        verbose: bool = False,
        warmup: bool = True
    ) -> dict:
        """ベンチマークを実行
        
        Args:
            query_dir: クエリファイルが格納されているディレクトリ
            timeout_minutes: 各クエリのタイムアウト時間（分）
            verbose: 詳細ログを出力するか
            warmup: ウォームアップを実行するか（デフォルト: True）
            
        Returns:
            ベンチマーク結果の辞書
        """
        from src.utils.legacy import natural_sort_key
        
        logger.info(f"Starting benchmark execution from {query_dir}")
        
        # クエリファイルを取得してソート
        query_files = sorted(
            query_dir.glob("*.sql"),
            key=lambda x: natural_sort_key(str(x))
        )
        
        if not query_files:
            logger.error(f"No SQL files found in {query_dir}")
            return {
                'total_queries': 0,
                'successful': 0,
                'failed': 0,
                'total_time': 0,
                'queries': []
            }
        
        logger.info(f"Found {len(query_files)} queries to execute")
        
        # ウォームアップ実行（総実行時間には含めない）
        warmup_time = 0.0
        if warmup:
            warmup_time = self._warmup_tables()
        
        results = []
        successful = 0
        failed = 0
        total_time = 0
        
        logger.info("Starting actual benchmark measurement...")
        benchmark_start = time.time()
        
        for idx, query_file in enumerate(query_files, 1):
            logger.info(f"[{idx}/{len(query_files)}] Executing {query_file.name}...")
            
            result = self.execute_query_file(query_file, timeout_minutes)
            total_time += result['time']
            
            if result['success']:
                successful += 1
                logger.info(f"  ✓ Success ({result['time']:.2f}s)")
            else:
                failed += 1
                error_msg = result['error']
                if error_msg and len(error_msg) > 100:
                    error_msg = error_msg[:100] + "..."
                logger.warning(f"  ✗ Failed ({result['time']:.2f}s): {error_msg}")
                
                if verbose and result['error']:
                    logger.debug(f"Full error: {result['error']}")
            
            results.append({
                'query_id': query_file.stem,
                'query_file': str(query_file),
                'success': result['success'],
                'execution_time': round(result['time'], 2),
                'error': result['error']
            })
        
        benchmark_elapsed = time.time() - benchmark_start
        
        # サマリーを表示
        logger.info("")
        logger.info("Benchmark Summary:")
        if warmup:
            logger.info(f"  Warmup time: {warmup_time:.2f}s (not included in total)")
        logger.info(f"  Total queries: {len(query_files)}")
        logger.info(f"  ✓ Successful: {successful}")
        logger.info(f"  ✗ Failed: {failed}")
        logger.info(f"  Total execution time: {total_time:.2f}s")
        logger.info(f"  Avg time per query: {total_time/len(query_files):.2f}s")
        logger.info(f"  Benchmark elapsed: {benchmark_elapsed:.2f}s")
        
        return {
            'total_queries': len(query_files),
            'successful': successful,
            'failed': failed,
            'total_time': round(total_time, 2),
            'benchmark_elapsed': round(benchmark_elapsed, 2),
            'avg_time_per_query': round(total_time / len(query_files), 2) if query_files else 0,
            'warmup_enabled': warmup,
            'warmup_time': round(warmup_time, 2) if warmup else 0,
            'queries': results
        }

    def execute_redbench_workload(
        self,
        workload_csv: Path,
        redbench_base_dir: Path,
        timeout_minutes: int = 30,
        verbose: bool = False,
        warmup: bool = True,
        max_queries: int = None
    ) -> dict:
        """RedBenchワークロードCSVからクエリを実行
        
        RedBenchのワークロードCSVは、CEBクエリへのパスを含んでいます。
        このメソッドはCSVを読み込み、指定されたクエリを順番に実行します。
        
        Args:
            workload_csv: RedBenchワークロードCSVファイルのパス
            redbench_base_dir: RedBenchのベースディレクトリ（CEBクエリが含まれる）
            timeout_minutes: 各クエリのタイムアウト時間（分）
            verbose: 詳細ログを出力するか
            warmup: ウォームアップを実行するか（デフォルト: True）
            max_queries: 実行するクエリの最大数（Noneの場合は全て実行）
            
        Returns:
            ベンチマーク結果の辞書
        """
        import csv
        
        logger.info(f"Loading RedBench workload from {workload_csv}")
        
        # CSVファイルを読み込み
        query_entries = []
        with open(workload_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                query_entries.append(row)
        
        if max_queries:
            query_entries = query_entries[:max_queries]
        
        logger.info(f"Found {len(query_entries)} queries in workload")
        
        # クエリファイルパスを解決
        query_files = []
        for entry in query_entries:
            filepath = entry['filepath']
            query_file = redbench_base_dir / filepath
            if query_file.exists():
                query_files.append((query_file, entry))
            else:
                logger.warning(f"Query file not found: {query_file}")
        
        if not query_files:
            logger.error(f"No valid query files found in workload")
            return {
                'total_queries': 0,
                'successful': 0,
                'failed': 0,
                'total_time': 0,
                'queries': []
            }
        
        logger.info(f"Resolved {len(query_files)} query files")
        
        # ウォームアップ実行（テーブルスキャン方式）
        warmup_time = 0.0
        if warmup:
            warmup_time = self._warmup_tables()
        
        results = []
        successful = 0
        failed = 0
        total_time = 0
        
        logger.info("Starting actual benchmark measurement...")
        benchmark_start = time.time()
        
        for idx, (query_file, entry) in enumerate(query_files, 1):
            query_id = entry.get('query_id', query_file.stem)
            
            if verbose or idx == 1 or idx == len(query_files) or idx % max(1, len(query_files) // 20) == 0:
                logger.info(f"[{idx}/{len(query_files)}] Executing {query_file.name} (id={query_id})...")
            
            result = self.execute_query_file(query_file, timeout_minutes)
            total_time += result['time']
            
            if result['success']:
                successful += 1
                if verbose:
                    logger.info(f"  ✓ Success ({result['time']:.2f}s)")
            else:
                failed += 1
                error_msg = result['error']
                if error_msg and len(error_msg) > 100:
                    error_msg = error_msg[:100] + "..."
                logger.warning(f"  ✗ Failed ({result['time']:.2f}s): {error_msg}")
            
            results.append({
                'query_id': str(query_id),
                'query_file': str(query_file),
                'template': query_file.parent.name,  # e.g., "10a"
                'success': result['success'],
                'execution_time': round(result['time'], 2),
                'error': result['error']
            })
        
        benchmark_elapsed = time.time() - benchmark_start
        
        # サマリーを表示
        logger.info("")
        logger.info("RedBench Workload Summary:")
        logger.info(f"  Workload: {workload_csv.name}")
        if warmup:
            logger.info(f"  Warmup time: {warmup_time:.2f}s (not included in total)")
        logger.info(f"  Total queries: {len(query_files)}")
        logger.info(f"  ✓ Successful: {successful}")
        logger.info(f"  ✗ Failed: {failed}")
        logger.info(f"  Total execution time: {total_time:.2f}s")
        logger.info(f"  Avg time per query: {total_time/len(query_files):.2f}s")
        logger.info(f"  Benchmark elapsed: {benchmark_elapsed:.2f}s")
        
        return {
            'workload_file': str(workload_csv),
            'total_queries': len(query_files),
            'successful': successful,
            'failed': failed,
            'total_time': round(total_time, 2),
            'benchmark_elapsed': round(benchmark_elapsed, 2),
            'avg_time_per_query': round(total_time / len(query_files), 2) if query_files else 0,
            'warmup_enabled': warmup,
            'warmup_time': round(warmup_time, 2) if warmup else 0,
            'queries': results
        }
