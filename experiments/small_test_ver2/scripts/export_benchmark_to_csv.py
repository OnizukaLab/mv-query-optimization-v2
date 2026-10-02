#!/usr/bin/env python3
"""
ベンチマーク結果をCSVにエクスポートするスクリプト

各タイムステップごとのクエリ実行時間を抽出し、
縦軸にタイムステップ、横軸に手法を取ったCSVファイルを生成します。

使い方:
    python export_benchmark_to_csv.py [結果ディレクトリ] [出力CSVファイル名]
    
    例:
    python export_benchmark_to_csv.py \
        experiments/small_test_ver2/time_dependent_output/job/result_50M_2 \
        benchmark_execution_times.csv
"""

import json
import csv
import sys
from pathlib import Path
from typing import Dict, Set


def load_benchmark_result(file_path: Path) -> tuple[Dict[str, float], Dict[str, float]]:
    """
    ベンチマーク結果JSONファイルを読み込み、タイムステップごとの実行時間を返す
    
    Args:
        file_path: ベンチマーク結果JSONファイルのパス
    
    Returns:
        2つの辞書のタプル:
        - {timestep: total_time} マイグレーション時間を含む
        - {timestep: query_only_time} マイグレーション時間を除く
    """
    with open(file_path, 'r') as f:
        data = json.load(f)
    
    total_times = {}
    query_only_times = {}
    
    for ts_result in data['timestep_results']:
        timestep = ts_result['timestep']
        total_time = ts_result['total_time']
        
        # マイグレーション時間を取得（存在しない場合は0）
        migration_time = 0.0
        if 'migration' in ts_result and isinstance(ts_result['migration'], dict):
            migration_time = ts_result['migration'].get('time', 0.0)
        
        total_times[timestep] = total_time
        query_only_times[timestep] = total_time - migration_time
    
    return total_times, query_only_times


def export_to_csv(result_dir: Path, output_file: Path, file_patterns: Dict[str, str] = None, export_query_only: bool = True):
    """
    複数のベンチマーク結果をCSVにエクスポート
    
    Args:
        result_dir: ベンチマーク結果が格納されているディレクトリ
        output_file: 出力CSVファイルのパス
        file_patterns: {手法名: ファイル名パターン} の辞書。Noneの場合はデフォルトパターンを使用
        export_query_only: Trueの場合、マイグレーション時間を除いたCSVも出力
    """
    # デフォルトのファイルパターン
    if file_patterns is None:
        file_patterns = {
            'baseline': 'benchmark_results_baseline*.json',
            'static_16_1': 'benchmark_results_static_16_1.json',
            'dynamic_16_1': 'benchmark_results_dynamic_16_1.json',
            'dynamic_16_2': 'benchmark_results_dynamic_16_2.json',
            'dynamic_16_2p': 'benchmark_results_dynamic_16_2p.json',
            'dynamic_16_3': 'benchmark_results_dynamic_16_3.json',
            'dynamic_16_3p': 'benchmark_results_dynamic_16_3p.json',
        }
    
    # 利用可能な全てのベンチマーク結果ファイルを検出
    total_time_by_method = {}  # マイグレーション時間を含む
    query_only_time_by_method = {}  # マイグレーション時間を除く
    timesteps: Set[str] = set()
    
    for method_name, pattern in file_patterns.items():
        # パターンに応じてファイルを検索
        if '*' in pattern:
            matched_files = list(result_dir.glob(pattern))
            if not matched_files:
                continue
            file_path = matched_files[0]  # 最初のマッチを使用
        else:
            file_path = result_dir / pattern
            if not file_path.exists():
                continue
        
        try:
            total_times, query_only_times = load_benchmark_result(file_path)
            total_time_by_method[method_name] = total_times
            query_only_time_by_method[method_name] = query_only_times
            timesteps.update(total_times.keys())
            print(f"✓ Loaded {method_name}: {len(total_times)} timesteps ({file_path.name})")
        except Exception as e:
            print(f"✗ Failed to load {method_name}: {e}")
            continue
    
    if not total_time_by_method:
        print("エラー: 有効なベンチマーク結果ファイルが見つかりませんでした")
        return False
    
    # タイムステップをソート（数値または文字列として）
    try:
        timesteps_sorted = sorted(timesteps, key=lambda x: int(x))
    except ValueError:
        timesteps_sorted = sorted(timesteps)
    
    # CSVに書き出し（マイグレーション時間を含む）
    methods = sorted(total_time_by_method.keys())
    _write_csv(output_file, methods, timesteps_sorted, total_time_by_method, "total")
    
    # マイグレーション時間を除いたCSVも出力
    if export_query_only:
        query_only_file = output_file.parent / (output_file.stem + "_query_only" + output_file.suffix)
        _write_csv(query_only_file, methods, timesteps_sorted, query_only_time_by_method, "query_only")
    
    return True


