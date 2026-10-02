#!/usr/bin/env python3
"""
MVサイズ分析スクリプト
"""

import json
from pathlib import Path


def analyze_mv_sizes():
    """MVのサイズを分析"""

    result_file = Path("experiments/small_test/time_dependent_output/normal_morning_result.json")

    if not result_file.exists():
        print("結果ファイルが見つかりません")
        return

    with open(result_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print("各MVのサイズ分析:")
    print("=" * 60)

    total_size = 0
    sizes = []

    for mv in data['selected_views']:
        size = mv['size']
        sizes.append(size)
        total_size += size

        kb_size = size / 1024
        print("12")

    print("\n" + "=" * 60)
    print(f"総サイズ: {total_size:,} bytes ({total_size/1024:,.2f} KB, {total_size/(1024*1024):.4f} MB)")
    print(f"MV数: {len(sizes)}")
    print(f"平均サイズ: {total_size/len(sizes):,.0f} bytes ({total_size/len(sizes)/1024:.2f} KB)")

    # サイズ分布
    print("\nサイズ分布:")
    small = len([s for s in sizes if s < 1000])    # 1KB未満
    medium = len([s for s in sizes if 1000 <= s < 10000])  # 1KB-10KB
    large = len([s for s in sizes if s >= 10000])   # 10KB以上

    print(f"  小サイズ (1KB未満): {small}個")
    print(f"  中サイズ (1-10KB): {medium}個")
    print(f"  大サイズ (10KB以上): {large}個")


if __name__ == "__main__":
    analyze_mv_sizes()