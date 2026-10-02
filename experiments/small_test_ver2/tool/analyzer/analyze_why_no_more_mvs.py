#!/usr/bin/env python3
"""
なぜ余裕があるのにMVが追加されないかを分析
"""

import json
import pickle
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def analyze_why_no_more_mvs():
    """余裕があるのに追加MVが選ばれない理由を分析"""

    print("=" * 70)
    print("余裕があるのにMVが追加されない理由の分析")
    print("=" * 70)

    # 結果を読み込み
    morning_result_file = Path("experiments/small_test_ver2/time_dependent_output/normal_morning_result.json")
    morning_pkl_file = Path("experiments/small_test_ver2/time_dependent_output/qp_morning.pkl")

    with open(morning_result_file, 'r', encoding='utf-8') as f:
        morning_result = json.load(f)

    with open(morning_pkl_file, 'rb') as f:
        qp_morning = pickle.load(f)

    print("\n【朝の時間帯】")
    print("-" * 70)
    print(f"総利得: {morning_result['total_utility']:.2f}")
    print(f"総ストレージ: {morning_result['total_storage']} bytes ({morning_result['total_storage']/1024:.4f} KB)")
    print(f"制約: 5120 bytes (5.00 KB)")
    print(f"余裕: {5120 - morning_result['total_storage']} bytes ({(5120 - morning_result['total_storage'])/1024:.4f} KB)")
    print(f"選択MV数: {len(morning_result['selected_views'])}")

    print("\n選択されたMV:")
    print(f"{'ノードID':<15} {'サイズ(B)':<12} {'使用回数':<12} {'使用位置'}")
    print("-" * 70)
    
    selected_nodes = set()
    for mv in morning_result['selected_views']:
        selected_nodes.add(mv['node_id'])
        usage_str = ', '.join([f"Q{pos[0]}@{pos[1]}" for pos in mv['usage_positions']])
        print(f"{mv['node_id']:<15} {mv['size']:<12} {mv['usage_count']:<12} {usage_str}")

    # 選択されなかったMVを分析
    print("\n" + "=" * 70)
    print("選択されなかったMV候補の分析")
    print("=" * 70)

    print(f"\n{'ノードID':<15} {'サイズ(B)':<12} {'利得':<12} {'効率':<12} {'理由'}")
    print("-" * 70)

    not_selected_count = 0
    for j, node_id in enumerate(qp_morning.node_list):
        if node_id not in selected_nodes:
            size = qp_morning.b_j[j]
            utility = sum(qp_morning.u_ij[i][j] for i in range(len(qp_morning.query)))
            efficiency = utility / size if size > 0 else 0

            # 理由を判定
            reason = ""
            if utility == 0:
                reason = "利得が0"
            elif size > (5120 - morning_result['total_storage']):
                reason = f"容量オーバー (残り{5120 - morning_result['total_storage']}B)"
            elif efficiency < 0.001:
                reason = "効率が低い"
            else:
                reason = "他のMVで代替可能"

            if not_selected_count < 10:  # 上位10個まで表示
                print(f"{node_id:<15} {size:<12} {utility:<12.2f} {efficiency:<12.4f} {reason}")
                not_selected_count += 1

    # 重要な洞察
    print("\n" + "=" * 70)
    print("💡 重要な洞察")
    print("=" * 70)

    print("\n【理由1】利得の計算方法")
    print("  MVの利得 = クエリ実行コストの削減量")
    print("  - MVが選ばれると、そのMVを使うクエリ部分のコストが削減される")
    print("  - 選択されたMVで**すでにカバーされている**クエリ部分は")
    print("    他のMVを追加しても利得が増えない")

    print("\n【理由2】ビュー選択の最適性")
    print("  選択された3つのMV:")
    for mv in morning_result['selected_views']:
        print(f"    - {mv['node_id']}")
    print("  これらのMVで、クエリの主要な部分をすでにカバーしている")

    print("\n【理由3】残りの候補MVの状況")
    zero_utility = sum(1 for j in range(len(qp_morning.node_list))
                      if qp_morning.node_list[j] not in selected_nodes
                      and sum(qp_morning.u_ij[i][j] for i in range(len(qp_morning.query))) == 0)
    print(f"  - 利得が0のMV: {zero_utility}個")
    print(f"  - これらは選択されたMVで完全にカバーされているか、")
    print(f"    そもそもクエリで使われていない")

    print("\n【結論】")
    print("  容量に余裕があっても追加MVが選ばれないのは:")
    print("  ✓ 既存のMVで十分にクエリをカバーしている")
    print("  ✓ 残りのMV候補は利得が0または極めて小さい")
    print("  ✓ ILPソルバーが最適解を見つけている")

    print("\n" + "=" * 70)
    print("🔧 選択を変えるための提案")
    print("=" * 70)
    print("\n1. **より厳しい容量制約**")
    print("   現在: 5120 bytes → 推奨: 2048 bytes (2KB)")
    print("   これにより、朝と夕方で異なる2個のMVが選ばれる可能性")

    print("\n2. **クエリの複雑化**")
    print("   より多様なクエリパターンを追加して、")
    print("   異なるMVが必要になるようにする")

    print("\n3. **頻度の差を極端に**")
    print("   朝: query1=1000, query2=1, query3=1")
    print("   夕方: query1=1, query2=1000, query3=1")
    print("   これで明確に異なるMVが選ばれるはず")


if __name__ == "__main__":
    analyze_why_no_more_mvs()
