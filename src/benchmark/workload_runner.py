"""ワークロード実行モジュール

run_redbench_workload.py と run_experiment.py から共通で使用される
ベンチマーク実行ロジックを提供する。
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional

from config.settings import Settings
from src.benchmark import QueryExecutor
from src.utils.legacy import get_red_queries_sql, natural_sort_key


def get_query_dir(algorithm: str, sql_base_dir: Path, rewritten_base_dir: Path):
    """アルゴリズムに応じたクエリディレクトリを返す
    
    Args:
        algorithm: アルゴリズム名 (none, normal, bigsubs, etc.)
        sql_base_dir: オリジナルSQLのベースディレクトリ
        rewritten_base_dir: 書き換え済みSQLのベースディレクトリ
        
    Returns:
        (query_dir, use_job_subdir): クエリディレクトリと、job/ サブディレクトリを使うかどうか
    """
    algo_dir_map = {
        "normal": "normal",
        "bigsubs": "bigsubs",
        "utility_capacity": "utility_capacity",
        "utility": "utility",
        "frequency": "frequency",
        "none": "none",
        "topku": "topku",
        "topke": "topke",
    }
    rewrite_dir = rewritten_base_dir / algo_dir_map.get(algorithm, algorithm)
    if rewrite_dir.exists() and any(rewrite_dir.glob("*.sql")):
        return rewrite_dir, False
    # フォールバック: オリジナル JOB クエリ
    return sql_base_dir, True


def run_simple_benchmark(
    executor: QueryExecutor,
    algorithm: str,
    query_dir: Path,
    timeout_minutes: int,
    verbose: bool,
    warmup: bool,
    logger: logging.Logger,
    limit: int = None
) -> dict:
    """シンプルなベンチマーク実行（各クエリ1回）
    
    job, ceb ワークロード用。書き換え済みディレクトリの全クエリを1回ずつ実行。
    
    Args:
        executor: QueryExecutor インスタンス
        algorithm: アルゴリズム名
        query_dir: クエリディレクトリ
        timeout_minutes: タイムアウト（分）
        verbose: 詳細出力
        warmup: ウォームアップ実行
        logger: ロガー
        limit: 実行する最大クエリ数（None = 全件）
        
    Returns:
        ベンチマーク結果の辞書
    """
    logger.info(f"Running simple benchmark (each query once)...")
    logger.info(f"Query directory: {query_dir}")
    
    # クエリファイルを収集
    query_files = sorted(query_dir.glob("*.sql"), key=lambda f: natural_sort_key(f.name))
    if limit is not None:
        query_files = query_files[:limit]
        logger.info(f"Query limit applied: {len(query_files)} queries")
    
    if not query_files:
        logger.error(f"No SQL files found in {query_dir}")
        return None
    
    logger.info(f"Found {len(query_files)} queries")
    
    # ウォームアップ（テーブルスキャン方式）
    warmup_time = 0.0
    if warmup:
        warmup_time = executor._warmup_tables()
    
    # ベンチマーク実行
    results = []
    successful = 0
    failed = 0
    total_time = 0
    
    benchmark_start = time.time()
    total_queries = len(query_files)
    
    logger.info(f"Starting benchmark execution ({total_queries} queries)...")
    
    for idx, query_file in enumerate(query_files, 1):
        # Always log progress for dashboard tracking
        progress_pct = (idx / total_queries) * 100
        logger.info(f"Query {idx}/{total_queries} ({progress_pct:.1f}%): {query_file.name}")
        
        result = executor.execute_query_file(query_file, timeout_minutes)
        total_time += result['time']
        
        if result['success']:
            successful += 1
        else:
            failed += 1
            if verbose:
                logger.warning(f"  ✗ Failed: {result['error'][:50]}...")
        
        results.append({
            'query_id': query_file.stem,
            'query_file': str(query_file),
            'success': result['success'],
            'execution_time': round(result['time'], 2),
            'error': result['error']
        })
    
    benchmark_elapsed = time.time() - benchmark_start
    
    logger.info(f"\nSimple Benchmark Summary:")
    logger.info(f"  Algorithm: {algorithm}")
    logger.info(f"  Total queries: {len(query_files)}")
    logger.info(f"  Successful: {successful}")
    logger.info(f"  Failed: {failed}")
    logger.info(f"  Total time: {total_time:.2f}s")
    logger.info(f"  Avg time: {total_time/len(query_files):.4f}s")
    
    return {
        'mode': 'simple',
        'workload_type': 'simple',
        'algorithm': algorithm,
        'total_queries': len(query_files),
        'successful': successful,
        'failed': failed,
        'total_time': round(total_time, 2),
        'benchmark_elapsed': round(benchmark_elapsed, 2),
        'avg_time_per_query': round(total_time / len(query_files), 4) if query_files else 0,
        'warmup_enabled': warmup,
        'warmup_time': round(warmup_time, 2) if warmup else 0,
        'queries': results
    }


def run_redbench_by_group(
    executor: QueryExecutor,
    algorithm: str,
    workloads_dir: Path,
    query_dir: Path,
    use_job_subdir: bool,
    timeout_minutes: int,
    verbose: bool,
    warmup: bool,
    logger: logging.Logger,
    job_only: bool = False,
    ceb_only: bool = False
) -> dict:
    """変動性バケット（グループ）ごとにクエリを実行・計測
    
    redbench, redbench-job, redbench-ceb ワークロード用。
    
    Args:
        executor: QueryExecutor インスタンス
        algorithm: アルゴリズム名
        workloads_dir: ワークロードCSVのディレクトリ
        query_dir: クエリディレクトリ
        use_job_subdir: job/ サブディレクトリを使うか
        timeout_minutes: タイムアウト（分）
        verbose: 詳細出力
        warmup: ウォームアップ実行
        logger: ロガー
        job_only: JOBクエリのみ実行
        ceb_only: CEBクエリのみ実行
        
    Returns:
        ベンチマーク結果の辞書
    """
    workload_type = "redbench"
    if job_only:
        workload_type = "redbench-job"
    elif ceb_only:
        workload_type = "redbench-ceb"
    
    logger.info(f"Running RedBench benchmark by variability group...")
    logger.info(f"Workload type: {workload_type}")
    logger.info(f"Query directory: {query_dir}")
    
    group_results = {}
    all_results = []
    total_time = 0
    total_successful = 0
    total_failed = 0
    total_queries = 0

    # ── ウォームアップフェーズ ─────────────────────────────────────────────
    # 1. pg_prewarm 'read' で全 IMDB テーブルを OS キャッシュにロード
    # 2. 全クエリを 1 回ドライラン（結果は計測に含めない）
    # これにより実験間の OS キャッシュ差異を排除し、再現性の高い計測を実現する。
    # 特に 30a.sql は cast_info/movie_info のランダムアクセスを多用するため、
    # 同パターンのドライランがなければキャッシュコールドで 4× 遅くなる。
    warmup_total_time = 0.0
    if warmup:
        warmup_total_time += executor._warmup_tables()

        # 全クエリを収集してドライラン
        all_query_files_for_warmup = []
        seen_queries = set()
        for subdir_w in sorted([x[0] for x in os.walk(str(workloads_dir)) if x[0] != str(workloads_dir)]):
            for fname in sorted(os.listdir(subdir_w)):
                if not fname.endswith(".csv") or fname == "stats.csv":
                    continue
                with open(os.path.join(subdir_w, fname)) as f:
                    lines = f.readlines()[1:]
                for line in lines:
                    qname = line.split(",")[0].split("/")[-1]
                    if not qname.endswith(".sql"):
                        continue
                    is_job = qname[0].isdigit()
                    if job_only and not is_job:
                        continue
                    if ceb_only and is_job:
                        continue
                    if qname in seen_queries:
                        continue
                    seen_queries.add(qname)
                    qpath = (query_dir / "job" / qname) if use_job_subdir else (query_dir / qname)
                    if qpath.exists():
                        all_query_files_for_warmup.append(qpath)

        if all_query_files_for_warmup:
            logger.info(f"[Warmup] 全クエリのドライラン実行 ({len(all_query_files_for_warmup)} distinct queries)...")
            warmup_total_time += executor._warmup_queries(all_query_files_for_warmup, verbose=False)

    # 各グループを処理
    for group_idx, subdir in enumerate(sorted([x[0] for x in os.walk(str(workloads_dir)) if x[0] != str(workloads_dir)])):
        group_name = Path(subdir).name
        group_queries = []
        
        # このグループのクエリを収集
        for filename in sorted(os.listdir(subdir)):
            if not filename.endswith(".csv") or filename == "stats.csv":
                continue
            with open(os.path.join(subdir, filename)) as csv_file:
                workload = csv_file.readlines()[1:]
            for line in workload:
                query_name = line.split(",")[0].split("/")[-1]
                if query_name.endswith(".sql"):
                    # JOBクエリかCEBクエリか判定
                    is_job_query = query_name.startswith(('1', '2', '3', '4', '5', '6', '7', '8', '9')) or \
                                   query_name[0].isdigit()
                    
                    # フィルタリング
                    if job_only and not is_job_query:
                        continue
                    if ceb_only and is_job_query:
                        continue
                    
                    if use_job_subdir:
                        query_path = query_dir / "job" / query_name
                    else:
                        query_path = query_dir / query_name
                    if query_path.exists():
                        group_queries.append(query_path)
        
        if not group_queries:
            continue
        
        logger.info(f"\n{'='*50}")
        logger.info(f"Group: {group_name} ({len(group_queries)} queries)")
        logger.info(f"{'='*50}")
        
        warmup_time = warmup_total_time if group_idx == 0 else 0.0
        
        # グループのベンチマーク実行
        group_total_time = 0
        group_successful = 0
        group_failed = 0
        group_query_results = []
        
        benchmark_start = time.time()
        
        for idx, query_file in enumerate(group_queries, 1):
            if verbose or idx == 1 or idx == len(group_queries) or idx % max(1, len(group_queries) // 5) == 0:
                logger.info(f"  [{idx}/{len(group_queries)}] {query_file.name}")
            
            result = executor.execute_query_file(query_file, timeout_minutes)
            group_total_time += result['time']
            
            if result['success']:
                group_successful += 1
            else:
                group_failed += 1
                if verbose:
                    logger.warning(f"    ✗ Failed: {result['error'][:50]}...")
            
            group_query_results.append({
                'query_id': query_file.stem,
                'query_file': str(query_file),
                'group': group_name,
                'success': result['success'],
                'execution_time': round(result['time'], 2),
                'error': result['error']
            })
        
        benchmark_elapsed = time.time() - benchmark_start
        
        # グループの結果を保存
        group_results[group_name] = {
            'total_queries': len(group_queries),
            'successful': group_successful,
            'failed': group_failed,
            'total_time': round(group_total_time, 2),
            'avg_time': round(group_total_time / len(group_queries), 4) if group_queries else 0,
            'warmup_time': round(warmup_time, 2),
            'benchmark_elapsed': round(benchmark_elapsed, 2)
        }
        
        all_results.extend(group_query_results)
        total_time += group_total_time
        total_successful += group_successful
        total_failed += group_failed
        total_queries += len(group_queries)
        
        logger.info(f"  Group {group_name}: {group_total_time:.2f}s total, {group_total_time/len(group_queries):.4f}s avg")
    
    # 全体サマリー
    logger.info(f"\n{'='*60}")
    logger.info("Overall Summary by Group:")
    logger.info(f"{'='*60}")
    for group_name, stats in sorted(group_results.items()):
        logger.info(f"  {group_name}: {stats['total_queries']} queries, {stats['total_time']:.2f}s total, {stats['avg_time']:.4f}s avg")
    logger.info(f"{'='*60}")
    if total_queries > 0:
        logger.info(f"Total: {total_queries} queries, {total_time:.2f}s, {total_time/total_queries:.4f}s avg")
    else:
        logger.warning("No queries executed")
    
    return {
        'mode': 'group',
        'workload_type': workload_type,
        'algorithm': algorithm,
        'total_queries': total_queries,
        'successful': total_successful,
        'failed': total_failed,
        'total_time': round(total_time, 2),
        'avg_time_per_query': round(total_time / total_queries, 4) if total_queries else 0,
        'warmup_enabled': warmup,
        'group_results': group_results,
        'queries': all_results
    }


def run_redbench_job_unique(
    executor: QueryExecutor,
    algorithm: str,
    workloads_dir: Path,
    query_dir: Path,
    use_job_subdir: bool,
    timeout_minutes: int,
    verbose: bool,
    warmup: bool,
    logger: logging.Logger
) -> dict:
    """JOBクエリのみを実行（ユニーク、ソート済み）
    
    Args:
        executor: QueryExecutor インスタンス
        algorithm: アルゴリズム名
        workloads_dir: ワークロードCSVのディレクトリ
        query_dir: クエリディレクトリ
        use_job_subdir: job/ サブディレクトリを使うか
        timeout_minutes: タイムアウト（分）
        verbose: 詳細出力
        warmup: ウォームアップ実行
        logger: ロガー
        
    Returns:
        ベンチマーク結果の辞書
    """
    logger.info("Running benchmark with unique JOB queries (sorted)...")
    
    if use_job_subdir:
        files, query_count = get_red_queries_sql(
            str(query_dir),
            str(workloads_dir),
            get_ceb=False
        )
    else:
        job_query_names = set()
        query_count = {}
        for subdir in sorted([x[0] for x in os.walk(str(workloads_dir)) if x[0] != str(workloads_dir)]):
            for filename in os.listdir(subdir):
                if not filename.endswith(".csv") or filename == "stats.csv":
                    continue
                with open(os.path.join(subdir, filename)) as csv_file:
                    workload = csv_file.readlines()[1:]
                for line in workload:
                    query_name = line.split(",")[0].split("/")[-1]
                    if query_name.endswith(".sql"):
                        query_path = str(query_dir / query_name)
                        if os.path.exists(query_path):
                            job_query_names.add(query_path)
                            if query_path not in query_count:
                                query_count[query_path] = 1
                            else:
                                query_count[query_path] += 1
        files = list(job_query_names)
    
    if not files:
        logger.error("No JOB queries found in workload")
        return None
    
    files = sorted(files, key=lambda f: natural_sort_key(Path(f).name))
    query_files = [Path(f) for f in files]
    
    logger.info(f"Found {len(query_files)} unique JOB queries")
    total_occurrences = sum(query_count.values())
    logger.info(f"Total occurrences in workload: {total_occurrences}")
    
    # ウォームアップ（テーブルスキャン方式）
    warmup_time = 0.0
    if warmup:
        warmup_time = executor._warmup_tables()
    
    # ベンチマーク実行
    results = []
    successful = 0
    failed = 0
    total_time = 0
    
    benchmark_start = time.time()
    
    for idx, query_file in enumerate(query_files, 1):
        occurrences = query_count.get(str(query_file), 1)
        
        if verbose or idx == 1 or idx == len(query_files) or idx % max(1, len(query_files) // 10) == 0:
            logger.info(f"[{idx}/{len(query_files)}] {query_file.name} (freq={occurrences})")
        
        result = executor.execute_query_file(query_file, timeout_minutes)
        total_time += result['time']
        
        if result['success']:
            successful += 1
        else:
            failed += 1
        
        results.append({
            'query_id': query_file.stem,
            'query_file': str(query_file),
            'frequency': occurrences,
            'success': result['success'],
            'execution_time': round(result['time'], 2),
            'error': result['error']
        })
    
    benchmark_elapsed = time.time() - benchmark_start
    
    logger.info(f"\nJOB Query Summary:")
    logger.info(f"  Algorithm: {algorithm}")
    logger.info(f"  Total queries: {len(query_files)}")
    logger.info(f"  Total time: {total_time:.2f}s")
    logger.info(f"  Avg time: {total_time/len(query_files):.2f}s")
    
    return {
        'mode': 'job',
        'workload_type': 'redbench-job',
        'algorithm': algorithm,
        'total_queries': len(query_files),
        'total_workload_occurrences': total_occurrences,
        'successful': successful,
        'failed': failed,
        'total_time': round(total_time, 2),
        'benchmark_elapsed': round(benchmark_elapsed, 2),
        'avg_time_per_query': round(total_time / len(query_files), 2) if query_files else 0,
        'warmup_enabled': warmup,
        'warmup_time': round(warmup_time, 2) if warmup else 0,
        'queries': results
    }


def run_workload_benchmark(
    workload_type: str,
    algorithm: str,
    settings: Settings,
    output_dir: Optional[Path] = None,
    verbose: bool = False,
    warmup: bool = True,
    timeout_minutes: int = 30,
) -> dict:
    """ワークロードに応じたベンチマークを実行
    
    Args:
        workload_type: ワークロードタイプ
            - "job": 全113 JOBクエリ（シンプル実行）
            - "ceb": 全CEBクエリ（シンプル実行）
            - "redbench": RedBench全体（グループ別実行）
            - "redbench-job": RedBench JOBクエリのみ（グループ別実行）
            - "redbench-ceb": RedBench CEBクエリのみ（グループ別実行）
        algorithm: アルゴリズム名 (none, normal, bigsubs, etc.)
        settings: Settings オブジェクト
        output_dir: 出力ディレクトリ
        verbose: 詳細出力
        warmup: ウォームアップ実行
        
    Returns:
        ベンチマーク結果の辞書
    """
    logger = logging.getLogger(__name__)
    
    # パス設定
    project_root = Path(__file__).parent.parent.parent
    workloads_dir = project_root / "Output" / "RED_WORKLOADS"
    sql_base_dir = project_root / "dataset" / "RED_SQL"
    # Use settings-provided output dir if available, else default
    _output_base = Path(output_dir) if output_dir else project_root / "Output"
    rewritten_base_dir = _output_base / "query_rewrite" / "re_sql"
    redbench_base = project_root / "dataset" / "redbench"
    
    # ワークロードディレクトリが存在しない場合は作成
    if not workloads_dir.exists():
        logger.info(f"Creating workloads directory: {workloads_dir}")
        import shutil
        shutil.copytree(redbench_base / "workloads", workloads_dir)
    
    # QueryExecutorを初期化
    executor = QueryExecutor(settings)
    
    logger.info("=" * 60)
    logger.info("Workload Benchmark Execution")
    logger.info("=" * 60)
    logger.info(f"Workload Type: {workload_type}")
    logger.info(f"Algorithm: {algorithm}")
    logger.info(f"Warmup: {'Enabled' if warmup else 'Disabled'}")
    logger.info("=" * 60)
    
    # クエリディレクトリを取得
    query_dir, use_job_subdir = get_query_dir(algorithm, sql_base_dir, rewritten_base_dir)
    
    if not query_dir.exists():
        logger.error(f"Query directory not found: {query_dir}")
        return None
    
    logger.info(f"Query directory: {query_dir}")
    
    start_time = time.time()
    results = None
    
    # ワークロードタイプに応じて実行方法を選択
    if workload_type in ["job", "ceb"]:
        # シンプル実行: 各クエリ1回
        # "none" algorithm uses original SQL files under job/ or ceb/ subdirectory
        actual_query_dir = query_dir
        if use_job_subdir:
            subdir = "job" if workload_type == "job" else "ceb"
            actual_query_dir = query_dir / subdir
        results = run_simple_benchmark(
            executor, algorithm, actual_query_dir,
            timeout_minutes=timeout_minutes, verbose=verbose, warmup=warmup, logger=logger
        )
    elif workload_type.startswith("ceb-"):
        # CEB template-based execution (e.g., ceb-1a, ceb-2a)
        # Extract template from workload_type (e.g., "1a" from "ceb-1a")
        ceb_template = workload_type[4:]  # Remove "ceb-" prefix
        ceb_limit = getattr(settings.benchmark, 'ceb_limit', None)

        # For rewritten queries (non-"none" algorithm), queries are stored directly in algorithm folder
        # For original queries ("none" algorithm), use ceb/template subdirectory
        if algorithm == "none":
            ceb_query_dir = query_dir / "ceb" / ceb_template
        else:
            # Rewritten queries are stored directly in the algorithm directory
            ceb_query_dir = query_dir

        if not ceb_query_dir.exists():
            logger.error(f"CEB query directory not found: {ceb_query_dir}")
            return None

        logger.info(f"Running CEB {ceb_template} queries from: {ceb_query_dir}")
        if ceb_limit is not None:
            logger.info(f"CEB benchmark limit: {ceb_limit} queries")
        results = run_simple_benchmark(
            executor, algorithm, ceb_query_dir,
            timeout_minutes=timeout_minutes, verbose=verbose, warmup=warmup, logger=logger,
            limit=ceb_limit
        )
    elif workload_type == "redbench":
        # RedBench全体: グループ別実行（JOB + CEB）
        results = run_redbench_by_group(
            executor, algorithm, workloads_dir, query_dir, use_job_subdir,
            timeout_minutes=timeout_minutes, verbose=verbose, warmup=warmup, logger=logger,
            job_only=False, ceb_only=False
        )
    elif workload_type == "redbench-job":
        # RedBench JOB: グループ別実行（JOBのみ）
        results = run_redbench_by_group(
            executor, algorithm, workloads_dir, query_dir, use_job_subdir,
            timeout_minutes=timeout_minutes, verbose=verbose, warmup=warmup, logger=logger,
            job_only=True, ceb_only=False
        )
    elif workload_type == "redbench-ceb":
        # RedBench CEB: グループ別実行（CEBのみ）
        results = run_redbench_by_group(
            executor, algorithm, workloads_dir, query_dir, use_job_subdir,
            timeout_minutes=timeout_minutes, verbose=verbose, warmup=warmup, logger=logger,
            job_only=False, ceb_only=True
        )
    else:
        logger.error(f"Unknown workload type: {workload_type}")
        return None
    
    if results is None:
        logger.error("Benchmark execution failed")
        return None
    
    elapsed = time.time() - start_time
    
    # メタデータを追加
    results['metadata'] = {
        'workload_type': workload_type,
        'algorithm': algorithm,
        'total_elapsed': round(elapsed, 2),
        'timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    return results
