#!/usr/bin/env python3
"""
異なる容量制約でMV選択がどう変わるかをテストするスクリプト
"""

import json
from pathlib import Path


def analyze_mv_selection_sensitivity():
    """容量制約とMV選択の関係を分析"""

    result_file = Path("experiments/small_test_ver2/time_dependent_output/normal_morning_result.json")

    if not result_file.exists():
        print("結果ファイルが見つかりません")
        return

    with open(result_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print("=" * 70)
    print("MV容量制約の感度分析")
    print("=" * 70)

    # 各MVのサイズと利得（朝の頻度での）
    mvs = []
    for mv in data['selected_views']:
        size = mv['size']
        node_id = mv['node_id']
        mvs.append({'node_id': node_id, 'size': size})

    # サイズでソート
    mvs_sorted = sorted(mvs, key=lambda x: x['size'], reverse=True)

    print("\nMVサイズ一覧（降順）:")
    print(f"{'ノードID':<15} {'サイズ(bytes)':<15} {'サイズ(KB)':<15} {'累積(KB)':<15}")
    print("-" * 70)

    cumulative_size = 0
    for i, mv in enumerate(mvs_sorted, 1):
        cumulative_size += mv['size']
        print(f"{mv['node_id']:<15} {mv['size']:<15} {mv['size']/1024:<15.2f} {cumulative_size/1024:<15.2f}")

    total_size = sum(mv['size'] for mv in mvs)

    print("\n" + "=" * 70)
    print("推奨される容量制約設定:")
    print("=" * 70)

    # 異なる制約レベルでの選択可能MV数を計算
    constraints = [
        (0.002, "2KB - 極小", "最小限のMVのみ"),
        (0.003, "3KB - 小", "重要なMVのみ"),
        (0.005, "5KB - 中", "半分程度のMV"),
        (0.008, "8KB - 大", "大半のMV"),
        (0.010, "10KB - 最大", "全MVが選択可能"),
    ]

    print("\n制約値でMV選択がどう変わるか:")
    print(f"{'制約値':<20} {'選択可能MV数':<15} {'説明':<30}")
    print("-" * 70)

    for limit_mb, label, description in constraints:
        limit_bytes = limit_mb * 1024 * 1024
        count = 0
        temp_size = 0

        for mv in mvs_sorted:
            if temp_size + mv['size'] <= limit_bytes:
                temp_size += mv['size']
                count += 1
            else:
                break

        print(f"{label:<20} {count:<15} {description:<30}")

    print("\n" + "=" * 70)
    print("💡 推奨:")
    print("=" * 70)
    print("頻度によって異なるMVを選択させるには、以下の制約が適切です:\n")
    print("1. **5-7KB制約**: 約5-7個のMVを選択")
    print("   - 朝と夕方で一部のMVが変わる可能性")
    print("   - config.yamlのstorage_limit_mbを0.005-0.007に設定\n")
    print("2. **3-4KB制約**: 約3-4個のMVを選択")
    print("   - 頻度の違いがより顕著に")
    print("   - config.yamlのstorage_limit_mbを0.003-0.004に設定\n")
    print("3. **2KB以下**: 約1-2個のMVのみ選択")
    print("   - 最も重要なMVのみが選択される")
    print("   - config.yamlのstorage_limit_mbを0.002以下に設定\n")

    print("\n現在の設定:")
    config_path = Path("experiments/small_test_ver2/config.yaml")
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            for line in f:
                if 'storage_limit_mb' in line or 'storage_limit_bytes' in line:
                    print(f"  {line.strip()}")


if __name__ == "__main__":
    analyze_mv_selection_sensitivity()
