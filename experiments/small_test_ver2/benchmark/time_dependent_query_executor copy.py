"""時間依存型ワークロードのクエリ実行とベンチマーク機能

このモジュールは、時間軸に沿って変化するワークロードのベンチマークを実行します。
各タイムステップで:
1. マイグレーションSQLを実行（MVの作成・削除）
2. クエリを頻度情報に基づいて繰り返し実行
3. 実行時間とコストを記録
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extensions import QueryCanceledError

from config.settings import Settings

logger = logging.getLogger(__name__)


class TimeDependentQueryExecutor:
    """時間依存型ワークロード用のクエリ実行管理クラス"""
    
    def __init__(self, settings: Settings):
        """初期化
        
        Args:
            settings: 設定オブジェクト
        """
        self.settings = settings
        self.db_config = settings.database
        self.connection = None
    
    def _get_connection(self):
        """データベース接続を取得または作成
        
        Note:
            Docker環境でもlocalhost経由で接続（ポートフォワーディング使用）
            Dockerコンテナは 0.0.0.0:5432->5432/tcp でマッピングされているため、
            localhost:5432 で接続可能
        """
        if self.connection is None or self.connection.closed:
            self.connection = psycopg2.connect(
                host=self.db_config.host,
                port=self.db_config.port,
                user=self.db_config.user,
                password=self.db_config.password,
                database=self.db_config.database
            )
            # 統計情報のターゲットを1000に設定（セッションごとにリセットされるためここで設定）
            try:
                with self.connection.cursor() as cursor:
                    # cursor.execute("SET default_statistics_target = 1000;")
                    cursor.execute("SET random_page_cost = 1.1;")
                self.connection.commit()
            except Exception as e:
                logger.warning(f"Failed to set random_page_cost: {e}")
        return self.connection

    
    def _execute_sql_file(
        self, 
        sql_file: Path, 
        timeout_minutes: int = 30
    ) -> Tuple[bool, float, Optional[str]]:
        """SQLファイルを実行
        
        Args:
            sql_file: 実行するSQLファイルのパス
            timeout_minutes: タイムアウト時間（分）
            
        Returns:
            (success, elapsed_time, error_message)のタプル
        """
        start_time = time.time()
        
        # SQLファイルを読み込み
        try:
            with open(sql_file, 'r', encoding='utf-8') as f:
                sql_content = f.read()
        except Exception as e:
            logger.error(f"Error reading {sql_file.name}: {e}")
            return False, 0.0, str(e)
        
        # psqlメタコマンド（\c, \set など）を除去
        # これらはpsqlコマンドラインツール専用で、psycopg2では実行できない
        lines = sql_content.split('\n')
        filtered_lines = []
        for line in lines:
            stripped = line.strip()
            # バックスラッシュで始まる行（psqlメタコマンド）をスキップ
            if stripped.startswith('\\'):
                logger.debug(f"Skipping psql meta-command: {stripped}")
                continue
            filtered_lines.append(line)
        
        sql_content = '\n'.join(filtered_lines).strip()
        
        if not sql_content:
            logger.warning(f"Empty SQL file after filtering: {sql_file.name}")
            return False, 0.0, "Empty SQL file"
        
        # SQLを実行（複数のステートメントを個別に実行）
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # タイムアウトを設定
            timeout_ms = timeout_minutes * 60 * 1000
            cursor.execute(f"SET statement_timeout = '{timeout_ms}'")
            
            logger.debug(f"Executing SQL file: {sql_file.name}")
            
            # SQLを個別のステートメントに分割して実行
            # セミコロンで分割し、空でないステートメントのみを実行
            statements = []
            current_statement = []
            
            for line in sql_content.split('\n'):
                stripped = line.strip()
                # コメント行や空行をスキップ
                if not stripped or stripped.startswith('--'):
                    continue
                    
                current_statement.append(line)
                
                # セミコロンで終わる場合、ステートメント完成
                if stripped.endswith(';'):
                    stmt = '\n'.join(current_statement).strip()
                    if stmt and stmt != ';':
                        statements.append(stmt)
                    current_statement = []
            
            # 残りのステートメントがあれば追加
            if current_statement:
                stmt = '\n'.join(current_statement).strip()
                if stmt:
                    statements.append(stmt)
            
            print(f"DEBUG: Executing {len(statements)} SQL statements from {sql_file.name}")
            
            # 各ステートメントを個別に実行
            for idx, statement in enumerate(statements, 1):
                if idx % 10 == 0 or idx == len(statements):
                    print(f"DEBUG: Executing statement {idx}/{len(statements)}")
                    logger.info(f"  Progress: {idx}/{len(statements)} statements")
                
                cursor.execute(statement)
            
            conn.commit()
            cursor.close()
            
            elapsed = time.time() - start_time
            print(f"DEBUG: Completed {len(statements)} statements in {elapsed:.2f}s")
            return True, elapsed, None
            
        except QueryCanceledError:
            elapsed = time.time() - start_time
            logger.warning(f"SQL file {sql_file.name} timed out after {timeout_minutes} minutes")
            if self.connection:
                self.connection.rollback()
            return False, elapsed, f'Timeout after {timeout_minutes} minutes'
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Error executing {sql_file.name}: {e}")
            if self.connection:
                self.connection.rollback()
            return False, elapsed, str(e)
    
    def _execute_query(
        self, 
        query_sql: str, 
        query_name: str,
        timeout_minutes: int = 30
    ) -> Tuple[bool, float, Optional[str]]:
        """単一クエリを実行
        
        Args:
            query_sql: 実行するSQL
            query_name: クエリ名（ログ用）
            timeout_minutes: タイムアウト時間（分）
            
        Returns:
            (success, elapsed_time, error_message)のタプル
        """
        start_time = time.time()
        
        if not query_sql.strip():
            return False, 0.0, "Empty query"
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # タイムアウトを設定
            timeout_ms = timeout_minutes * 60 * 1000
            cursor.execute(f"SET statement_timeout = '{timeout_ms}'")
            
            # クエリを実行
            cursor.execute(query_sql)
            
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
            return True, elapsed, None
            
        except QueryCanceledError:
            elapsed = time.time() - start_time
            logger.warning(f"Query {query_name} timed out after {timeout_minutes} minutes")
            if self.connection:
                self.connection.rollback()
            return False, elapsed, f'Timeout after {timeout_minutes} minutes'
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Error executing query {query_name}: {e}")
            if self.connection:
                self.connection.rollback()
            return False, elapsed, str(e)
    
    def _execute_queries_with_frequency(
        self,
        query_files: List[Path],
        frequencies: List[float],
        timeout_minutes: int = 30,
        verbose: bool = False,
        ease_mode: bool = False
    ) -> Dict:
        """頻度に基づいてクエリを実行
        
        Args:
            query_files: クエリファイルのリスト
            frequencies: 各クエリの実行頻度（実行回数）
            timeout_minutes: タイムアウト時間（分）
            verbose: 詳細ログを出力するか
            ease_mode: 簡易モード（各クエリを1回実行し、時間に頻度を掛ける）
            
        Returns:
            実行結果の辞書
        """
        results = []
        total_time = 0.0
        total_executions = 0
        successful_executions = 0
        failed_executions = 0
        
        for query_file, frequency in zip(query_files, frequencies):
            # 頻度が0の場合はスキップ
            if frequency <= 0:
                if verbose:
                    logger.debug(f"Skipping {query_file.name} (frequency=0)")
                continue
            
            # SQLファイルを読み込み
            try:
                with open(query_file, 'r', encoding='utf-8') as f:
                    query_sql = f.read().strip()
            except Exception as e:
                logger.error(f"Error reading {query_file.name}: {e}")
                results.append({
                    'query_id': query_file.stem,
                    'frequency': frequency,
                    'executions': 0,
                    'success': False,
                    'error': str(e)
                })
                continue
            
            execution_times = []
            execution_count = int(frequency)
            query_successful = 0
            query_failed = 0
            
            if ease_mode:
                # 簡易モード: 1回だけ実行し、時間に頻度を掛ける
                if verbose:
                    logger.info(f"  [EASE] Executing {query_file.name} (single run, freq={frequency})...")
                
                success, elapsed, error = self._execute_query(
                    query_sql, 
                    query_file.name, 
                    timeout_minutes
                )
                
                # 実測時間と推定時間
                actual_time = elapsed
                estimated_total = elapsed * frequency
                
                execution_times.append(actual_time)
                total_time += estimated_total  # 推定時間を合計に加算
                total_executions += 1  # 実際の実行は1回
                
                if success:
                    query_successful = 1
                    successful_executions += 1
                    if verbose:
                        logger.info(f"    ✓ Success (actual: {actual_time:.2f}s, estimated: {estimated_total:.2f}s)")
                else:
                    query_failed = 1
                    failed_executions += 1
                    if verbose:
                        logger.warning(f"    ✗ Failed ({actual_time:.2f}s): {error}")
                
                # 結果記録
                results.append({
                    'query_id': query_file.stem,
                    'frequency': frequency,
                    'executions': 1,  # 実際の実行回数
                    'estimated_executions': execution_count,  # 頻度として期待される回数
                    'successful': query_successful,
                    'failed': query_failed,
                    'actual_time': round(actual_time, 5),
                    'total_time': round(estimated_total, 5),  # 推定合計時間
                    'avg_time': round(actual_time, 5),
                    'min_time': round(actual_time, 5),
                    'max_time': round(actual_time, 5),
                    'ease_mode': True
                })
            else:
                # 通常モード: 頻度分だけクエリを実行
                for exec_idx in range(execution_count):
                    if verbose:
                        logger.info(f"  [{exec_idx+1}/{execution_count}] Executing {query_file.name}...")
                    
                    success, elapsed, error = self._execute_query(
                        query_sql, 
                        query_file.name, 
                        timeout_minutes
                    )
                    
                    execution_times.append(elapsed)
                    total_time += elapsed
                    total_executions += 1
                    
                    if success:
                        query_successful += 1
                        successful_executions += 1
                        if verbose:
                            logger.info(f"    ✓ Success ({elapsed:.2f}s)")
                    else:
                        query_failed += 1
                        failed_executions += 1
                        if verbose:
                            logger.warning(f"    ✗ Failed ({elapsed:.2f}s): {error}")
                
                # クエリごとの集計
                avg_time = sum(execution_times) / len(execution_times) if execution_times else 0.0
                results.append({
                    'query_id': query_file.stem,
                    'frequency': frequency,
                    'executions': execution_count,
                    'successful': query_successful,
                    'failed': query_failed,
                    'total_time': round(sum(execution_times), 5),
                    'avg_time': round(avg_time, 5),
                    'min_time': round(min(execution_times), 5) if execution_times else 0,
                    'max_time': round(max(execution_times), 5) if execution_times else 0,
                })
        
        return {
            'queries': results,
            'total_executions': total_executions,
            'successful_executions': successful_executions,
            'failed_executions': failed_executions,
            'total_time': round(total_time, 5),
            'ease_mode': ease_mode
        }
    
    def execute_time_dependent_benchmark(
        self,
        optimization_result: Dict,
        migration_sql_dir: Path,
        rewritten_queries_base_dir: Path,
        frequencies_by_timestep: Dict[str, List[float]],
        timeout_minutes: int = 30,
        verbose: bool = False,
        ease_mode: bool = False
    ) -> Dict:
        """時間依存型ベンチマークを実行
        
        Args:
            optimization_result: 最適化結果（migration_analysisを含む）
            migration_sql_dir: マイグレーションSQLが格納されているディレクトリ
            rewritten_queries_base_dir: 書き換えられたクエリのベースディレクトリ（例: jobs/）
            frequencies_by_timestep: タイムステップごとの頻度情報
            timeout_minutes: タイムアウト時間（分）
            verbose: 詳細ログを出力するか
            ease_mode: 簡易モード（各クエリを1回実行し、時間に頻度を掛ける）
            
        Returns:
            ベンチマーク結果の辞書
        """
        print("DEBUG: execute_time_dependent_benchmark called")
        logger.info("Starting time-dependent benchmark execution")
        
        print("DEBUG: Getting migration_analysis and timesteps...")
        migration_analysis = optimization_result.get('migration_analysis', [])
        timesteps = optimization_result.get('timesteps', [])
        print(f"DEBUG: Got {len(migration_analysis)} migration_analysis entries, {len(timesteps)} timesteps")
        
        if not migration_analysis:
            logger.error("No migration_analysis found in optimization result")
            return {'error': 'No migration_analysis found'}
        
        print(f"DEBUG: About to log 'Found {len(timesteps)} timesteps to execute'")
        logger.info(f"Found {len(timesteps)} timesteps to execute")
        print("DEBUG: Logger.info completed")
        
        benchmark_start = time.time()
        timestep_results = []
        total_migration_time = 0.0
        total_query_time = 0.0
        
        print("DEBUG: Starting timestep loop...")
        # 各タイムステップを順に実行
        for t_idx, (timestep_name, timestep_info) in enumerate(zip(timesteps, migration_analysis)):
            logger.info(f"\n{'='*60}")
            logger.info(f"Timestep {t_idx}: {timestep_name}")
            logger.info(f"{'='*60}")
            
            timestep_start = time.time()
            
            # マイグレーションSQL実行（t > 0の場合）
            migration_time = 0.0
            migration_success = True
            migration_error = None
            
            if t_idx == 0:
                # 初期タイムステップ: 初期MV作成
                migration_sql_file = migration_sql_dir / f"timestep_{t_idx}_{timestep_name}.sql"
                
                if migration_sql_file.exists():
                    logger.info(f"Creating initial MVs from {migration_sql_file.name}...")
                    success, elapsed, error = self._execute_sql_file(migration_sql_file, 0)
                    migration_time = elapsed
                    migration_success = success
                    migration_error = error
                    
                    if success:
                        logger.info(f"  ✓ Initial MVs created ({elapsed:.2f}s)")
                    else:
                        logger.error(f"  ✗ Failed to create initial MVs: {error}")
                else:
                    logger.info(f"No initial migration SQL found (skipping)")
            else:
                # タイムステップ間のマイグレーション
                migration_sql_file = migration_sql_dir / f"timestep_{t_idx}_{timestep_name}.sql"
                
                if migration_sql_file.exists():
                    logger.info(f"Executing migration SQL: {migration_sql_file.name}...")
                    success, elapsed, error = self._execute_sql_file(migration_sql_file, 0)
                    migration_time = elapsed
                    migration_success = success
                    migration_error = error
                    
                    if success:
                        logger.info(f"  ✓ Migration completed ({elapsed:.2f}s)")
                    else:
                        logger.error(f"  ✗ Migration failed: {error}")
                else:
                    logger.info(f"No migration SQL found for timestep {t_idx} (no changes)")
            
            total_migration_time += migration_time
            
            # 書き換えられたクエリファイルを取得（タイムステップ別）
            rewritten_queries_dir = rewritten_queries_base_dir / f"timestep_{t_idx}_{timestep_name}"
            
            if not rewritten_queries_dir.exists():
                logger.error(f"Rewritten queries directory not found: {rewritten_queries_dir}")
                return {'error': f'Rewritten queries directory not found for timestep {timestep_name}'}
            
            # Helper for natural sort (to match io_loaders.py behavior)
            import re
            def natural_sort_key(s):
                return [int(text) if text.isdigit() else text.lower() for text in re.split("([0-9]+)", str(s))]
            
            query_files_for_timestep = sorted(rewritten_queries_dir.glob("*.sql"), key=lambda x: natural_sort_key(x.name))
            
            if not query_files_for_timestep:
                logger.error(f"No query files found in {rewritten_queries_dir}")
                return {'error': f'No query files found for timestep {timestep_name}'}
            
            logger.info(f"Executing queries for timestep {timestep_name}...")
            logger.info(f"  Using rewritten queries from: {rewritten_queries_dir}")
            logger.info(f"  Query count: {len(query_files_for_timestep)}")
            
            frequencies = frequencies_by_timestep.get(timestep_name, [1.0] * len(query_files_for_timestep))
            
            # 頻度リストの長さを調整
            if len(frequencies) < len(query_files_for_timestep):
                frequencies.extend([0.0] * (len(query_files_for_timestep) - len(frequencies)))
            elif len(frequencies) > len(query_files_for_timestep):
                frequencies = frequencies[:len(query_files_for_timestep)]
            
            query_results = self._execute_queries_with_frequency(
                query_files_for_timestep,
                frequencies,
                timeout_minutes,
                verbose,
                ease_mode
            )
            
            total_query_time += query_results['total_time']
            
            if ease_mode:
                timestep_elapsed = migration_time + query_results['total_time']
            else:
                timestep_elapsed = time.time() - timestep_start
            
            # タイムステップごとの結果を保存
            timestep_result = {
                'timestep': timestep_name,
                'timestep_index': t_idx,
                'migration': {
                    'success': migration_success,
                    'time': round(migration_time, 5),
                    'error': migration_error,
                    'sql_file': str(migration_sql_file) if 'migration_sql_file' in locals() else None
                },
                'queries': query_results,
                'total_time': round(timestep_elapsed, 5),
            }
            
            timestep_results.append(timestep_result)
            
            # サマリー表示
            logger.info(f"\nTimestep {timestep_name} Summary:")
            logger.info(f"  Migration time: {migration_time:.2f}s")
            logger.info(f"  Query executions: {query_results['total_executions']}")
            logger.info(f"  Query time: {query_results['total_time']:.2f}s")
            logger.info(f"  Total timestep time: {timestep_elapsed:.2f}s")
        
        if ease_mode:
            benchmark_elapsed = total_migration_time + total_query_time
        else:
            benchmark_elapsed = time.time() - benchmark_start
        
        # 全体サマリー
        logger.info(f"\n{'='*60}")
        logger.info("Benchmark Summary:")
        logger.info(f"  Total timesteps: {len(timesteps)}")
        logger.info(f"  Total migration time: {total_migration_time:.2f}s")
        logger.info(f"  Total query time: {total_query_time:.2f}s")
        logger.info(f"  Total benchmark time: {benchmark_elapsed:.2f}s")
        logger.info(f"{'='*60}")
        
        return {
            'timesteps': timesteps,
            'timestep_results': timestep_results,
            'summary': {
                'total_timesteps': len(timesteps),
                'total_migration_time': round(total_migration_time, 5),
                'total_query_time': round(total_query_time, 5),
                'total_benchmark_time': round(benchmark_elapsed, 2),
            }
        }
    
    def execute_baseline_benchmark(
        self,
        query_files: List[Path],
        frequencies_by_timestep: Dict[str, List[float]],
        timesteps: List[str],
        timeout_minutes: int = 30,
        verbose: bool = False,
        ease_mode: bool = False
    ) -> Dict:
        """ベースライン: MVなしでクエリを実行
        
        Args:
            query_files: クエリファイルのリスト
            frequencies_by_timestep: タイムステップごとの頻度情報
            timesteps: タイムステップのリスト
            timeout_minutes: タイムアウト時間（分）
            verbose: 詳細ログを出力するか
            ease_mode: 簡易モード（各クエリを1回実行し、時間に頻度を掛ける）
            
        Returns:
            ベンチマーク結果の辞書
        """
        print("DEBUG: execute_baseline_benchmark called")
        logger.info("Starting baseline benchmark execution (no materialized views)")
        
        benchmark_start = time.time()
        timestep_results = []
        total_query_time = 0.0
        
        # 各タイムステップを順に実行（MVなし）
        for t_idx, timestep_name in enumerate(timesteps):
            logger.info(f"\n{'='*60}")
            logger.info(f"Timestep {t_idx}: {timestep_name}")
            logger.info(f"{'='*60}")
            
            timestep_start = time.time()
            
            logger.info(f"Executing queries for timestep {timestep_name} (no MVs)...")
            
            frequencies = frequencies_by_timestep.get(timestep_name, [1.0] * len(query_files))
            
            # 頻度リストの長さを調整
            if len(frequencies) < len(query_files):
                frequencies.extend([0.0] * (len(query_files) - len(frequencies)))
            elif len(frequencies) > len(query_files):
                frequencies = frequencies[:len(query_files)]
            
            query_results = self._execute_queries_with_frequency(
                query_files,
                frequencies,
                timeout_minutes,
                verbose,
                ease_mode
            )
            
            total_query_time += query_results['total_time']
            
            if ease_mode:
                timestep_elapsed = query_results['total_time']
            else:
                timestep_elapsed = time.time() - timestep_start
            
            timestep_result = {
                'timestep': timestep_name,
                'timestep_index': t_idx,
                'queries': query_results,
                'total_time': round(timestep_elapsed, 5),
            }
            
            timestep_results.append(timestep_result)
            
            logger.info(f"\nTimestep {timestep_name} Summary:")
            logger.info(f"  Query executions: {query_results['total_executions']}")
            logger.info(f"  Query time: {query_results['total_time']:.2f}s")
            logger.info(f"  Total timestep time: {timestep_elapsed:.2f}s")
        
        if ease_mode:
            benchmark_elapsed = total_query_time
        else:
            benchmark_elapsed = time.time() - benchmark_start
        
        logger.info(f"\n{'='*60}")
        logger.info("Baseline Benchmark Summary:")
        logger.info(f"  Total timesteps: {len(timesteps)}")
        logger.info(f"  Total query time: {total_query_time:.2f}s")
        logger.info(f"  Total benchmark time: {benchmark_elapsed:.2f}s")
        logger.info(f"{'='*60}")
        
        return {
            'mode': 'baseline',
            'timesteps': timesteps,
            'timestep_results': timestep_results,
            'summary': {
                'total_timesteps': len(timesteps),
                'total_query_time': round(total_query_time, 5),
                'total_benchmark_time': round(benchmark_elapsed, 2),
            }
        }
    
    def execute_static_mv_benchmark(
        self,
        optimization_result: Dict,
        migration_sql_dir: Path,
        rewritten_queries_base_dir: Path,
        frequencies_by_timestep: Dict[str, List[float]],
        timesteps: List[str] = None,
        timeout_minutes: int = 30,
        verbose: bool = False,
        static_algorithm: str = 'normal',
        ease_mode: bool = False
    ) -> Dict:
        """静的MV: 最初のタイムステップでMVを作成し、マイグレーションなしで実行
        
        Args:
            optimization_result: 最適化結果（migration_analysis生む）
            migration_sql_dir: マイグレーションSQLが格納されているディレクトリ
            rewritten_queries_base_dir: 書き換えられたクエリのベースディレクトリ（例: jobs/）
            frequencies_by_timestep: タイムステップごとの頻度情報
            timeout_minutes: タイムアウト時間（分）
            verbose: 詳細ログを出力するか
            static_algorithm: 使用するアルゴリズム ('normal' or 'bigsubs')
            ease_mode: 簡易モード（各クエリを1回実行し、時間に頻度を掛ける）
            
        Returns:
            ベンチマーク結果の辞書
        """
        print("DEBUG: execute_static_mv_benchmark called")
        logger.info("Starting static MV benchmark execution (initial MVs only, no migration)")
        
        migration_analysis = optimization_result.get('migration_analysis', [])
        # Staticモードの場合はmigration_analysisがない場合がある（純粋な静的最適化）
        is_pure_static = 'migration_analysis' not in optimization_result and 'selected_mvs' in optimization_result
        
        timesteps = optimization_result.get('timesteps', [])
        # 純粋な静的最適化の場合、timestepsが含まれていない可能性があるため、frequencies_by_timestepから取得
        if not timesteps and frequencies_by_timestep:
            timesteps = sorted(frequencies_by_timestep.keys(), key=lambda x: int(x))
        
        if not migration_analysis and not is_pure_static:
            logger.error("No migration_analysis found in optimization result")
            return {'error': 'No migration_analysis found'}
        
        benchmark_start = time.time()
        timestep_results = []
        initial_mv_creation_time = 0.0
        total_query_time = 0.0
        
        # 最初のタイムステップでMVを作成
        logger.info(f"\n{'='*60}")
        logger.info("Creating initial MVs (timestep 0)")
        logger.info(f"{'='*60}")
        
        if is_pure_static:
            # 純粋な静的最適化の場合、アルゴリズムに応じてSQLファイルを選択
            if static_algorithm == 'bigsubs':
                migration_sql_file = migration_sql_dir / "static_bigsubs_initial_mvs.sql"
            else:
                migration_sql_file = migration_sql_dir / "static_initial_mvs.sql"
        else:
            # 従来の時間依存最適化の最初のステップを使用する場合
            migration_sql_file = migration_sql_dir / f"timestep_0_{timesteps[0]}.sql"
        
        if migration_sql_file.exists():
            logger.info(f"Creating initial MVs from {migration_sql_file.name}...")
            success, elapsed, error = self._execute_sql_file(migration_sql_file, 0)
            initial_mv_creation_time = elapsed
            
            if success:
                logger.info(f"  ✓ Initial MVs created ({elapsed:.2f}s)")
            else:
                logger.error(f"  ✗ Failed to create initial MVs: {error}")
                return {'error': f'Failed to create initial MVs: {error}'}
        else:
            logger.warning(f"No initial migration SQL found: {migration_sql_file}")
        
        # 最初のタイムステップの書き換えられたクエリを取得（全タイムステップで使用）
        # Static モードではMVが変わらないため、クエリも変わらない
        if is_pure_static:
            # 純粋な静的最適化の場合、rewritten_queries_base_dir がそのままクエリディレクトリ
            initial_rewritten_queries_dir = rewritten_queries_base_dir
        else:
            initial_rewritten_queries_dir = rewritten_queries_base_dir / f"timestep_0_{timesteps[0]}"
        
        if not initial_rewritten_queries_dir.exists():
            logger.error(f"Initial rewritten queries directory not found: {initial_rewritten_queries_dir}")
            return {'error': f'Initial rewritten queries directory not found'}
        
        # Helper for natural sort (to match io_loaders.py behavior)
        import re
        def natural_sort_key(s):
            return [int(text) if text.isdigit() else text.lower() for text in re.split("([0-9]+)", str(s))]
        
        static_query_files = sorted(initial_rewritten_queries_dir.glob("*.sql"), key=lambda x: natural_sort_key(x.name))
        
        if not static_query_files:
            logger.error(f"No query files found in {initial_rewritten_queries_dir}")
            return {'error': f'No initial query files found'}
        
        logger.info(f"Loaded {len(static_query_files)} queries from: {initial_rewritten_queries_dir}")
        logger.info(f"These queries will be used for all timesteps (MVs do not change)")
        
        # 各タイムステップでクエリを実行（同じMVとクエリのまま）
        for t_idx, timestep_name in enumerate(timesteps):
            logger.info(f"\n{'='*60}")
            logger.info(f"Timestep {t_idx}: {timestep_name} (using initial MVs and queries)")
            logger.info(f"{'='*60}")
            
            timestep_start = time.time()
            
            logger.info(f"Executing queries for timestep {timestep_name}...")
            logger.info(f"  Using initial rewritten queries (timestep 0)")
            logger.info(f"  Query count: {len(static_query_files)}")
            
            frequencies = frequencies_by_timestep.get(timestep_name, [1.0] * len(static_query_files))
            
            # 頻度リストの長さを調整
            if len(frequencies) < len(static_query_files):
                frequencies.extend([0.0] * (len(static_query_files) - len(frequencies)))
            elif len(frequencies) > len(static_query_files):
                frequencies = frequencies[:len(static_query_files)]
            
            query_results = self._execute_queries_with_frequency(
                static_query_files,  # 常に最初のタイムステップのクエリを使用
                frequencies,
                timeout_minutes,
                verbose,
                ease_mode
            )
            
            total_query_time += query_results['total_time']
            
            if ease_mode:
                timestep_elapsed = query_results['total_time']
            else:
                timestep_elapsed = time.time() - timestep_start
            
            timestep_result = {
                'timestep': timestep_name,
                'timestep_index': t_idx,
                'queries': query_results,
                'total_time': round(timestep_elapsed, 5),
            }
            
            timestep_results.append(timestep_result)
            
            logger.info(f"\nTimestep {timestep_name} Summary:")
            logger.info(f"  Query executions: {query_results['total_executions']}")
            logger.info(f"  Query time: {query_results['total_time']:.2f}s")
            logger.info(f"  Total timestep time: {timestep_elapsed:.2f}s")
        
        if ease_mode:
            benchmark_elapsed = total_query_time + initial_mv_creation_time
        else:
            benchmark_elapsed = time.time() - benchmark_start
        
        logger.info(f"\n{'='*60}")
        logger.info("Static MV Benchmark Summary:")
        logger.info(f"  Total timesteps: {len(timesteps)}")
        logger.info(f"  Initial MV creation time: {initial_mv_creation_time:.2f}s")
        logger.info(f"  Total query time: {total_query_time:.2f}s")
        logger.info(f"  Total benchmark time: {benchmark_elapsed:.2f}s")
        logger.info(f"{'='*60}")
        
        return {
            'mode': 'static',
            'timesteps': timesteps,
            'initial_mv_creation_time': round(initial_mv_creation_time, 5),
            'timestep_results': timestep_results,
            'summary': {
                'total_timesteps': len(timesteps),
                'initial_mv_creation_time': round(initial_mv_creation_time, 5),
                'total_query_time': round(total_query_time, 5),
                'total_benchmark_time': round(benchmark_elapsed, 2),
            }
        }
    
    def close(self):
        """データベース接続をクローズ"""
        if self.connection and not self.connection.closed:
            self.connection.close()
            logger.debug("Database connection closed")
