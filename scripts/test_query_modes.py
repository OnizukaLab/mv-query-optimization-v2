#!/usr/bin/env python3
"""クエリ選択モードのテストスクリプト

RedBenchモードと全JOBクエリモードの両方をテストします。
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings, BenchmarkConfig
from src.core.query_parser import QueryParser


def test_mode(mode: str):
    """指定されたモードでクエリパースをテスト"""
    print("=" * 70)
    print(f"クエリパーステスト - モード: {mode}")
    print("=" * 70)
    
    # 設定の読み込みとモード変更
    settings = Settings()
    settings.benchmark.query_selection_mode = mode
    
    print(f"\n✓ 設定:")
    print(f"  - クエリ選択モード: {settings.benchmark.query_selection_mode}")
    print(f"  - クエリディレクトリ: {settings.benchmark.queries_dir}")
    print(f"  - ワークロードディレクトリ: {settings.benchmark.workloads_dir}")
    
    # QueryParserの初期化
    qp = QueryParser(settings)
    
    # クエリのパース実行
    print(f"\n✓ パース中...")
    query_path = settings.benchmark.queries_dir
    
    try:
        qp.query_parse(0, query_path, 1)
        
        # 結果表示
        print(f"\n📊 パース結果:")
        print(f"  - パースされたクエリ数: {len(qp.query)}")
        print(f"  - リーフノード数: {len(qp.qm.leaf_nodes_map)}")
        print(f"  - 非リーフノード数: {len(qp.qm.non_leaf_nodes_map)}")
        print(f"  - 総ノード数: {qp.s_num}")
        
        if qp.b_j:
            total_size = sum(qp.b_j)
            print(f"  - 総ストレージサイズ: {total_size / (1024*1024):.2f} MB")
        
        return True
        
    except Exception as e:
        print(f"\n❌ エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """両方のモードをテスト"""
    print("\n" + "=" * 70)
    print("クエリ選択モード比較テスト")
    print("=" * 70)
    
    # RedBenchモードのテスト
    print("\n\n[1/2] RedBenchワークロードベースのクエリ選択")
    success1 = test_mode("redbench")
    
    # 全JOBモードのテスト
    print("\n\n[2/2] 全JOBクエリの使用")
    success2 = test_mode("all_job")
    
    # 比較結果
    print("\n\n" + "=" * 70)
    print("テスト結果サマリー")
    print("=" * 70)
    print(f"  RedBenchモード: {'✅ 成功' if success1 else '❌ 失敗'}")
    print(f"  全JOBモード: {'✅ 成功' if success2 else '❌ 失敗'}")
    print("\n💡 ヒント:")
    print("  - RedBenchモード: 実験で使われる83個のクエリのみ（頻度情報あり）")
    print("  - 全JOBモード: dataset/RED_JSON/job/ の全113個のクエリ（頻度=1）")
    print("\n  config/default.yaml で query_selection_mode を変更できます:")
    print("    query_selection_mode: redbench  # または all_job")
    print("=" * 70)
    
    return success1 and success2


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