def _write_csv(
    output_file: Path,
    methods: list,
    timesteps_sorted: list,
    data_by_method: Dict[str, Dict[str, float]],
    label: str
):
    """CSVファイルを書き出すヘルパー関数
    
    Args:
        output_file: 出力CSVファイルのパス
        methods: 手法名のリスト
        timesteps_sorted: ソート済みタイムステップのリスト
        data_by_method: {method_name: {timestep: time}} のデータ
        label: ラベル（"total" or "query_only"）
    """
    with open(output_file, 'w', newline='') as csvfile:
        # ヘッダー: timestep, method1, method2, ...
        fieldnames = ['timestep'] + methods
        
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        # 各タイムステップの行を書き込み
        for ts in timesteps_sorted:
            row = {'timestep': ts}
            for method in methods:
                if ts in data_by_method[method]:
                    row[method] = data_by_method[method][ts]
                else:
                    row[method] = ''  # データがない場合は空
            writer.writerow(row)
    
    time_type = "Total time (incl. migration)" if label == "total" else "Query-only time (excl. migration)"
    print(f"\n✓ CSV saved to: {output_file}")
    print(f"  Type: {time_type}")
    print(f"  Timesteps: {len(timesteps_sorted)}")
    print(f"  Methods: {len(methods)}")
    print(f"  Methods included: {', '.join(methods)}")


