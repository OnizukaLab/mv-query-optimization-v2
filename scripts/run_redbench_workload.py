#!/usr/bin/env python3
"""RedBenchワークロードを実行するスクリプト

ワークロードタイプに応じたベンチマークを実行できます：
- job: 全113 JOBクエリ（シンプル実行、各クエリ1回）
- ceb: 全CEBクエリ（シンプル実行、各クエリ1回）
- redbench: RedBench全体（グループ別実行、JOB+CEB混在）
- redbench-job: RedBench JOBクエリのみ（グループ別実行、83クエリ）
- redbench-ceb: RedBench CEBクエリのみ（グループ別実行）

使用例:
    # RedBench JOBクエリをグループ別に実行
    python scripts/run_redbench_workload.py --workload redbench-job --algorithm normal
    
    # 全JOBクエリをシンプル実行（各クエリ1回）
    python scripts/run_redbench_workload.py --workload job --algorithm none
    
    # RedBench全体をグループ別実行（JOB+CEB）
    python scripts/run_redbench_workload.py --workload redbench --algorithm frequency
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from src.benchmark.workload_runner import run_workload_benchmark


def setup_logging(verbose: bool = False):
    """ロギングを設定"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


def list_workloads():
    """利用可能なワークロードを一覧表示"""
    print("\n=== Available Workload Types ===\n")
    print("  job          - All 113 JOB queries (simple execution, each query once)")
    print("  ceb          - All CEB queries (simple execution, each query once)")
    print("  redbench     - Full RedBench workload (group execution, JOB + CEB mixed)")
    print("  redbench-job - RedBench JOB queries only (group execution, 83 queries)")
    print("  redbench-ceb - RedBench CEB queries only (group execution)")
    print()
    print("=== Execution Modes ===\n")
    print("  Simple (job, ceb):")
    print("    - Each query is executed once")
    print("    - Results show total and average execution time")
    print()
    print("  Group (redbench, redbench-job, redbench-ceb):")
    print("    - Queries are grouped by variability bucket")
    print("    - Queries may appear multiple times (according to RedBench workload)")
    print("    - Results show per-group statistics")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="RedBenchワークロードを実行",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available workloads
  python scripts/run_redbench_workload.py --list
  
  # Run RedBench JOB queries by variability group
  python scripts/run_redbench_workload.py --workload redbench-job --algorithm normal
  
  # Run all JOB queries (simple, each once)
  python scripts/run_redbench_workload.py --workload job --algorithm none
  
  # Run full RedBench (JOB + CEB mixed)
  python scripts/run_redbench_workload.py --workload redbench --algorithm frequency
        """
    )
    
    parser.add_argument(
        "--workload", "-w",
        type=str,
        choices=["job", "ceb", "redbench", "redbench-job", "redbench-ceb"],
        default="redbench-job",
        help="""Workload type:
  job: All 113 JOB queries (simple execution)
  ceb: All CEB queries (simple execution)
  redbench: Full RedBench (group execution, JOB + CEB)
  redbench-job: RedBench JOB only (group execution)
  redbench-ceb: RedBench CEB only (group execution)
(default: redbench-job)"""
    )
    parser.add_argument(
        "--algorithm", "-a",
        type=str,
        choices=["none", "normal", "bigsubs", "utility_capacity", "utility", "frequency"],
        default="none",
        help="Algorithm to use. 'none' uses original SQL (default: none)"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List available workloads"
    )
    parser.add_argument(
        "--no-warmup",
        action="store_true",
        help="Skip warmup phase"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output file path for results"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="Config file path"
    )
    
    args = parser.parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    if args.list:
        list_workloads()
        return
    
    # 設定を読み込み
    if args.config:
        settings = Settings.from_yaml(args.config)
    else:
        settings = Settings()
    
    logger.info("=" * 60)
    logger.info("RedBench Workload Execution")
    logger.info("=" * 60)
    logger.info(f"Workload: {args.workload}")
    logger.info(f"Algorithm: {args.algorithm}")
    logger.info(f"Warmup: {'Disabled' if args.no_warmup else 'Enabled'}")
    logger.info("=" * 60)
    
    start_time = time.time()
    
    # 共通モジュールを使用してベンチマーク実行
    results = run_workload_benchmark(
        workload_type=args.workload,
        algorithm=args.algorithm,
        settings=settings,
        verbose=args.verbose,
        warmup=not args.no_warmup
    )
    
    if results is None:
        logger.error("Benchmark execution failed")
        return
    
    elapsed = time.time() - start_time
    
    # 出力パスを決定
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = project_root / "Output" / f"redbench_{args.workload}_{args.algorithm}_results.json"
    
    # 結果を保存
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n✓ Results saved to {output_path}")
    
    # サマリー表示
    print("\n" + "=" * 60)
    print("Final Summary")
    print("=" * 60)
    print(f"Workload: {args.workload}")
    print(f"Algorithm: {args.algorithm}")
    print(f"Total queries: {results['total_queries']}")
    print(f"Successful: {results['successful']}")
    print(f"Failed: {results['failed']}")
    print(f"Total execution time: {results['total_time']:.2f}s")
    print(f"Avg time per query: {results['avg_time_per_query']:.4f}s")
    
    if 'group_results' in results:
        print("\nBy Group:")
        for group_name, stats in sorted(results['group_results'].items()):
            print(f"  {group_name}: {stats['total_queries']} queries, {stats['total_time']:.2f}s, {stats['avg_time']:.4f}s/q")
    
    print(f"\nTotal elapsed: {elapsed:.2f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
