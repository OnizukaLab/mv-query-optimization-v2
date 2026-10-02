#!/usr/bin/env python3
"""アルゴリズム比較スクリプト

複数のILPアルゴリズムの結果を比較する
"""
import argparse
import csv
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def load_mv_selections(result_dir: Path, algorithms: list[str]) -> dict[str, dict]:
    """MV選択結果を読み込み

    Args:
        result_dir: 結果ディレクトリ
        algorithms: アルゴリズムリスト

    Returns:
        {algorithm: {query_id: [mv_nodes]}}
    """
    results = {}

    for algo in algorithms:
        mv_file = result_dir / algo / "mv_y_list.csv"
        if mv_file.exists():
            with open(mv_file, encoding="utf-8") as f:
                reader = csv.reader(f)
                mv_data = {}
                for i, row in enumerate(reader):
                    if row:
                        mv_data[i] = [node.strip() for node in row if node.strip()]
                    else:
                        mv_data[i] = []
                results[algo] = mv_data
        else:
            print(f"Warning: MV list not found: {mv_file}")
            results[algo] = {}

    return results


def load_execution_times(result_dir: Path, algorithms: list[str]) -> dict[str, float]:
    """実行時間を読み込み

    Args:
        result_dir: 結果ディレクトリ
        algorithms: アルゴリズムリスト

    Returns:
        {algorithm: execution_time}
    """
    times = {}

    for algo in algorithms:
        # query_rewrite からの出力ファイル
        time_file = result_dir / "query_rewrite" / f"{algo}.out"

        if time_file.exists():
            # TODO: 出力ファイルから実行時間を抽出
            times[algo] = 0.0
        else:
            times[algo] = 0.0

    return times


def count_mv_nodes(mv_selections: dict[str, dict]) -> dict[str, int]:
    """各アルゴリズムのMV数をカウント

    Args:
        mv_selections: MV選択結果

    Returns:
        {algorithm: total_mv_count}
    """
    counts = {}

    for algo, queries in mv_selections.items():
        unique_mvs = set()

        for query_id, mv_nodes in queries.items():
            for node in mv_nodes:
                if node and node != "NONE":
                    unique_mvs.add(node)

        counts[algo] = len(unique_mvs)

    return counts


def compare_algorithms(result_dir: Path, algorithms: list[str]) -> None:
    """アルゴリズムを比較

    Args:
        result_dir: 結果ディレクトリ
        algorithms: アルゴリズムリスト
    """
    print("\n" + "=" * 80)
    print("Algorithm Comparison")
    print("=" * 80)

    # MV選択結果読み込み
    mv_selections = load_mv_selections(result_dir, algorithms)

    # MV数カウント
    mv_counts = count_mv_nodes(mv_selections)

    # 結果表示
    print(f"\n{'Algorithm':<20} {'Total MVs':<15} {'Queries with MVs':<20}")
    print("-" * 80)

    for algo in algorithms:
        total_mvs = mv_counts.get(algo, 0)
        queries_with_mvs = sum(1 for mvs in mv_selections.get(algo, {}).values() if mvs)

        print(f"{algo:<20} {total_mvs:<15} {queries_with_mvs:<20}")

    print("=" * 80)


def export_comparison_csv(result_dir: Path, algorithms: list[str], output_file: str) -> None:
    """比較結果をCSVにエクスポート

    Args:
        result_dir: 結果ディレクトリ
        algorithms: アルゴリズムリスト
        output_file: 出力CSVファイル
    """
    mv_selections = load_mv_selections(result_dir, algorithms)
    mv_counts = count_mv_nodes(mv_selections)

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Algorithm", "Total MVs", "Queries with MVs"])

        for algo in algorithms:
            total_mvs = mv_counts.get(algo, 0)
            queries_with_mvs = sum(1 for mvs in mv_selections.get(algo, {}).values() if mvs)
            writer.writerow([algo, total_mvs, queries_with_mvs])

    print(f"\nExported comparison to: {output_file}")


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(description="Compare optimization algorithm results")
    parser.add_argument("--results", type=str, default="Output", help="Results directory")
    parser.add_argument(
        "--algorithms",
        nargs="+",
        default=["normal", "bigsubs", "utility", "utility_capacity", "frequency"],
        help="Algorithms to compare",
    )
    parser.add_argument("--output", type=str, help="Output CSV file")

    args = parser.parse_args()

    result_dir = Path(args.results)

    if not result_dir.exists():
        print(f"Error: Results directory not found: {result_dir}")
        sys.exit(1)

    # 比較実行
    compare_algorithms(result_dir, args.algorithms)

    # CSV出力
    if args.output:
        export_comparison_csv(result_dir, args.algorithms, args.output)


if __name__ == "__main__":
    main()
