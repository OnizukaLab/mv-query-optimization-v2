#!/usr/bin/env python3
"""ILP最適化機能のテストスクリプト

クエリパース後、ILP最適化が正常に実行できるかを確認します。
"""
import sys
import time
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from src.core.query_parser import QueryParser
from src.optimization.factory import OptimizerFactory


def test_optimization(algorithm: str = "bigsubs"):
    """指定されたアルゴリズムで最適化をテスト"""
    print("=" * 70)
    print(f"ILP最適化テスト - アルゴリズム: {algorithm}")
    print("=" * 70)
    
    # 設定の読み込み
    settings = Settings()
    print(f"\n✓ 設定読み込み完了")
    print(f"  - ストレージ制限: {settings.optimization.storage_limit_mb} MB")
    print(f"  - クエリ選択モード: {settings.benchmark.query_selection_mode}")
    
    # ステップ1: クエリパース
    print(f"\n[1/2] クエリをパース中...")
    qp = QueryParser(settings)
    query_path = settings.benchmark.queries_dir
    
    try:
        qp.query_parse(0, query_path, 1)
        print(f"  ✓ {len(qp.query)}個のクエリをパース完了")
        print(f"  ✓ {qp.s_num}個のノードを抽出")
    except Exception as e:
        print(f"  ❌ パースエラー: {e}")
        return False
    
    # ステップ2: ILP最適化
    print(f"\n[2/2] ILP最適化を実行中...")
    print(f"  - アルゴリズム: {algorithm}")
    print(f"  - ノード数: {qp.s_num}")
    print(f"  - ストレージ制限: {settings.optimization.storage_limit_bytes:,} bytes")
    
    if not OptimizerFactory.is_available(algorithm):
        print(f"  ❌ アルゴリズム '{algorithm}' は利用できません")
        print(f"  利用可能: {OptimizerFactory.list_algorithms()}")
        return False
    
    try:
        start_time = time.time()
        
        # オプティマイザーのパラメータを準備
        optimizer_params = {
            "qm": qp.qm,
            "s_num": qp.s_num,
            "m_cost": qp.m_cost,
            "node_list": qp.node_list,
            "B_max": settings.optimization.storage_limit_bytes,
            "b_j": qp.b_j,
            "u_ij": qp.u_ij,
            "X": qp.X,
            "q_s_list": qp.q_s_list,
            "settings": settings,
            # インデックス作成コストを追加
            "index_build_costs": getattr(qp, 'index_build_costs', None),
        }
        
        # BigSubs固有のパラメータを追加
        if algorithm == "bigsubs":
            optimizer_params.update({
                "U_j_max": qp.U_j_max,
                "U_max": qp.U_max,
                "y_ij": qp.y_ij,
            })
        
        # オプティマイザーを作成
        print(f"  ✓ オプティマイザー作成中...")
        optimizer = OptimizerFactory.create(algorithm, **optimizer_params)
        
        # 最適化を実行
        print(f"  ✓ 最適化実行中...")
        result = optimizer.optimize()
        
        execution_time = time.time() - start_time
        
        # 結果を表示
        print(f"\n{'=' * 70}")
        print(f"最適化結果")
        print(f"{'=' * 70}")
        
        print(f"\n⏱️  実行時間:")
        print(f"  - アルゴリズム実行時間: {result.execution_time:.2f}秒")
        print(f"  - 総実行時間: {execution_time:.2f}秒")
        
        print(f"\n📊 最適化結果:")
        print(f"  - 目的関数値(ユーティリティ): {result.total_utility:,.2f}")
        print(f"  - 選択されたMV数: {len(result.selected_views)}")
        print(f"  - 使用ストレージ: {result.total_storage / (1024*1024):.2f} MB")
        print(f"  - ストレージ使用率: {result.total_storage / settings.optimization.storage_limit_bytes * 100:.1f}%")
        
        if 'iterations' in result.metadata:
            print(f"  - イテレーション数: {result.metadata['iterations']}")
        
        print(f"\n🎯 選択されたマテリアライズドビュー (最初の10個):")
        if result.selected_views:
            for i, mv in enumerate(result.selected_views[:10], 1):
                size_mb = mv.size / (1024*1024)
                print(f"  {i}. {mv.node_id} ({size_mb:.2f} MB, cost={mv.maintenance_cost:.2f})")
            
            if len(result.selected_views) > 10:
                print(f"  ... 他 {len(result.selected_views) - 10} 個")
        else:
            print(f"  (なし)")
        
        print(f"\n{'=' * 70}")
        print(f"✅ 最適化テスト成功！")
        print(f"{'=' * 70}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 最適化エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """複数のアルゴリズムをテスト"""
    algorithms = ["bigsubs", "normal", "utility"]
    
    print("\n" + "=" * 70)
    print("ILP最適化テストスイート")
    print("=" * 70)
    
    results = {}
    
    for algo in algorithms:
        print(f"\n\n{'#' * 70}")
        print(f"# テスト: {algo.upper()}")
        print(f"{'#' * 70}\n")
        
        success = test_optimization(algo)
        results[algo] = success
        
        if not success:
            print(f"\n⚠️  {algo} のテストに失敗しました。次に進みます...\n")
    
    # サマリー
    print("\n\n" + "=" * 70)
    print("テスト結果サマリー")
    print("=" * 70)
    
    for algo, success in results.items():
        status = "✅ 成功" if success else "❌ 失敗"
        print(f"  {algo:20s}: {status}")
    
    print("\n💡 ヒント:")
    print("  - 最適化にはGurobiライセンスが必要です")
    print("  - gurobi.lic ファイルがプロジェクトルートに配置されているか確認してください")
    print("=" * 70)
    
    all_success = all(results.values())
    return all_success


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="ILP最適化のテスト")
    parser.add_argument(
        "--algorithm",
        choices=["bigsubs", "normal", "utility", "utility_capacity", "frequency", "all"],
        default="all",
        help="テストするアルゴリズム"
    )
    
    args = parser.parse_args()
    
    if args.algorithm == "all":
        success = main()
    else:
        success = test_optimization(args.algorithm)
    
    sys.exit(0 if success else 1)
