#!/usr/bin/env python3
"""クエリパース機能のテストスクリプト

物理プランのパースが正しく動作するかを確認します。
"""
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from src.core.query_parser import QueryParser


def test_query_parse():
    """クエリパースのテスト"""
    print("=" * 60)
    print("クエリパーステスト")
    print("=" * 60)
    
    # 設定の読み込み
    settings = Settings()
    print(f"\n✓ 設定ファイル読み込み完了")
    print(f"  - クエリディレクトリ: {settings.benchmark.queries_dir}")
    print(f"  - ワークロードディレクトリ: {settings.benchmark.workloads_dir}")
    print(f"  - ベンチマークタイプ: {settings.benchmark.type}")
    
    # QueryParserの初期化
    print(f"\n✓ QueryParserを初期化中...")
    qp = QueryParser(settings)
    
    # クエリのパース実行
    print(f"\n✓ クエリをパース中...")
    query_path = settings.benchmark.queries_dir
    q_num = 0  # 実際のクエリ数は自動計算
    insert_query = 1  # デフォルト値
    
    try:
        qp.query_parse(q_num, query_path, insert_query)
        print(f"\n✓ パース完了！")
        
        # パース結果のサマリー表示
        print("\n" + "=" * 60)
        print("パース結果サマリー")
        print("=" * 60)
        
        print(f"\n📊 ノード統計:")
        print(f"  - リーフノード数: {len(qp.qm.leaf_nodes_map)}")
        print(f"  - 非リーフノード数: {len(qp.qm.non_leaf_nodes_map)}")
        print(f"  - 総ノード数 (s_num): {qp.s_num}")
        
        print(f"\n📝 クエリ統計:")
        print(f"  - パースされたクエリ数: {len(qp.query)}")
        
        if qp.node_list:
            print(f"\n🔗 ノードリスト (最初の10個):")
            for i, node in enumerate(qp.node_list[:10]):
                print(f"  [{i}] {node}")
            if len(qp.node_list) > 10:
                print(f"  ... 他 {len(qp.node_list) - 10} 個")
        
        print(f"\n💾 ストレージ情報:")
        if qp.b_j:
            total_size = sum(qp.b_j)
            print(f"  - 総サイズ: {total_size:,} bytes ({total_size / (1024*1024):.2f} MB)")
            print(f"  - 平均ノードサイズ: {total_size / len(qp.b_j):,.0f} bytes")
        
        print(f"\n⚡ コスト情報:")
        if qp.m_cost:
            total_mcost = sum(qp.m_cost)
            print(f"  - 総メンテナンスコスト: {total_mcost:,.2f}")
            print(f"  - 平均メンテナンスコスト: {total_mcost / len(qp.m_cost):.2f}")
        
        if qp.U_j_max:
            total_utility = sum(qp.U_j_max)
            print(f"  - 総最大ユーティリティ: {total_utility:,.2f}")
            print(f"  - 平均ユーティリティ: {total_utility / len(qp.U_j_max):.2f}")
        
        print(f"\n📋 テーブル情報:")
        if qp.qm.relation_tables:
            tables = set(qp.qm.relation_tables.values())
            print(f"  - 使用されているテーブル数: {len(tables)}")
            print(f"  - テーブルリスト: {', '.join(sorted(list(tables)[:10]))}")
            if len(tables) > 10:
                print(f"    ... 他 {len(tables) - 10} 個")
        
        print("\n" + "=" * 60)
        print("✅ クエリパーステスト成功！")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_query_parse()
    sys.exit(0 if success else 1)
