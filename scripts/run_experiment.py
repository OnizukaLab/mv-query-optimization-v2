#!/usr/bin/env python3
"""実験実行メインスクリプト

src/ 配下のリファクタリング済みコードを使用した実験実行スクリプト
"""
import argparse
import json
import os
import pickle
import sys
import time
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# src/ 配下のモジュールをインポート
from src.core.query_manager import QueryManager
from src.core.query_parser import QueryParser
from src.optimization.factory import OptimizerFactory
from src.database.connection import DatabaseConnection
from src.utils.logging_utils import setup_logging, get_logger
from src.utils import run_layout
from src.utils.run_layout import RunManifest, resolve_workload_files

# Initialize logger (will be properly configured in main())
logger = get_logger(__name__)


def _topological_sort_mvs(mvs: list, qm) -> list:
    """Sort MVs in topological order (dependencies first).
    
    Args:
        mvs: List of MaterializedView objects
        qm: QueryManager with node information
        
    Returns:
        Sorted list of MVs
    """
    from collections import defaultdict, deque
    
    # Build dependency graph
    mv_dict = {mv.node_id: mv for mv in mvs}
    in_degree = {node_id: 0 for node_id in mv_dict}
    graph = defaultdict(list)
    
    for node_id in mv_dict:
        if node_id.startswith('non_leaf_'):
            # Get children from non_leaf_nodes_map_r
            if node_id in qm.non_leaf_nodes_map_r:
                children = qm.non_leaf_nodes_map_r[node_id]
                for child_id in children:
                    if child_id in mv_dict:
                        # child_id depends on nothing (or other nodes)
                        # node_id depends on child_id
                        graph[child_id].append(node_id)
                        in_degree[node_id] += 1
    
    # Topological sort using Kahn's algorithm
    queue = deque([node_id for node_id in mv_dict if in_degree[node_id] == 0])
    sorted_node_ids = []
    
    while queue:
        node_id = queue.popleft()
        sorted_node_ids.append(node_id)
        
        for neighbor in graph[node_id]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    
    # Check for cycles
    if len(sorted_node_ids) != len(mv_dict):
        logger.warning(f"Circular dependency detected! Only {len(sorted_node_ids)}/{len(mv_dict)} nodes sorted")
        # Add remaining nodes at the end
        remaining = [node_id for node_id in mv_dict if node_id not in sorted_node_ids]
        sorted_node_ids.extend(remaining)
    
    # Convert back to MV objects
    return [mv_dict[node_id] for node_id in sorted_node_ids]


def parse_args():
    """コマンドライン引数解析"""
    parser = argparse.ArgumentParser(description="Run MV optimization experiment")

    parser.add_argument(
        "--algorithms",
        nargs="+",
        choices=["none", "normal", "bigsubs", "utility", "utility_capacity", "frequency"],
        default=["none", "normal", "bigsubs", "utility", "utility_capacity", "frequency"],
        help="Optimization algorithms to run",
    )

    parser.add_argument(
        "--output", type=str, default="Output",
        help="Output root. Results go to <output>/runs/<run-id>/, parse caches to <output>/artifacts/",
    )
    parser.add_argument(
        "--run-id", type=str, default=None,
        help="Run directory name under <output>/runs/ (default: <timestamp>_<workload>). "
             "Pass an existing id with --phases/--start-from to continue that run.",
    )

    # Legacy skip flags (deprecated, use --phases instead)
    parser.add_argument(
        "--skip-mv-creation", action="store_true", 
        help="(Deprecated) Skip MV creation in database. Use --phases instead."
    )
    parser.add_argument(
        "--skip-rewrite", action="store_true", 
        help="(Deprecated) Skip query rewriting. Use --phases instead."
    )
    parser.add_argument(
        "--skip-benchmark", action="store_true", 
        help="(Deprecated) Skip benchmark execution. Use --phases instead."
    )

    # New phase control options
    parser.add_argument(
        "--phases",
        nargs="+",
        choices=["query_parsing", "optimization", "sql_generation", "mv_creation", "query_rewriting", "benchmark"],
        help="Specify which phases to run (e.g., --phases query_parsing optimization sql_generation)"
    )
    
    parser.add_argument(
        "--start-from",
        choices=["query_parsing", "optimization", "sql_generation", "mv_creation", "query_rewriting", "benchmark"],
        help="Start execution from this phase (inclusive)"
    )
    
    parser.add_argument(
        "--end-at",
        choices=["query_parsing", "optimization", "sql_generation", "mv_creation", "query_rewriting", "benchmark"],
        help="End execution at this phase (inclusive)"
    )

    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    
    parser.add_argument(
        "--storage-limit", 
        type=int, 
        default=None,  # Will use config file value if not specified
        help="Storage limit for materialized views in bytes (overrides config file)"
    )
    
    parser.add_argument(
        "--insert-queries",
        type=int,
        default=None,  # Will use config file value if not specified
        help="Number of insert queries for maintenance cost calculation (overrides config file)"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration YAML file (overrides default)"
    )
    
    parser.add_argument(
        "--no-warmup",
        action="store_true",
        help="Disable cache warmup before benchmark (warmup is enabled by default)"
    )
    
    # Workload configuration
    parser.add_argument(
        "--workload-type",
        type=str,
        choices=["job", "ceb", "ceb-1a", "redbench", "redbench-job", "redbench-ceb"],
        default=None,  # Will use config file value if not specified
        help="""Workload type:
  job: All 113 JOB queries from dataset/RED_JSON/job/
  ceb: All CEB queries from dataset/RED_JSON/ (RedBench CEB)
  ceb-1a: All CEB 1a queries from dataset/RED_JSON/ceb/1a/
  redbench: Full RedBench workload (JOB + CEB mixed)
  redbench-job: Only JOB queries from RedBench (83 queries)
  redbench-ceb: Only CEB queries from RedBench"""
    )
    
    parser.add_argument(
        "--ceb-template",
        type=str,
        default="1a",
        help="CEB template to use when workload-type is ceb-1a (e.g., 1a, 2a, 3b). Default: 1a"
    )

    parser.add_argument(
        "--ceb-limit",
        type=int,
        default=None,
        help="Maximum number of CEB queries to load (None = all). Use to reduce memory usage for large templates like 1a (3000 queries)."
    )

    return parser.parse_args()


