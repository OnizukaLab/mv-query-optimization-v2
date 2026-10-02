#!/usr/bin/env python3
"""
全MV候補のサイズと利得を分析し、最適な容量制約を提案
"""

import pickle
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def analyze_all_mv_candidates():
    """全MV候補を分析"""

    print("=" * 70)
    print("全MV候補の分析")
    print("=" * 70)

    # パース結果を読み込み
    morning_pkl = Path("experiments/small_test/time_dependent_output/qp_morning.pkl")
    evening_pkl = Path("experiments/small_test/time_dependent_output/qp_evening.pkl")

    if not morning_pkl.exists() or not evening_pkl.exists():
        print("パース結果が見つかりません")
        return

    with open(morning_pkl, 'rb') as f:
        qp_morning = pickle.load(f)

    with open(evening_pkl, 'rb') as f:
        qp_evening = pickle.load(f)

    # 各MVの情報を収集
    print("\n朝の時間帯のMV候補:")
    print(f"{'ノードID':<15} {'サイズ(B)':<12} {'サイズ(KB)':<12} {'利得':<12}")
    print("-" * 70)

    morning_mvs = []
    total_size_morning = 0

    for j, node_id in enumerate(qp_morning.node_list):
        size = qp_morning.b_j[j]
        # 各クエリからの利得を合計
        utility = sum(qp_morning.u_ij[i][j] for i in range(len(qp_morning.query)))

        morning_mvs.append({
            'node_id': node_id,
            'size': size,
            'utility': utility,
            'efficiency': utility / size if size > 0 else 0
        })
        total_size_morning += size

        print(f"{node_id:<15} {size:<12} {size/1024:<12.2f} {utility:<12.2f}")

    print(f"\n総サイズ: {total_size_morning} bytes ({total_size_morning/1024:.2f} KB, {total_size_morning/(1024*1024):.4f} MB)")

    print("\n" + "=" * 70)
    print("夕方の時間帯のMV候補:")
    print(f"{'ノードID':<15} {'サイズ(B)':<12} {'サイズ(KB)':<12} {'利得':<12}")
    print("-" * 70)

    evening_mvs = []
    total_size_evening = 0

    for j, node_id in enumerate(qp_evening.node_list):
        size = qp_evening.b_j[j]
        utility = sum(qp_evening.u_ij[i][j] for i in range(len(qp_evening.query)))

        evening_mvs.append({
            'node_id': node_id,
            'size': size,
            'utility': utility,
            'efficiency': utility / size if size > 0 else 0
        })
        total_size_evening += size

        print(f"{node_id:<15} {size:<12} {size/1024:<12.2f} {utility:<12.2f}")

    print(f"\n総サイズ: {total_size_evening} bytes ({total_size_evening/1024:.2f} KB, {total_size_evening/(1024*1024):.4f} MB)")

    # 効率性でソート（利得/サイズ）
    print("\n" + "=" * 70)
    print("朝の時間帯: 効率性ランキング（利得/サイズ）")
    print("=" * 70)
    print(f"{'順位':<6} {'ノードID':<15} {'効率性':<12} {'利得':<12} {'サイズ(KB)':<12}")
    print("-" * 70)

    morning_sorted = sorted(morning_mvs, key=lambda x: x['efficiency'], reverse=True)
    for i, mv in enumerate(morning_sorted[:10], 1):
        print(f"{i:<6} {mv['node_id']:<15} {mv['efficiency']:<12.2f} {mv['utility']:<12.2f} {mv['size']/1024:<12.2f}")

    print("\n" + "=" * 70)
    print("夕方の時間帯: 効率性ランキング（利得/サイズ）")
    print("=" * 70)
    print(f"{'順位':<6} {'ノードID':<15} {'効率性':<12} {'利得':<12} {'サイズ(KB)':<12}")
    print("-" * 70)

    evening_sorted = sorted(evening_mvs, key=lambda x: x['efficiency'], reverse=True)
    for i, mv in enumerate(evening_sorted[:10], 1):
        print(f"{i:<6} {mv['node_id']:<15} {mv['efficiency']:<12.2f} {mv['utility']:<12.2f} {mv['size']/1024:<12.2f}")

    # 推奨容量制約の計算
    print("\n" + "=" * 70)
    print("💡 推奨容量制約")
    print("=" * 70)

    # 累積サイズを計算して、どのレベルで選択が変わるかを見る
    cumulative_morning = 0
    cumulative_evening = 0

    print("\n朝の時間帯で効率的なMVを選択する場合:")
    print(f"{'選択MV数':<12} {'累積サイズ(KB)':<18} {'推奨制約(KB)':<18} {'推奨制約(MB)':<18}")
    print("-" * 70)

    for i in range(1, min(len(morning_sorted), 10) + 1):
        cumulative_morning += morning_sorted[i-1]['size']
        # 余裕を持たせて1.2倍
        recommended_kb = (cumulative_morning / 1024) * 1.2
        recommended_mb = recommended_kb / 1024
        print(f"{i:<12} {cumulative_morning/1024:<18.2f} {recommended_kb:<18.2f} {recommended_mb:<18.4f}")

    print("\n" + "=" * 70)
    print("🎯 結論: 頻度で選択を変えるための推奨設定")
    print("=" * 70)

    # 朝と夕方のトップ5を比較
    morning_top5 = set(mv['node_id'] for mv in morning_sorted[:5])
    evening_top5 = set(mv['node_id'] for mv in evening_sorted[:5])
    
    different = morning_top5.symmetric_difference(evening_top5)

    print(f"\n朝のトップ5: {', '.join([mv['node_id'] for mv in morning_sorted[:5]])}")
    print(f"夕方のトップ5: {', '.join([mv['node_id'] for mv in evening_sorted[:5]])}")
    print(f"\n異なるMV: {', '.join(different) if different else '同じMVが選ばれる'}")

    if different:
        # 5個選択するのに必要なサイズ
        size_for_5_morning = sum(mv['size'] for mv in morning_sorted[:5]) / 1024
        size_for_5_evening = sum(mv['size'] for mv in evening_sorted[:5]) / 1024
        avg_size = (size_for_5_morning + size_for_5_evening) / 2

        print(f"\n選択を変えるための推奨制約:")
        print(f"  - 3-5個のMVを選択: {avg_size*0.8:.3f} - {avg_size*1.2:.3f} KB")
        print(f"  - config.yamlに設定: storage_limit_mb: {avg_size*1.0/1024:.6f}")
    else:
        # より厳しい制約が必要
        size_for_3_morning = sum(mv['size'] for mv in morning_sorted[:3]) / 1024
        print(f"\n選択を変えるにはより厳しい制約が必要:")
        print(f"  - 2-3個のMVを選択: {size_for_3_morning*0.8:.3f} - {size_for_3_morning*1.2:.3f} KB")
        print(f"  - config.yamlに設定: storage_limit_mb: {size_for_3_morning*1.0/1024:.6f}")


if __name__ == "__main__":
    analyze_all_mv_candidates()