def main():
    """メイン関数"""
    # コマンドライン引数の処理
    if len(sys.argv) < 2:
        # デフォルトのパス
        result_dir = Path('experiments/small_test_ver2/time_dependent_output/job/result_100M_fix')
        output_filename = 'benchmark_execution_times.csv'
    elif len(sys.argv) == 2:
        result_dir = Path(sys.argv[1])
        output_filename = 'benchmark_execution_times.csv'
    else:
        result_dir = Path(sys.argv[1])
        output_filename = sys.argv[2]
    
    # 出力ファイルのパス
    output_file = result_dir / output_filename
    
    print(f"=== Benchmark Results CSV Exporter ===")
    print(f"Result directory: {result_dir}")
    print(f"Output file: {output_file}")
    print()
    
    # ディレクトリの存在確認
    if not result_dir.exists():
        print(f"エラー: ディレクトリが見つかりません: {result_dir}")
        sys.exit(1)

    file_patterns1 = {
            'baseline_16_1': 'benchmark_results_baseline*.json',
            'static_16_1': 'benchmark_results_static_16_1.json',
            'dynamic_16_1': 'benchmark_results_dynamic_16_1.json',
            'dynamic_16_1p': 'benchmark_results_dynamic_16_1p.json',
        }
    
    file_patterns2 = {
            'baseline_16_2': 'benchmark_results_baseline*.json',
            'static_16_2': 'benchmark_results_static_16_2.json',
            'dynamic_16_2': 'benchmark_results_dynamic_16_2.json',
            'dynamic_16_2p': 'benchmark_results_dynamic_16_2ps.json',
        }
    
    file_patterns3 = {
            'baseline_16_3': 'benchmark_results_baseline*.json',
            'static_16_3': 'benchmark_results_static_16_3.json',
            'dynamic_16_3': 'benchmark_results_dynamic_16_3.json',
            'dynamic_16_3p': 'benchmark_results_dynamic_16_3p.json',
        }

    file_patterns4 = {
            'baseline_16_4': 'benchmark_results_baseline*.json',
            'static_16_4': 'benchmark_results_static_16_4.json',
            'dynamic_16_4': 'benchmark_results_dynamic_16_4.json',
            'dynamic_16_4p': 'benchmark_results_dynamic_16_4p.json',
        }
    
    file_patterns5 = {
            'static_8_1_5': 'benchmark_results_static_8_1_5.json',
            'dynamic_8_1_5': 'benchmark_results_dynamic_8_1_5.json',
            'static_8_2_5': 'benchmark_results_static_8_2_5.json',
            'dynamic_8_2_5': 'benchmark_results_dynamic_8_2_5.json',
            'static_8_3_5': 'benchmark_results_static_8_3_5.json',
            'dynamic_8_3_5': 'benchmark_results_dynamic_8_3_5.json',
        }

    file_patterns6 = {
            'static_16_1_5': 'benchmark_results_static_16_1_5.json',
            'dynamic_16_1_5': 'benchmark_results_dynamic_16_1_5.json',
            'dynamic_16_1_5p': 'benchmark_results_dynamic_16_1_5p.json',
            'static_16_2_5': 'benchmark_results_static_16_2_5.json',
            'dynamic_16_2_5': 'benchmark_results_dynamic_16_2_5.json',
            'dynamic_16_2_5p': 'benchmark_results_dynamic_16_2_5p.json',
            'static_16_3_5': 'benchmark_results_static_16_3_5.json',
            'dynamic_16_3_5': 'benchmark_results_dynamic_16_3_5.json',
            'dynamic_16_3_5p': 'benchmark_results_dynamic_16_3_5p.json',
        }

    file_patterns7 = {
            'static_16_1_10': 'benchmark_results_static_16_1_10.json',
            'dynamic_16_1_10': 'benchmark_results_dynamic_16_1_10.json',
            'dynamic_16_1_10p': 'benchmark_results_dynamic_16_1_10p.json',
            'static_16_2_10': 'benchmark_results_static_16_2_10.json',
            'dynamic_16_2_10': 'benchmark_results_dynamic_16_2_10.json',
            'dynamic_16_2_10p': 'benchmark_results_dynamic_16_2_10p.json',
            'static_16_3_10': 'benchmark_results_static_16_3_10.json',
            'dynamic_16_3_10': 'benchmark_results_dynamic_16_3_10.json',
            'dynamic_16_3_10p': 'benchmark_results_dynamic_16_3_10p.json',
            'static_16_peak': 'benchmark_results_static_16_peak.json',
            'dynamic_16_peakp': 'benchmark_results_dynamic_16_peakp.json',
            'dynamic_16_peak': 'benchmark_results_dynamic_16_peak.json',
            'static_16_mono': 'benchmark_results_static_16_mono.json',
            'dynamic_16_monop': 'benchmark_results_dynamic_16_monop.json',
        }

    file_patterns8 = {
            'static_16_1': 'benchmark_results_static_16_1.json',
            'dynamic_16_1': 'benchmark_results_dynamic_16_1.json',
            'dynamic_16_1p': 'benchmark_results_dynamic_16_1p.json',
            'static_16_2': 'benchmark_results_static_16_2.json',
            'dynamic_16_2': 'benchmark_results_dynamic_16_2.json',
            'dynamic_16_2p': 'benchmark_results_dynamic_16_2p.json',
            'static_16_3': 'benchmark_results_static_16_3.json',
            'dynamic_16_3': 'benchmark_results_dynamic_16_3.json',
            'dynamic_16_3p': 'benchmark_results_dynamic_16_3p.json',
        }
    
    # CSVをエクスポート
    success = export_to_csv(result_dir, output_file, file_patterns7)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