def setup_directories(output_dir: str) -> None:
    """必要なディレクトリを作成

    Args:
        output_dir: 出力ベースディレクトリ
    """
    os.makedirs(f"{output_dir}/query_rewrite", exist_ok=True)


def cleanup_mv_files() -> None:
    """データベース上の既存MVを全て削除"""
    logger.info("Dropping existing materialized views...")

    # データベースからMV削除（実験はrunごとに独立させるため、毎回全MVを落としてから始める）
    try:
        logger.info("Connecting to database to drop existing MVs...")
        from config.settings import Settings
        settings = Settings()
        db = DatabaseConnection(settings.database)
        
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                # 先に他のアクティブな接続を終了
                logger.info("Terminating active connections...")
                cur.execute("""
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = 'imdbload'
                      AND pid != pg_backend_pid()
                      AND state != 'idle'
                """)
                terminated = cur.fetchall()
                if terminated:
                    logger.info(f"Terminated {len(terminated)} active connections")
                
                # 既存のMVを削除
                cur.execute("""
                    SELECT matviewname FROM pg_matviews 
                    WHERE schemaname = 'public'
                """)
                mvs = cur.fetchall()
                logger.info(f"Found {len(mvs)} existing materialized views to drop")
                for idx, (mv_name,) in enumerate(mvs, 1):
                    logger.info(f"  [{idx}/{len(mvs)}] Dropping {mv_name}...")
                    cur.execute(f"DROP MATERIALIZED VIEW IF EXISTS {mv_name} CASCADE")
            conn.commit()
        logger.info(f"Successfully dropped {len(mvs)} materialized views")
    except Exception as e:
        logger.warning(f"Error cleaning up MVs: {e}")


def calibrate_bj_with_explain(qp, cache_dir: Path, settings, verbose: bool = False) -> None:
    """MV SQLに対してEXPLAINを実行し、b_j（MVサイズ推定）を補正する。

    現在のb_jはフルクエリコンテキスト下での Plan Rows × Plan Width を使っており、
    外側フィルタが乗った状態の推定値のため実際のMVサイズを大幅に過小評価する。
    各ノードのMV SQLを単独でEXPLAINすることで、外側フィルタなしの正確なサイズを推定する。

    結果は {cache_dir}/bj_calibrated.json（ワークロード単位のartifacts）にキャッシュし、2回目以降は再実行しない。
    """
    import json, re
    from pathlib import Path
    from src.rewrite.enhanced_mv_generator import EnhancedMVGenerator
    from src.database.connection import DatabaseConnection

    cache_path = Path(cache_dir) / "bj_calibrated.json"

    # キャッシュがあれば読み込んで適用
    if cache_path.exists():
        logger.info(f"Loading calibrated b_j from cache: {cache_path}")
        with open(cache_path) as f:
            calibrated = json.load(f)
        n_applied = 0
        for j, node_id in enumerate(qp.node_list):
            if node_id in calibrated:
                qp.b_j[j] = calibrated[node_id]
                qp.qm.subquery_sizes[node_id] = calibrated[node_id]
                n_applied += 1
        total_mb = sum(qp.b_j) / (1024 * 1024)
        logger.info(f"Applied calibrated sizes to {n_applied}/{len(qp.node_list)} nodes "
                    f"(total estimated: {total_mb:.1f} MB)")
        return

    logger.info(f"Calibrating b_j with EXPLAIN on MV SQLs ({len(qp.node_list)} nodes)...")
    logger.info("  (This runs once and is cached in bj_calibrated.json)")

    mv_generator = EnhancedMVGenerator(qp.qm, schema_provider=None)
    db = DatabaseConnection(settings.database)

    calibrated: dict[str, int] = {}
    n_improved = 0
    n_failed = 0
    n_zero = 0

    with db.get_connection() as conn:
        conn.set_session(autocommit=True)
        with conn.cursor() as cur:
            for j, node_id in enumerate(qp.node_list):
                if j % 200 == 0:
                    logger.info(f"  Progress: {j}/{len(qp.node_list)} nodes calibrated...")

                orig_size = qp.b_j[j]

                try:
                    create_sql, _ = mv_generator.generate_mv_and_index_sql(node_id)
                    if not create_sql:
                        calibrated[node_id] = orig_size
                        continue

                    # CREATE MATERIALIZED VIEW ... AS SELECT ... から SELECT 部分を抽出
                    m = re.search(r'\bAS\b\s*(SELECT\b.*)', create_sql, re.DOTALL | re.IGNORECASE)
                    if not m:
                        calibrated[node_id] = orig_size
                        n_failed += 1
                        continue
                    select_sql = m.group(1).strip().rstrip(';')

                    # MV SQL 単独で EXPLAIN
                    cur.execute(f"EXPLAIN (FORMAT JSON) {select_sql}")
                    plan_json = cur.fetchone()[0]
                    plan = plan_json[0]['Plan']
                    rows = plan.get('Plan Rows', 0)
                    width = plan.get('Plan Width', 0)
                    new_size = int(rows * width)

                    if new_size <= 0:
                        # EXPLAIN が 0 行推定 → 元の値を保持
                        calibrated[node_id] = orig_size
                        n_zero += 1
                        continue

                    calibrated[node_id] = new_size
                    qp.b_j[j] = new_size
                    qp.qm.subquery_sizes[node_id] = new_size

                    if new_size > orig_size:
                        n_improved += 1
                        if verbose:
                            logger.debug(f"  {node_id}: {orig_size/1024:.1f}KB → {new_size/1024/1024:.1f}MB "
                                         f"({new_size/max(orig_size,1):.0f}x)")

                except Exception as e:
                    calibrated[node_id] = orig_size
                    n_failed += 1
                    if verbose:
                        logger.debug(f"  {node_id}: EXPLAIN failed: {e}")

    # キャッシュ保存
    with open(cache_path, 'w') as f:
        json.dump(calibrated, f)

    total_mb = sum(qp.b_j) / (1024 * 1024)
    logger.info(f"✓ Calibration complete: {n_improved} nodes size-corrected upward, "
                f"{n_zero} zero-estimate kept, {n_failed} failed")
    logger.info(f"  Total estimated storage budget: {total_mb:.1f} MB "
                f"(vs storage limit {storage_limit_for_log(settings):.1f} MB)")


