#!/usr/bin/env python3
"""
ベンチマーク結果の総実行時間をCSVにエクスポートするスクリプト

各手法の総実行時間（全タイムステップの合計）を抽出し、
手法ごとに1行でCSVファイルを生成します。

使い方:
    python export_total_time_to_csv.py [結果ディレクトリ] [出力CSVファイル名]
    
    例:
    python export_total_time_to_csv.py \
        experiments/small_test_ver2/time_dependent_output/job/result_1G \
        total_execution_times.csv
"""

import json
import csv
import sys
from pathlib import Path
from typing import Dict, Tuple, Optional


def load_benchmark_total_time(file_path: Path) -> Tuple[float, float, float]:
    """
    ベンチマーク結果JSONファイルを読み込み、総実行時間を返す
    
    Args:
        file_path: ベンチマーク結果JSONファイルのパス
    
    Returns:
        3つの値のタプル:
        - total_time: 全タイムステップのtotal_time合計（マイグレーション/MV作成時間を含む）
        - query_only_time: マイグレーション/MV作成時間を除いた時間
        - migration_time: マイグレーション/MV作成時間の合計
    """
    with open(file_path, 'r') as f:
        data = json.load(f)
    
    total_time = 0.0
    migration_time = 0.0
    
    # 静的ベンチマークの場合、初期MV作成時間を取得
    initial_mv_creation_time = data.get('initial_mv_creation_time', 0.0)
    migration_time += initial_mv_creation_time
    total_time += initial_mv_creation_time
    
    for ts_result in data['timestep_results']:
        total_time += ts_result['total_time']
        
        # マイグレーション時間を取得（存在しない場合は0）
        if 'migration' in ts_result and isinstance(ts_result['migration'], dict):
            migration_time += ts_result['migration'].get('time', 0.0)
    
    query_only_time = total_time - migration_time
    
    return total_time, query_only_time, migration_time


def export_total_time_to_csv(
    result_dir: Path, 
    output_file: Path, 
    file_patterns: Optional[Dict[str, str]] = None
) -> bool:
    """
    複数のベンチマーク結果の総実行時間をCSVにエクスポート
    
    Args:
        result_dir: ベンチマーク結果が格納されているディレクトリ
        output_file: 出力CSVファイルのパス
        file_patterns: {手法名: ファイル名パターン} の辞書。Noneの場合はデフォルトパターンを使用
    
    Returns:
        成功した場合はTrue
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
    
    # 各手法の総実行時間を収集
    results: Dict[str, Dict[str, float]] = {}
    
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
            total_time, query_only_time, migration_time = load_benchmark_total_time(file_path)
            results[method_name] = {
                'total_time': total_time,
                'query_only_time': query_only_time,
                'migration_time': migration_time
            }
            print(f"✓ Loaded {method_name}: total={total_time:.2f}s, query={query_only_time:.2f}s, migration={migration_time:.2f}s ({file_path.name})")
        except Exception as e:
            print(f"✗ Failed to load {method_name}: {e}")
            continue
    
    if not results:
        print("エラー: 有効なベンチマーク結果ファイルが見つかりませんでした")
        return False
    
    # CSVに書き出し
    methods = sorted(results.keys())
    
    with open(output_file, 'w', newline='') as csvfile:
        # ヘッダー: method, total_time, query_only_time, migration_time
        fieldnames = ['method', 'total_time', 'query_only_time', 'migration_time']
        
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        # 各手法の行を書き込み
        for method in methods:
            row = {
                'method': method,
                'total_time': results[method]['total_time'],
                'query_only_time': results[method]['query_only_time'],
                'migration_time': results[method]['migration_time']
            }
            writer.writerow(row)
    
    print(f"\n✓ CSV saved to: {output_file}")
    print(f"  Methods: {len(methods)}")
    print(f"  Methods included: {', '.join(methods)}")
    
    # 横型のCSVも出力（手法を列に）
    horizontal_file = output_file.parent / (output_file.stem + "_horizontal" + output_file.suffix)
    _write_horizontal_csv(horizontal_file, methods, results)
    
    return True


def _write_horizontal_csv(
    output_file: Path,
    methods: list,
    results: Dict[str, Dict[str, float]]
):
    """
    横型のCSVファイルを書き出すヘルパー関数（手法を列に、時間の種類を行に）
    
    Args:
        output_file: 出力CSVファイルのパス
        methods: 手法名のリスト
        results: {method_name: {time_type: value}} のデータ
    """
    with open(output_file, 'w', newline='') as csvfile:
        # ヘッダー: time_type, method1, method2, ...
        fieldnames = ['time_type'] + methods
        
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        # 各時間種類の行を書き込み
        for time_type in ['total_time', 'query_only_time', 'migration_time']:
            row = {'time_type': time_type}
            for method in methods:
                row[method] = results[method][time_type]
            writer.writerow(row)
    
    print(f"✓ Horizontal CSV saved to: {output_file}")


def main():
    """メイン関数"""
    # コマンドライン引数の処理
    if len(sys.argv) < 2:
        # デフォルトのパス
        result_dir = Path('experiments/small_test_ver2/time_dependent_output/job/result_500M_originalcost_10')
        output_filename = 'total_execution_times.csv'
    elif len(sys.argv) == 2:
        result_dir = Path(sys.argv[1])
        output_filename = 'total_execution_times.csv'
    else:
        result_dir = Path(sys.argv[1])
        output_filename = sys.argv[2]
    
    # 出力ファイルのパス
    output_file = result_dir / output_filename
    
    print(f"=== Benchmark Total Time CSV Exporter ===")
    print(f"Result directory: {result_dir}")
    print(f"Output file: {output_file}")
    print()
    
    # ディレクトリの存在確認
    if not result_dir.exists():
        print(f"エラー: ディレクトリが見つかりません: {result_dir}")
        sys.exit(1)

    # ファイルパターン定義（export_benchmark_to_csv.pyと同様）
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
    
    # CSVをエクスポート（file_patterns6を使用）
    success = export_total_time_to_csv(result_dir, output_file, file_patterns7)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
