#!/usr/bin/env python3
"""
ターミナル出力からNeuroCard推定値を抽出してJSON形式で保存する

使い方:
1. NeuroCardの実行ログをコピーしてテキストファイルに保存
2. このスクリプトを実行してJSON形式に変換
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict


def extract_estimates_from_log(log_content: str) -> Dict[int, float]:
    """
    ログからNeuroCard推定値を抽出
    
    フォーマット例:
    Query 1: Q(...):
      actual 1000 (0.000%)
    fact_psample_1000 263398 (err=263398.000)
    """
    estimates = {}
    
    # パターン: Query N: ... fact_psample_1000 <estimate>
    pattern = r'Query (\d+):.*?fact_psample_1000 (\d+(?:\.\d+)?)'
    
    for match in re.finditer(pattern, log_content, re.DOTALL):
        query_num = int(match.group(1))
        estimate = float(match.group(2))
        estimates[query_num] = estimate
    
    return estimates


def main():
    """メイン処理"""
    # 入力ファイル（ターミナル出力をコピーしたもの）
    input_file = Path(__file__).parent / "neurocard_execution_log.txt"
    
    # 出力ファイル（JSON形式）
    output_file = Path(__file__).parent / "neurocard_estimates.json"
    
    if not input_file.exists():
        print(f"❌ ログファイルが見つかりません: {input_file}")
        print()
        print("以下の手順で実行してください:")
        print("1. NeuroCardを実行:")
        print("   cd neurocard/neurocard")
        print("   source ../../venv/bin/activate")
        print(f"   WANDB_MODE=offline python run.py --run mv-queries-estimation --gpus 0 2>&1 | tee {input_file}")
        print()
        print("2. このスクリプトを実行:")
        print(f"   python {Path(__file__).name}")
        return
    
    print("📖 ログファイルを読み込み中...")
    with open(input_file, 'r', encoding='utf-8') as f:
        log_content = f.read()
    
    print("🔍 推定値を抽出中...")
    estimates = extract_estimates_from_log(log_content)
    
    if not estimates:
        print("❌ 推定値が見つかりませんでした")
        print("   ログファイルの内容を確認してください")
        return
    
    print(f"✅ {len(estimates)}件の推定値を抽出しました")
    print()
    print("最初の5件:")
    for query_num in sorted(estimates.keys())[:5]:
        print(f"  Query {query_num}: {estimates[query_num]:,.0f}")
    
    # JSON形式で保存
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(estimates, f, indent=2, ensure_ascii=False)
    
    print()
    print(f"💾 推定値を保存しました: {output_file}")


if __name__ == "__main__":
    main()
