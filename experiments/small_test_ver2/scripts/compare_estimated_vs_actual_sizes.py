#!/usr/bin/env python3
"""
EXPLAIN推定サイズと実測サイズの比較（SELECT * 変換後）

Phase 1でSELECT * 変換を行った後のEXPLAIN推定精度を検証します。
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

def load_costs(query_set: str = "job") -> Dict:
    """simple_migration_costs.jsonを読み込み"""
    costs_file = Path(__file__).parent.parent / "04_migration" / query_set / "simple_migration_costs.json"
    
    if not costs_file.exists():
        print(f"エラー: {costs_file} が見つかりません")
        sys.exit(1)
    
    with open(costs_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_actual_sizes(query_set: str = "job") -> Dict[str, int]:
    """root_nodes_actual_sizes.jsonを読み込み、クエリ名→実測サイズのマップを返す"""
    actual_file = Path(__file__).parent.parent / "04_migration" / query_set / "root_nodes_actual_sizes.json"
    
    if not actual_file.exists():
        print(f"エラー: {actual_file} が見つかりません")
        sys.exit(1)
    
    with open(actual_file, 'r', encoding='utf-8') as f:
        actual_list = json.load(f)
    
    # クエリ名→実測サイズのマップに変換
    return {item["query"]: item["actual_size"] for item in actual_list}

def get_root_node_id(query_name: str, query_set: str = "job") -> str:
    """EXPLAIN JSONファイルからルートノードIDを取得"""
    json_file = Path(__file__).parent.parent / "02_json" / query_set / f"{query_name}.json"
    
    if not json_file.exists():
        print(f"警告: {json_file} が見つかりません")
        return None
    
    with open(json_file, 'r', encoding='utf-8') as f:
        explain_data = json.load(f)
    
    # ルートノードのnode_idを取得
    if isinstance(explain_data, list) and len(explain_data) > 0:
        root_plan = explain_data[0]
        if "Plan" in root_plan:
            return root_plan["Plan"].get("node_id")
    
    return None

def compare_sizes(costs: Dict, actual_sizes: Dict[str, int], query_set: str = "job") -> List[Dict]:
    """推定サイズと実測サイズを比較"""
    comparisons = []
    
    for query_name, actual_size in actual_sizes.items():
        # 現在の02_json/からルートノードIDを取得
        root_node_id = get_root_node_id(query_name, query_set)
        
        if root_node_id is None:
            print(f"警告: {query_name} のルートノードIDが取得できません")
            continue
        
        # simple_migration_costs.jsonから推定サイズを取得
        if root_node_id not in costs:
            print(f"警告: {root_node_id} がcosts.jsonに見つかりません")
            continue
        
        node_costs = costs[root_node_id]
        
        # "[]"キー（依存MVなし）のサイズを取得
        if "[]" not in node_costs:
            print(f"警告: {root_node_id} に[]プランが見つかりません")
            continue
        
        estimated_size = node_costs["[]"]["size"]
        estimated_rows = node_costs["[]"]["rows"]
        estimated_width = node_costs["[]"]["width"]
        
        # 誤差を計算
        if actual_size > 0:
            ratio = estimated_size / actual_size
            error_percent = abs(estimated_size - actual_size) / actual_size * 100
        else:
            ratio = 0
            error_percent = 0
        
        comparisons.append({
            "query": query_name,
            "root_node_id": root_node_id,
            "estimated_size": estimated_size,
            "estimated_rows": estimated_rows,
            "estimated_width": estimated_width,
            "actual_size": actual_size,
            "ratio": ratio,
            "error_percent": error_percent,
            "diff": estimated_size - actual_size
        })
    
    return comparisons

def print_statistics(comparisons: List[Dict]):
    """統計情報を表示"""
    print("\n" + "="*80)
    print("推定サイズ vs 実測サイズ 比較結果（SELECT * 変換後）")
    print("="*80)
    
    # 全体統計
    total_queries = len(comparisons)
    total_estimated = sum(c["estimated_size"] for c in comparisons)
    total_actual = sum(c["actual_size"] for c in comparisons)
    avg_ratio = sum(c["ratio"] for c in comparisons) / total_queries if total_queries > 0 else 0
    avg_error = sum(c["error_percent"] for c in comparisons) / total_queries if total_queries > 0 else 0
    
    print(f"\n【全体統計】")
    print(f"  クエリ数: {total_queries}")
    print(f"  推定サイズ合計: {total_estimated:,} bytes ({total_estimated / (1024**2):.2f} MB)")
    print(f"  実測サイズ合計: {total_actual:,} bytes ({total_actual / (1024**2):.2f} MB)")
    print(f"  平均比率（推定/実測）: {avg_ratio:.2f}x")
    print(f"  平均誤差率: {avg_error:.2f}%")
    
    # 精度分類
    perfect = sum(1 for c in comparisons if 0.9 <= c["ratio"] <= 1.1)
    good = sum(1 for c in comparisons if 0.5 <= c["ratio"] <= 2.0)
    moderate = sum(1 for c in comparisons if 0.1 <= c["ratio"] <= 10.0)
    poor = total_queries - moderate
    
    print(f"\n【精度分類】")
    print(f"  ほぼ正確（0.9x - 1.1x）: {perfect}/{total_queries} ({perfect*100//total_queries}%)")
    print(f"  良好（0.5x - 2.0x）: {good}/{total_queries} ({good*100//total_queries}%)")
    print(f"  中程度（0.1x - 10.0x）: {moderate}/{total_queries} ({moderate*100//total_queries}%)")
    print(f"  要改善（< 0.1x or > 10x）: {poor}/{total_queries} ({poor*100//total_queries if total_queries > 0 else 0}%)")
    
    # 最も誤差が大きいクエリ
    print(f"\n【誤差が大きいクエリ Top 10】")
    sorted_by_error = sorted(comparisons, key=lambda x: x["error_percent"], reverse=True)[:10]
    
    print(f"{'クエリ':<10} {'ルートノード':<15} {'推定サイズ':<15} {'実測サイズ':<15} {'比率':<10} {'誤差率'}")
    print("-" * 80)
    for c in sorted_by_error:
        print(f"{c['query']:<10} {c['root_node_id']:<15} "
              f"{c['estimated_size']:>14,} {c['actual_size']:>14,} "
              f"{c['ratio']:>9.2f}x {c['error_percent']:>6.1f}%")
    
    # 最も精度が良いクエリ
    print(f"\n【最も精度が良いクエリ Top 10】")
    sorted_by_accuracy = sorted(comparisons, key=lambda x: abs(1.0 - x["ratio"]))[:10]
    
    print(f"{'クエリ':<10} {'ルートノード':<15} {'推定サイズ':<15} {'実測サイズ':<15} {'比率':<10} {'誤差率'}")
    print("-" * 80)
    for c in sorted_by_accuracy:
        print(f"{c['query']:<10} {c['root_node_id']:<15} "
              f"{c['estimated_size']:>14,} {c['actual_size']:>14,} "
              f"{c['ratio']:>9.2f}x {c['error_percent']:>6.1f}%")
    
    # 詳細リスト
    print(f"\n{'='*80}")
    print("詳細リスト（全クエリ）")
    print(f"{'='*80}")
    print(f"{'クエリ':<10} {'ルートノード':<15} {'行数':<12} {'幅':<8} {'推定サイズ':<15} {'実測サイズ':<15} {'比率':<10} {'誤差率'}")
    print("-" * 115)
    
    for c in sorted(comparisons, key=lambda x: x["query"]):
        print(f"{c['query']:<10} {c['root_node_id']:<15} "
              f"{c['estimated_rows']:>11,} {c['estimated_width']:>7,} "
              f"{c['estimated_size']:>14,} {c['actual_size']:>14,} "
              f"{c['ratio']:>9.2f}x {c['error_percent']:>6.1f}%")
    
    print(f"\n{'='*80}\n")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="EXPLAIN推定サイズと実測サイズの比較")
    parser.add_argument(
        "--query-set",
        type=str,
        default="job",
        help="クエリセット名（デフォルト: job）"
    )
    
    args = parser.parse_args()
    
    # データ読み込み
    print(f"クエリセット: {args.query_set}")
    costs = load_costs(args.query_set)
    actual_sizes = load_actual_sizes(args.query_set)
    
    # 比較
    comparisons = compare_sizes(costs, actual_sizes, args.query_set)
    
    # 統計表示
    print_statistics(comparisons)
    
    # JSON出力
    output_file = Path(__file__).parent.parent / "04_migration" / args.query_set / "size_comparison_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(comparisons, f, indent=2, ensure_ascii=False)
    
    print(f"詳細結果を保存: {output_file}")

if __name__ == "__main__":
    main()
