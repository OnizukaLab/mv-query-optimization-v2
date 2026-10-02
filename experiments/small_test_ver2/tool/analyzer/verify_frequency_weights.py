#!/usr/bin/env python3
"""頻度重み付け最適化の検証スクリプト

利得に頻度の重みが正しく適用されているかを確認します。
"""

import sys
from pathlib import Path
import pickle
import json

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def verify_frequency_weighted_optimization():
    """頻度重み付け最適化の検証"""
    print("=" * 70)
    print("頻度重み付け最適化の検証")
    print("=" * 70)
    
    # パース結果を読み込み
    pickle_path = Path(__file__).parent / "qp_class.pkl"
    
    if not pickle_path.exists():
        print(f"\n✗ エラー: {pickle_path} が見つかりません")
        print("  先に phase2 を実行してください:")
        print("  python experiments/small_test/run_experiment.py --phase 2")
        return
    
    with open(pickle_path, 'rb') as f:
        qp = pickle.load(f)
    
    print(f"\n✓ パース結果を読み込み: {pickle_path}")
    
    # 頻度情報を確認
    freq_file = Path(__file__).parent / "01_queries" / "frequency.json"
    if freq_file.exists():
        with open(freq_file, 'r') as f:
            frequencies = json.load(f)
        
        print(f"\n✓ 頻度情報:")
        total_freq = 0
        for query, freq in frequencies.items():
            print(f"  {query}: {freq}回")
            total_freq += freq
        print(f"  総実行回数: {total_freq}")
    else:
        print(f"\n✗ 頻度情報ファイルが見つかりません: {freq_file}")
        frequencies = {}
    
    # u_ij の統計を表示
    print(f"\n✓ 利得行列 (u_ij) の統計:")
    print(f"  クエリ数: {len(qp.u_ij)}")
    print(f"  ノード数: {len(qp.u_ij[0]) if qp.u_ij else 0}")
    
    # 各クエリの総利得を計算
    print(f"\n  各クエリの総利得:")
    for i, u_row in enumerate(qp.u_ij):
        total_utility = sum(u_row)
        non_zero_count = sum(1 for u in u_row if u > 0)
        print(f"    Query {i}: 総利得={total_utility:.2f}, 非ゼロノード数={non_zero_count}")
    
    # U_max を表示
    print(f"\n  総利得 (U_max): {qp.U_max:.2f}")
    
    # トップ10の高利得ノードを表示
    node_utilities = []
    for j in range(len(qp.U_j_max)):
        if qp.U_j_max[j] > 0:
            node_utilities.append((qp.node_list[j], qp.U_j_max[j]))
    
    node_utilities.sort(key=lambda x: x[1], reverse=True)
    
    print(f"\n  トップ10高利得ノード:")
    for i, (node_id, utility) in enumerate(node_utilities[:10], 1):
        print(f"    {i}. {node_id}: {utility:.2f}")
    
    # メンテナンスコストの確認
    total_m_cost = sum(qp.m_cost)
    non_zero_m_cost = sum(1 for c in qp.m_cost if c > 0)
    
    print(f"\n✓ メンテナンスコスト:")
    print(f"  総コスト: {total_m_cost:.6f}")
    print(f"  非ゼロノード数: {non_zero_m_cost}/{len(qp.m_cost)}")
    
    if qp.settings.optimization.insert_queries == 0:
        print(f"  → INSERT考慮なし（insert_queries=0）")
    else:
        print(f"  → INSERT考慮あり（insert_queries={qp.settings.optimization.insert_queries}）")
    
    # 頻度重み付けの効果を検証
    print(f"\n" + "=" * 70)
    print("頻度重み付けの効果検証")
    print("=" * 70)
    
    if frequencies:
        freq_values = list(frequencies.values())
        max_freq = max(freq_values)
        min_freq = min(freq_values)
        freq_ratio = max_freq / min_freq if min_freq > 0 else 0
        
        print(f"\n頻度の範囲:")
        print(f"  最小頻度: {min_freq}")
        print(f"  最大頻度: {max_freq}")
        print(f"  頻度比率: {freq_ratio:.1f}x")
        
        # 利得の範囲を確認
        all_utilities = [u for row in qp.u_ij for u in row if u > 0]
        if all_utilities:
            max_util = max(all_utilities)
            min_util = min(all_utilities)
            util_ratio = max_util / min_util if min_util > 0 else 0
            
            print(f"\n利得の範囲:")
            print(f"  最小利得: {min_util:.2f}")
            print(f"  最大利得: {max_util:.2f}")
            print(f"  利得比率: {util_ratio:.1f}x")
            
            if util_ratio >= freq_ratio * 0.8:
                print(f"\n✓ 頻度の重み付けが反映されています")
                print(f"  （利得比率 {util_ratio:.1f}x ≈ 頻度比率 {freq_ratio:.1f}x）")
            else:
                print(f"\n⚠ 頻度の重み付けが不十分の可能性があります")
                print(f"  （利得比率 {util_ratio:.1f}x < 頻度比率 {freq_ratio:.1f}x）")
    
    print("\n" + "=" * 70)
    print("✅ 検証完了")
    print("=" * 70)
    
    print("\n次のステップ:")
    print("  1. 最適化を実行:")
    print("     python experiments/small_test/run_experiment.py --phase 3")
    print("  2. 結果を確認:")
    print("     cat experiments/small_test/Output/normal_result.json")


if __name__ == "__main__":
    verify_frequency_weighted_optimization()
