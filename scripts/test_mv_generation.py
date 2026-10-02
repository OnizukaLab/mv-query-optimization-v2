#!/usr/bin/env python3
"""MV作成SQL生成機能のテストスクリプト

最適化結果から、マテリアライズドビュー作成SQLを生成できるかを確認します。
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from src.core.query_parser import QueryParser
from src.optimization.factory import OptimizerFactory
from src.rewrite.mv_generator import MVGenerator


def test_mv_sql_generation(algorithm: str = "bigsubs", max_mvs: int = 10):
    """MV作成SQL生成をテスト"""
    print("=" * 70)
    print(f"MV作成SQL生成テスト - アルゴリズム: {algorithm}")
    print("=" * 70)
    
    # 設定の読み込み
    settings = Settings()
    
    # ステップ1: クエリパース
    print(f"\n[1/3] クエリをパース中...")
    qp = QueryParser(settings)
    query_path = settings.benchmark.queries_dir
    
    try:
        qp.query_parse(0, query_path, 1)
        print(f"  ✓ {len(qp.query)}個のクエリをパース完了")
    except Exception as e:
        print(f"  ❌ パースエラー: {e}")
        return False
    
    # ステップ2: ILP最適化
    print(f"\n[2/3] ILP最適化を実行中...")
    
    try:
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
        
        if algorithm == "bigsubs":
            optimizer_params.update({
                "U_j_max": qp.U_j_max,
                "U_max": qp.U_max,
                "y_ij": qp.y_ij,
            })
        
        optimizer = OptimizerFactory.create(algorithm, **optimizer_params)
        result = optimizer.optimize()
        
        print(f"  ✓ 最適化完了")
        print(f"  - 選択されたMV数: {len(result.selected_views)}")
        print(f"  - 総ユーティリティ: {result.total_utility:,.2f}")
        
    except Exception as e:
        print(f"  ❌ 最適化エラー: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # ステップ3: MV作成SQL生成
    print(f"\n[3/3] MV作成SQLを生成中...")
    
    try:
        # MVGeneratorを初期化
        mv_generator = MVGenerator()
        
        # 選択されたMVノードのリストを取得（上限あり）
        mv_nodes = [mv.node_id for mv in result.selected_views[:max_mvs]]
        
        print(f"  - 生成するMV数: {len(mv_nodes)} (最大{max_mvs}個)")
        
        # 出力ディレクトリ
        output_dir = Path("Output/test_mv_creation")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # SQL生成
        generated_files = mv_generator.generate_mv_scripts(mv_nodes, qp.qm, str(output_dir))
        
        print(f"  ✓ {len(generated_files)}個のSQLファイルを生成")
        
        # 結果表示
        print(f"\n{'=' * 70}")
        print(f"生成されたMV作成SQL")
        print(f"{'=' * 70}")
        
        for i, filepath in enumerate(generated_files[:5], 1):
            print(f"\n📄 {i}. {Path(filepath).name}")
            print(f"   パス: {filepath}")
            
            # SQLの内容を表示（最初の10行）
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                preview_lines = lines[:10]
                
                print(f"   内容:")
                for line in preview_lines:
                    print(f"   {line.rstrip()}")
                
                if len(lines) > 10:
                    print(f"   ... (残り{len(lines) - 10}行)")
        
        if len(generated_files) > 5:
            print(f"\n... 他 {len(generated_files) - 5} 個のファイル")
        
        print(f"\n{'=' * 70}")
        print(f"📂 生成されたSQLファイルの場所:")
        print(f"   {output_dir.absolute()}")
        print(f"{'=' * 70}")
        
        # サマリー統計
        print(f"\n📊 生成されたSQLのサマリー:")
        
        total_size = 0
        sql_types = {"leaf": 0, "non_leaf": 0}
        
        for filepath in generated_files:
            filename = Path(filepath).stem
            if filename.startswith("leaf_"):
                sql_types["leaf"] += 1
            elif filename.startswith("non_leaf_"):
                sql_types["non_leaf"] += 1
            
            total_size += Path(filepath).stat().st_size
        
        print(f"  - リーフノードMV: {sql_types['leaf']}個")
        print(f"  - 非リーフノードMV: {sql_types['non_leaf']}個")
        print(f"  - 総ファイルサイズ: {total_size / 1024:.2f} KB")
        
        print(f"\n{'=' * 70}")
        print(f"✅ MV作成SQL生成テスト成功！")
        print(f"{'=' * 70}")
        
        print(f"\n💡 次のステップ:")
        print(f"  1. 生成されたSQLを確認: ls -la {output_dir}")
        print(f"  2. SQLをデータベースで実行: psql -f {output_dir}/leaf_1.sql")
        print(f"  3. MVが作成されたか確認: \\d+ mv_name")
        
        return True
        
    except Exception as e:
        print(f"\n❌ SQL生成エラー: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="MV作成SQL生成のテスト")
    parser.add_argument(
        "--algorithm",
        choices=["bigsubs", "normal", "utility", "utility_capacity", "frequency"],
        default="bigsubs",
        help="使用するアルゴリズム"
    )
    parser.add_argument(
        "--max-mvs",
        type=int,
        default=10,
        help="生成する最大MV数"
    )
    
    args = parser.parse_args()
    
    success = test_mv_sql_generation(args.algorithm, args.max_mvs)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