def storage_limit_for_log(settings) -> float:
    return settings.optimization.storage_limit_bytes / (1024 * 1024)


def run_ilp_optimization(
    ilp_type: str,
    output_dir: str,
    artifacts_dir: Path,
    workload_id: str,
    settings,  # Settings object with execution phase config
    storage_limit: int = 50 * 1024 * 1024,
    verbose: bool = False,
    warmup: bool = True,
) -> bool:
    """ILP最適化を実行（src/ モジュールのみ使用）

    Args:
        ilp_type: ILPアルゴリズムタイプ
        output_dir: このrunのディレクトリ（<Output>/runs/<run_id>）
        artifacts_dir: ワークロード単位のパースキャッシュ置き場
        workload_id: ワークロードの内容ハッシュ（キャッシュの有効性判定に使う）
        settings: Settings object with execution configuration
        storage_limit: ストレージ上限（バイト）
        verbose: 詳細出力
        warmup: ベンチマーク前にキャッシュウォームアップを行うか

    Returns:
        最後まで実行できたら True、途中で中断（エラー・MV未選択など）したら False
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Running ILP: {ilp_type}")
    logger.info(f"{'='*60}")
    
    # 各アルゴリズム実行前に既存のMVを全て削除
    logger.info("Cleaning up existing materialized views before starting...")
    cleanup_mv_files()

    # Display which phases will run
    phases_to_run = []
    for phase in ['query_parsing', 'optimization', 'sql_generation', 'mv_creation', 'query_rewriting', 'benchmark']:
        if settings.execution.should_run_phase(phase):
            phases_to_run.append(phase)
    logger.info(f"Phases to execute: {', '.join(phases_to_run)}")

    start_time = time.time()
    
    # アルゴリズム専用のディレクトリを作成
    algorithm_dir = Path(output_dir) / ilp_type
    algorithm_dir.mkdir(parents=True, exist_ok=True)
    
    # 各フェーズの実行時間を記録
    phase_times = {}

    if ilp_type == "none":
        logger.info("Running with 'none' algorithm (no materialized views - baseline benchmark)")
        # For 'none' algorithm, skip optimization, SQL generation, and MV creation
        # but keep query_parsing, query_rewriting, and benchmark based on user selection
        settings.execution.optimization = False
        settings.execution.sql_generation = False
        settings.execution.mv_creation = False
        # query_rewriting and benchmark phases remain as user specified

    try:
        from src.rewrite.query_rewriter import QueryRewriter
        from src.database.mv_manager import MaterializedViewManager
        
        # [1/6] クエリパース
        if settings.execution.should_run_phase('query_parsing'):
            logger.info("[1/6] Parsing queries...")
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            pickle_path = artifacts_dir / "qp_class.pkl"
            cache_metadata_path = artifacts_dir / "qp_class_metadata.json"
            current_insert_queries = settings.optimization.insert_queries

            # The directory is already keyed by workload id and insert_queries; the metadata is a
            # second check against a cache written by an older layout or a partial run.
            cache_valid = False
            if pickle_path.exists() and cache_metadata_path.exists():
                try:
                    with open(cache_metadata_path, 'r') as f:
                        metadata = json.load(f)
                    cache_valid = (
                        metadata.get('workload_id') == workload_id
                        and metadata.get('insert_queries') == current_insert_queries
                    )
                    if not cache_valid:
                        logger.info(f"Cache invalidated: metadata {metadata} does not match "
                                    f"workload_id={workload_id}, insert_queries={current_insert_queries}")
                except (OSError, json.JSONDecodeError) as e:
                    logger.warning(f"Failed to read cache metadata: {e}")

            if cache_valid:
                logger.info(f"Loading query parser from {pickle_path}")
                with open(pickle_path, 'rb') as f:
                    qp = pickle.load(f)
            else:
                if pickle_path.exists():
                    pickle_path.unlink()
                    logger.info(f"Removed old cache: {pickle_path}")

                logger.info("Creating QueryParser using src/ modules...")
                qp = QueryParser(settings)
                qp.query_parse(0, settings.benchmark.queries_dir, settings.optimization.insert_queries)

                logger.info(f"Saving query parser to {pickle_path}")
                with open(pickle_path, 'wb') as f:
                    pickle.dump(qp, f)

                with open(cache_metadata_path, 'w') as f:
                    json.dump({
                        'workload_id': workload_id,
                        'insert_queries': current_insert_queries,
                        'query_selection_mode': settings.benchmark.query_selection_mode,
                    }, f)
                logger.info(f"Saved cache metadata: workload_id={workload_id}, insert_queries={current_insert_queries}")

                # Save parsing statistics
                parse_stats = qp.get_parse_statistics()
                if parse_stats:
                    stats_path = artifacts_dir / "parse_statistics.json"
                    with open(stats_path, 'w') as f:
                        json.dump(parse_stats, f, indent=2)
                    logger.info(f"✓ Saved parsing statistics to {stats_path}")
                    logger.info(f"  - Positive utility entries: {parse_stats['positive_utility_percentage']:.2f}%")
                    logger.info(f"  - Nodes with positive utility: {parse_stats['nodes_with_positive_utility_percentage']:.2f}%")
                    logger.info(f"  - Nodes with positive net benefit: {parse_stats['nodes_with_positive_net_benefit_percentage']:.2f}%")

            # Export annotated query files with node_id (always run in query_parsing phase)
            logger.info("Exporting annotated query files with node_id...")
            from src.core.parse_exporter import ParseExporter

            files, _ = resolve_workload_files(settings)
            parsed_output_dir = artifacts_dir / "parsed"
            exporter = ParseExporter(qp.qm)
            exporter.annotate_query_files(files, parsed_output_dir)
            logger.info(f"✓ Annotated {len(files)} query files saved to {parsed_output_dir}")
        else:
            logger.info("[1/6] Skipping query parsing (loading from cache)")
            pickle_path = artifacts_dir / "qp_class.pkl"
            if not pickle_path.exists():
                logger.error("Query parser cache not found! Run with query_parsing phase first.")
                return False
            with open(pickle_path, 'rb') as f:
                qp = pickle.load(f)

        # [1.5/6] b_j をMV SQL の EXPLAIN で補正（ストレージ推定精度向上）
        if settings.execution.should_run_phase('optimization') and ilp_type != 'none':
            calibrate_bj_with_explain(qp, artifacts_dir, settings, verbose)

        # [2/6] ILP最適化実行
        if settings.execution.should_run_phase('optimization'):
            phase_start = time.time()
            logger.info(f"[2/6] Running {ilp_type} optimization...")
            logger.info(f"Storage limit: {storage_limit / (1024*1024):.2f} MB")
            
            if not OptimizerFactory.is_available(ilp_type):
                logger.error(f"Algorithm {ilp_type} is not available")
                return False
            
            # オプティマイザーのパラメータを準備
            optimizer_params = {
                "qm": qp.qm,
                "s_num": qp.s_num,
                "m_cost": qp.m_cost,
                "node_list": qp.node_list,
                "B_max": storage_limit,
                "b_j": qp.b_j,
                "u_ij": qp.u_ij,
                "X": qp.X,
                "q_s_list": qp.q_s_list,
                "query_files": getattr(qp, 'query_files', []),  # Pass query files list
                "settings": settings,
                # インデックス作成コストを追加（Index Scanノードで使用）
                "index_build_costs": getattr(qp, 'index_build_costs', None),
            }
            
            # 近傍探索を使うアルゴリズムの場合、追加パラメータを渡す
            if ilp_type in ["frequency", "utility", "utility_capacity"]:
                optimizer_params.update({
                    "position_node_id": qp.position_node_id,
                    "deeplist": qp.deeplist,
                })

            # frequency アルゴリズムには Redset 重み付き頻度を渡す
            if ilp_type == "frequency":
                optimizer_params["query_frequencies"] = getattr(qp, 'query_frequencies', {})
            
            # BigSubs固有のパラメータを追加
            if ilp_type == "bigsubs":
                optimizer_params.update({
                    "U_j_max": qp.U_j_max if hasattr(qp, 'U_j_max') else [0] * qp.s_num,
                    "U_max": qp.U_max if hasattr(qp, 'U_max') else 0.0,
                    "y_ij": qp.y_ij if hasattr(qp, 'y_ij') else [[0] * qp.s_num for _ in range(len(qp.u_ij))],
                })
                
            optimizer = OptimizerFactory.create(ilp_type, **optimizer_params)
            
            result = optimizer.optimize()
            phase_times['optimization'] = time.time() - phase_start
            
            logger.info(f"Selected {len(result.selected_views)} materialized views")
            logger.info(f"Total utility: {result.total_utility:,.2f}")
            logger.info(f"Total storage: {result.total_storage / (1024*1024):.2f} MB")
            logger.info(f"Optimization time: {phase_times['optimization']:.2f} seconds")
            
            if len(result.selected_views) == 0:
                logger.warning("No MVs selected. Check query parsing and optimization parameters.")
                return False
            
            # 最適化結果を保存（MV選択結果のみ、SQL生成なし）
            optimization_dir = algorithm_dir / "optimization"
            optimization_dir.mkdir(parents=True, exist_ok=True)
            
            # JSON形式で保存（create_sql は空の状態で保存）
            result.save_to_json(str(optimization_dir / "result.json"))
            logger.info(f"Saved optimization result to {optimization_dir / 'result.json'}")
            
            # CSV形式で保存（旧形式互換）
            result.save_to_csv(str(optimization_dir / "mv_list.csv"))
            logger.info(f"Saved MV list to {optimization_dir / 'mv_list.csv'}")
        else:
            logger.info("[2/6] Skipping optimization (loading existing results)")
            # Load optimization results from file
            optimization_dir = algorithm_dir / "optimization"
            result_json_path = optimization_dir / "result.json"
            
            if ilp_type == "none":
                # For 'none' algorithm, create empty result (no MVs selected)
                from src.core.models import OptimizationResult
                result = OptimizationResult(
                    algorithm="none",
                    selected_views=[],
                    total_utility=0.0,
                    total_storage=0,
                    execution_time=0.0
                )
                logger.info("Using empty optimization result (no materialized views)")
            elif not result_json_path.exists():
                logger.error(f"Optimization result not found: {result_json_path}")
                logger.error("Please run Phase 2 (optimization) first, or check the algorithm name.")
                return False
            else:
                logger.info(f"Loading optimization result from {result_json_path}")
                
                # Load OptimizationResult using the new load_from_json method
                from src.core.models import OptimizationResult
                
                result = OptimizationResult.load_from_json(str(result_json_path))
                logger.info(f"Loaded {len(result.selected_views)} materialized views")
                logger.info(f"Total utility: {result.total_utility:,.2f}")
                logger.info(f"Total storage: {result.total_storage / (1024*1024):.2f} MB")

        
        # [3/6] MV作成SQL生成
        if settings.execution.should_run_phase('sql_generation'):
            phase_start = time.time()
            logger.info("[3/6] Generating MV creation SQL...")
            
            # EnhancedMVGeneratorを使用してSQL生成
            # Note: SQL生成のみならデータベース接続は不要
            from src.rewrite.enhanced_mv_generator import EnhancedMVGenerator
            
            # SchemaProviderなしで初期化（静的スキーマを使用）
            mv_generator = EnhancedMVGenerator(qp.qm, schema_provider=None)
            
            # 各MVのSQLを生成
            sql_generation_log = []
            index_count = 0
            for mv in result.selected_views:
                try:
                    # MV作成SQLとインデックスSQLを生成
                    create_sql, index_sql = mv_generator.generate_mv_and_index_sql(mv.node_id)
                    mv.create_sql = create_sql
                    mv.index_sql = index_sql
                    
                    if index_sql:
                        index_count += 1
                    
                    sql_generation_log.append({
                        "view_id": mv.view_id,
                        "node_id": mv.node_id,
                        "status": "SUCCESS",
                        "sql_length": len(create_sql),
                        "has_index": index_sql is not None
                    })
                    
                    if verbose:
                        logger.info(f"Generated SQL for {mv.view_id} ({len(create_sql)} chars)")
                        if index_sql:
                            logger.info(f"  + Index: {index_sql[:60]}...")
                        
                except Exception as e:
                    logger.error(f"Failed to generate SQL for {mv.view_id}: {e}")
                    sql_generation_log.append({
                        "view_id": mv.view_id,
                        "node_id": mv.node_id,
                        "status": "FAILED",
                        "error": str(e)
                    })
            
            phase_times['sql_generation'] = time.time() - phase_start
            
            # SQL生成結果を保存
            sql_dir = algorithm_dir / "sql"
            sql_dir.mkdir(parents=True, exist_ok=True)
            
            # 既存のSQLファイルをクリーンアップ
            for file_path in sql_dir.glob("*.sql"):
                file_path.unlink()
            
            # 各MVのSQLを個別ファイルに保存
            for mv in result.selected_views:
                if mv.create_sql:
                    sql_file = sql_dir / f"{mv.view_id}.sql"
                    with open(sql_file, 'w', encoding='utf-8') as f:
                        f.write(mv.create_sql)
                        # インデックスSQLがあれば追記
                        if mv.index_sql:
                            f.write("\n\n-- Index for MV\n")
                            f.write(mv.index_sql)
            
            # 更新されたresultを保存
            result.save_to_json(str(optimization_dir / "result.json"))
            
            logger.info(f"Generated SQL for {len([log for log in sql_generation_log if log['status'] == 'SUCCESS'])} MVs")
            logger.info(f"Generated {index_count} index creation statements")
            logger.info(f"SQL generation time: {phase_times['sql_generation']:.2f} seconds")
            logger.info(f"SQL files saved to {sql_dir}")
        else:
            logger.info("[3/6] Skipping SQL generation (using existing SQL)")
            # SQL生成をスキップする場合、resultにSQLが含まれているか確認
            if result.selected_views and not result.selected_views[0].create_sql:
                logger.warning("No SQL found in result. Please run Phase 3 (sql_generation) first.")
        
        # [4/6] MV作成（データベースへの登録）
        if settings.execution.should_run_phase('mv_creation'):
            phase_start = time.time()
            logger.info("[4/6] Creating MVs in database...")
            
            logger.info("Initializing MaterializedViewManager...")
            mv_manager = MaterializedViewManager(DatabaseConnection(settings.database))
            
            # Sort MVs by dependency order using topological sort
            logger.info("Sorting MVs by dependency order...")
            sorted_mvs = _topological_sort_mvs(result.selected_views, qp.qm)
            
            logger.info(f"Creating {len(sorted_mvs)} MVs in dependency order")
            
            created_count = 0
            failed_count = 0
            mv_creation_log = []
            total_mvs = len(sorted_mvs)
            index_created_count = 0
            
            for idx, mv in enumerate(sorted_mvs, 1):
                mv_start = time.time()
                
                # 各MVの作成開始時に必ずログを出力
                logger.info(f"[{idx}/{total_mvs}] Creating {mv.view_id}...")
                
                try:
                    success = mv_manager.create_view_from_model(mv, replace=True)
                    mv_time = time.time() - mv_start
                    
                    index_created = False
                    if success:
                        created_count += 1
                        status = "SUCCESS"
                        logger.info(f"  ✓ {mv.view_id} created successfully ({mv_time:.2f}s)")
                        
                        # Create index if index_sql is provided
                        if mv.index_sql:
                            try:
                                logger.info(f"    Creating index for {mv.view_id}...")
                                mv_manager.db.execute(mv.index_sql)
                                index_created = True
                                index_created_count += 1
                                logger.info(f"    ✓ Index created successfully")
                            except Exception as idx_e:
                                logger.warning(f"    ⚠ Failed to create index: {str(idx_e)[:50]}")
                    else:
                        failed_count += 1
                        status = "FAILED"
                        logger.warning(f"  ✗ Failed to create {mv.view_id}")
                    
                    mv_creation_log.append({
                        "view_id": mv.view_id,
                        "node_id": mv.node_id,
                        "status": status,
                        "creation_time": round(mv_time, 2),
                        "size_mb": round(mv.size / (1024 * 1024), 2),
                        "index_created": index_created,
                    })
                except Exception as e:
                    failed_count += 1
                    mv_time = time.time() - mv_start
                    
                    # エラーメッセージを簡潔に表示
                    error_msg = str(e)
                    if len(error_msg) > 100:
                        error_msg = error_msg[:100] + "..."
                    logger.error(f"  ✗ Failed to create MV {mv.view_id}: {error_msg}")
                    
                    mv_creation_log.append({
                        "view_id": mv.view_id,
                        "node_id": mv.node_id,
                        "status": "ERROR",
                        "creation_time": round(mv_time, 2),
                        "error": str(e),
                        "index_created": False,
                    })
                    
                    if verbose:
                        import traceback
                        traceback.print_exc()
            
            phase_times['mv_creation'] = time.time() - phase_start
            
            # 最終結果をサマリー表示
            success_rate = (created_count / total_mvs * 100) if total_mvs > 0 else 0
            logger.info(f"")
            logger.info(f"MV Creation Summary:")
            logger.info(f"  ✓ Success: {created_count}/{total_mvs} ({success_rate:.1f}%)")
            logger.info(f"  ✗ Failed:  {failed_count}/{total_mvs} ({failed_count/total_mvs*100:.1f}%)")
            logger.info(f"  🔍 Indexes: {index_created_count} created")
            logger.info(f"  ⏱  Total time: {phase_times['mv_creation']:.2f} seconds")
            logger.info(f"  ⚡ Avg time per MV: {phase_times['mv_creation']/total_mvs:.2f} seconds")
            
            # MV作成直後に統計情報を更新
            logger.info("")
            logger.info("Updating statistics for created materialized views...")
            analyze_start = time.time()
            try:
                db_conn = DatabaseConnection(settings.database)
                conn = db_conn.get_connection()
                cursor = conn.cursor()
                
                # 作成に成功したMVのみANALYZEを実行
                analyzed_count = 0
                failed_analyze = 0
                
                for mv in sorted_mvs:
                    # 作成に成功したMVかチェック
                    mv_log = next((log for log in mv_creation_log if log['view_id'] == mv.view_id), None)
                    if mv_log and mv_log['status'] == 'SUCCESS':
                        try:
                            # create_sqlから実際のMV名を取得
                            import re
                            match = re.search(r'CREATE\s+MATERIALIZED\s+VIEW\s+(\w+)', mv.create_sql, re.IGNORECASE)
                            actual_view_name = match.group(1) if match else mv.view_id
                            
                            cursor.execute(f"ANALYZE {actual_view_name}")
                            analyzed_count += 1
                            if verbose:
                                logger.info(f"  Analyzed {actual_view_name}")
                        except Exception as e:
                            failed_analyze += 1
                            logger.warning(f"  Failed to analyze {mv.view_id}: {e}")
                
                conn.commit()
                cursor.close()
                db_conn.close()
                
                analyze_time = time.time() - analyze_start
                logger.info(f"✓ Analyzed {analyzed_count}/{created_count} materialized views in {analyze_time:.2f}s")
                if failed_analyze > 0:
                    logger.warning(f"  Failed to analyze {failed_analyze} views")
            except Exception as e:
                logger.warning(f"Failed to analyze materialized views: {e}")
                if verbose:
                    import traceback
                    traceback.print_exc()
            
            # MV作成結果を保存
            mv_creation_dir = algorithm_dir / "mv_creation"
            mv_creation_dir.mkdir(parents=True, exist_ok=True)
            
            with open(mv_creation_dir / "creation_log.json", 'w', encoding='utf-8') as f:
                json.dump({
                    "total_mvs": len(sorted_mvs),
                    "created": created_count,
                    "failed": failed_count,
                    "total_time": round(phase_times['mv_creation'], 2),
                    "mvs": mv_creation_log,
                }, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved MV creation log to {mv_creation_dir / 'creation_log.json'}")
        else:
            logger.info("[4/6] Skipping MV creation in database")
        
        # [5/6] クエリ書き換え
        if settings.execution.should_run_phase('query_rewriting'):
            phase_start = time.time()
            logger.info("[5/6] Rewriting queries...")
            rewriter = QueryRewriter(settings)
            
            rewritten_dir = Path(output_dir) / "query_rewrite" / "re_sql" / ilp_type
            rewritten_dir.mkdir(parents=True, exist_ok=True)
            # 前回実行（別ワークロード等）の書き換え済みSQLが残ると、ベンチマークが
            # 存在しないMVを参照する古いクエリまで実行して失敗するため、先に削除する
            for stale_file in rewritten_dir.glob("*.sql"):
                stale_file.unlink()

            rewritten_queries = rewriter.rewrite_queries(result.selected_views)
            
            rewrite_log = []
            for query_id, rewritten_sql in rewritten_queries.items():
                query_start = time.time()
                output_file = rewritten_dir / f"{query_id}.sql"
                with open(output_file, 'w') as f:
                    f.write(rewritten_sql)
                query_time = time.time() - query_start
                
                rewrite_log.append({
                    "query_id": query_id,
                    "output_file": str(output_file),
                    "rewrite_time": round(query_time, 4),
                })
            
            phase_times['query_rewriting'] = time.time() - phase_start
            logger.info(f"Rewritten {len(rewritten_queries)} queries to {rewritten_dir}")
            logger.info(f"Query rewriting time: {phase_times['query_rewriting']:.2f} seconds")
            
            # クエリ書き換え結果を保存
            query_rewrite_dir = algorithm_dir / "query_rewrite"
            query_rewrite_dir.mkdir(parents=True, exist_ok=True)
            
            with open(query_rewrite_dir / "rewrite_log.json", 'w', encoding='utf-8') as f:
                json.dump({
                    "total_queries": len(rewritten_queries),
                    "total_time": round(phase_times['query_rewriting'], 2),
                    "output_directory": str(rewritten_dir),
                    "queries": rewrite_log,
                }, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved query rewrite log to {query_rewrite_dir / 'rewrite_log.json'}")
        else:
            logger.info("[5/6] Skipping query rewriting")
        
        # [6/6] 書き換えられたクエリの実行
        if settings.execution.should_run_phase('benchmark'):
            phase_start = time.time()
            logger.info("[6/6] Executing benchmark...")
            
            # ベンチマーク実行前にマテリアライズドビューの統計情報を更新
            logger.info("Updating statistics for materialized views...")
            try:
                db_conn = DatabaseConnection(settings.database)
                conn = db_conn.get_connection()
                
                # すべてのマテリアライズドビューに対してANALYZEを実行
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT schemaname, matviewname 
                    FROM pg_matviews 
                    WHERE schemaname = 'public'
                """)
                
                mv_list = cursor.fetchall()
                total_mvs = len(mv_list)
                logger.info(f"Found {total_mvs} materialized views to analyze...")
                
                mv_count = 0
                for idx, (schema, mv_name) in enumerate(mv_list, 1):
                    # 進捗を定期的に表示（10%ごと、または10件ごと）
                    if total_mvs > 20 and idx % max(1, total_mvs // 10) == 0:
                        logger.info(f"  Analyzing MVs... {idx}/{total_mvs} ({idx*100//total_mvs}%)")
                    cursor.execute(f"ANALYZE {schema}.{mv_name}")
                    mv_count += 1
                
                conn.commit()
                cursor.close()
                db_conn.close()
                
                logger.info(f"✓ Analyzed {mv_count} materialized views")
            except Exception as e:
                logger.warning(f"Failed to analyze materialized views: {e}")
                if verbose:
                    import traceback
                    traceback.print_exc()
            
            # workload_type を決定
            # settings から取得、または引数から取得
            workload_type = getattr(settings, '_workload_type', None)
            if workload_type is None:
                # settingsからworkload_typeを推測
                query_selection_mode = settings.benchmark.query_selection_mode
                use_ceb = settings.query.use_ceb
                benchmark_type = settings.benchmark.type
                
                if query_selection_mode == 'all_job':
                    if use_ceb or benchmark_type == 'ceb':
                        workload_type = 'ceb'
                    else:
                        workload_type = 'job'
                elif query_selection_mode == 'redbench':
                    if benchmark_type == 'ceb':
                        workload_type = 'redbench-ceb'
                    elif use_ceb:
                        workload_type = 'redbench'
                    else:
                        workload_type = 'redbench-job'
                else:
                    workload_type = 'redbench-job'  # デフォルト
            
            logger.info(f"Workload type: {workload_type}")
            
            # workload_runner を使用してベンチマーク実行
            from src.benchmark.workload_runner import run_workload_benchmark
            
            benchmark_results = run_workload_benchmark(
                workload_type=workload_type,
                algorithm=ilp_type,
                settings=settings,
                output_dir=Path(output_dir),
                verbose=verbose,
                warmup=warmup
            )
            
            phase_times['benchmark'] = time.time() - phase_start
            
            if benchmark_results:
                # ベンチマーク結果を保存
                benchmark_dir = algorithm_dir / "benchmark"
                benchmark_dir.mkdir(parents=True, exist_ok=True)
                
                with open(benchmark_dir / "benchmark_results.json", 'w', encoding='utf-8') as f:
                    json.dump(benchmark_results, f, indent=2, ensure_ascii=False)
                
                logger.info(f"Saved benchmark results to {benchmark_dir / 'benchmark_results.json'}")
                
                # サマリー表示
                logger.info(f"\nBenchmark Summary:")
                logger.info(f"  Workload: {workload_type}")
                logger.info(f"  Total queries: {benchmark_results['total_queries']}")
                logger.info(f"  Successful: {benchmark_results['successful']}")
                logger.info(f"  Failed: {benchmark_results['failed']}")
                logger.info(f"  Total time: {benchmark_results['total_time']:.2f}s")
                logger.info(f"  Avg time: {benchmark_results['avg_time_per_query']:.4f}s")
            else:
                logger.error("Benchmark execution failed")
        else:
            logger.info("[6/6] Skipping benchmark execution")
            
    except Exception as e:
        logger.error(f"Error in ILP optimization: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False

    elapsed = time.time() - start_time
    
    # 統合サマリーを保存
    summary = {
        "algorithm": ilp_type,
        "total_execution_time": round(elapsed, 2),
        "phases": phase_times,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    
    with open(algorithm_dir / "summary.json", 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n✓ Completed {ilp_type} in {elapsed:.2f} seconds")
    logger.info(f"Results saved to {algorithm_dir}")
    logger.info(f"Summary: {algorithm_dir / 'summary.json'}")
    return True


def main():
    """メイン処理"""
    args = parse_args()

    # Load settings from config file or use defaults
    from config.settings import Settings
    if args.config:
        settings = Settings.from_yaml(args.config)
    else:
        settings = Settings()
    
    # Setup logging first (root logger to capture all modules)
    setup_logging(
        name=None,
        level=settings.logging.level,
        console=True
    )
    
    # Get logger for this module
    global logger
    logger = get_logger('run_experiment')
    
    # Override settings with command-line arguments
    if args.phases or args.start_from or args.end_at:
        # Use new phase control
        if args.phases:
            # Only run specified phases
            settings.execution.query_parsing = 'query_parsing' in args.phases
            settings.execution.optimization = 'optimization' in args.phases
            settings.execution.sql_generation = 'sql_generation' in args.phases
            settings.execution.mv_creation = 'mv_creation' in args.phases
            settings.execution.query_rewriting = 'query_rewriting' in args.phases
            settings.execution.benchmark = 'benchmark' in args.phases
        
        if args.start_from:
            settings.execution.start_from = args.start_from
        
        if args.end_at:
            settings.execution.end_at = args.end_at
    else:
        # Legacy skip flags (backward compatibility)
        if args.skip_mv_creation:
            settings.execution.mv_creation = False
            logger.warning("--skip-mv-creation is deprecated. Use --phases or execution.phases in config YAML.")
        if args.skip_rewrite:
            settings.execution.query_rewriting = False
            logger.warning("--skip-rewrite is deprecated. Use --phases or execution.phases in config YAML.")
        if args.skip_benchmark:
            settings.execution.benchmark = False
            logger.warning("--skip-benchmark is deprecated. Use --phases or execution.phases in config YAML.")

    # Use storage_limit from command line if specified, otherwise use config
    storage_limit = args.storage_limit if args.storage_limit is not None else settings.optimization.storage_limit_bytes
    
    # Use insert_queries from command line if specified, otherwise use config
    if args.insert_queries is not None:
        settings.optimization.insert_queries = args.insert_queries
    
    # Override workload settings from command line if specified
    if args.workload_type is not None:
        # Map workload_type to settings
        # job: All JOB queries (query_selection_mode=all_job, use_ceb=False)
        # ceb: All CEB queries (query_selection_mode=all_job, use_ceb=True, type=ceb)
        # redbench: Full RedBench (query_selection_mode=redbench, use_ceb=True)
        # redbench-job: RedBench JOB only (query_selection_mode=redbench, use_ceb=False)
        # redbench-ceb: RedBench CEB only (query_selection_mode=redbench, use_ceb=True, type=ceb)
        
        # workload_typeをsettingsに保存（ベンチマークフェーズで使用）
        settings._workload_type = args.workload_type
        
        if args.workload_type == 'job':
            settings.benchmark.type = 'job'
            settings.benchmark.query_selection_mode = 'all_job'
            settings.query.use_ceb = False
        elif args.workload_type == 'ceb':
            settings.benchmark.type = 'ceb'
            settings.benchmark.query_selection_mode = 'all_job'
            settings.query.use_ceb = True
        elif args.workload_type == 'ceb-1a':
            # CEB template-based selection (e.g., 1a, 2a, 3b)
            settings.benchmark.type = 'ceb'
            settings.benchmark.query_selection_mode = 'all_ceb'
            settings.benchmark.ceb_template = args.ceb_template
            settings.query.use_ceb = True
            if args.ceb_limit is not None:
                settings.benchmark.ceb_limit = args.ceb_limit
        elif args.workload_type == 'redbench':
            settings.benchmark.type = 'job'  # Start with JOB, but include CEB
            settings.benchmark.query_selection_mode = 'redbench'
            settings.query.use_ceb = True
        elif args.workload_type == 'redbench-job':
            settings.benchmark.type = 'job'
            settings.benchmark.query_selection_mode = 'redbench'
            settings.query.use_ceb = False
        elif args.workload_type == 'redbench-ceb':
            settings.benchmark.type = 'ceb'
            settings.benchmark.query_selection_mode = 'redbench'
            settings.query.use_ceb = True

    # Determine display name for workload
    workload_display = args.workload_type if args.workload_type else f"{settings.benchmark.query_selection_mode}-{settings.benchmark.type}"

    logger.info("=" * 60)
    logger.info("MV Query Optimization Experiment")
    logger.info("=" * 60)
    logger.info(f"Algorithms: {', '.join(args.algorithms)}")
    logger.info(f"Output root: {args.output}")
    logger.info(f"Storage Limit: {storage_limit / (1024*1024):.2f} MB")
    logger.info(f"Insert Queries: {settings.optimization.insert_queries}")
    logger.info(f"Workload: {workload_display}")
    logger.info(f"  - Type: {settings.benchmark.type}")
    logger.info(f"  - Query Selection: {settings.benchmark.query_selection_mode}")
    if settings.benchmark.query_selection_mode == 'all_ceb':
        logger.info(f"  - CEB Template: {settings.benchmark.ceb_template}")
    logger.info(f"  - Include CEB: {settings.query.use_ceb}")
    
    # Display execution phases
    phases_status = []
    for phase in ['query_parsing', 'optimization', 'sql_generation', 'mv_creation', 'query_rewriting', 'benchmark']:
        status = "✓" if settings.execution.should_run_phase(phase) else "✗"
        phases_status.append(f"{status} {phase}")
    logger.info(f"Execution Phases:\n  " + "\n  ".join(phases_status))
    logger.info("=" * 60)

    # Identify the workload by the content of the query files it resolves to
    query_files, query_freq = resolve_workload_files(settings)
    workload_id = run_layout.compute_workload_id(
        query_files, settings.benchmark.queries_dir, query_freq
    )
    label = run_layout.workload_label(args.workload_type, settings)
    run_id = run_layout.validate_run_id(args.run_id) if args.run_id else run_layout.new_run_id(label)
    run_dir = run_layout.run_dir(args.output, run_id)
    artifacts_dir = run_layout.artifacts_dir(
        args.output, workload_id, settings.optimization.insert_queries
    )
    logger.info(f"Run: {run_id} ({run_dir})")
    logger.info(f"Workload id: {workload_id} ({len(query_files)} queries), artifacts: {artifacts_dir}")

    # Continuing an existing run must use the same workload, or its algorithms would not be comparable
    previous = RunManifest.read(run_dir)
    if previous is not None and previous.workload.get("id") != workload_id:
        logger.error(
            f"Run {run_id} was made with workload {previous.workload.get('id')} "
            f"({previous.workload.get('label')}), not {workload_id} ({label}). "
            "Use a new --run-id."
        )
        sys.exit(2)

    setup_directories(str(run_dir))
    manifest = previous or RunManifest(
        run_id=run_id,
        created_at=time.time(),
        status="running",
        workload={
            "id": workload_id,
            "label": label,
            "type": settings.benchmark.type,
            "query_selection_mode": settings.benchmark.query_selection_mode,
            "ceb_template": settings.benchmark.ceb_template,
            "ceb_limit": settings.benchmark.ceb_limit,
            "include_ceb": settings.query.use_ceb,
            "num_queries": len(query_files),
            "query_ids": [Path(f).stem for f in query_files],
        },
        params={
            "algorithms": args.algorithms,
            "storage_limit_bytes": storage_limit,
            "insert_queries": settings.optimization.insert_queries,
            "warmup": not args.no_warmup,
        },
        git_commit=run_layout.git_commit(project_root),
    )
    manifest.status = "running"
    manifest.finished_at = None
    manifest.params["phases"] = [
        p for p in ['query_parsing', 'optimization', 'sql_generation', 'mv_creation', 'query_rewriting', 'benchmark']
        if settings.execution.should_run_phase(p)
    ]
    manifest.write(run_dir)

    # 各アルゴリズムで実行
    total_start = time.time()
    import copy

    for ilp_type in args.algorithms:
        try:
            ok = run_ilp_optimization(
                ilp_type=ilp_type,
                output_dir=str(run_dir),
                artifacts_dir=artifacts_dir,
                workload_id=workload_id,
                settings=copy.deepcopy(settings),
                storage_limit=storage_limit,
                verbose=args.verbose,
                warmup=not args.no_warmup,
            )
            if ok and ilp_type not in manifest.algorithms_done:
                manifest.algorithms_done.append(ilp_type)
            elif not ok and ilp_type not in manifest.algorithms_failed:
                manifest.algorithms_failed.append(ilp_type)
        except Exception as e:
            logger.error(f"\n✗ Error running {ilp_type}: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            if ilp_type not in manifest.algorithms_failed:
                manifest.algorithms_failed.append(ilp_type)
            continue
        finally:
            manifest.write(run_dir)

    total_elapsed = time.time() - total_start
    manifest.status = "failed" if manifest.algorithms_failed else "completed"
    manifest.finished_at = time.time()
    manifest.write(run_dir)

    logger.info("\n" + "=" * 60)
    logger.info("Experiment completed successfully!")
    logger.info(f"Total time: {total_elapsed:.2f} seconds")
    logger.info(f"Results saved to: {run_dir}/")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
