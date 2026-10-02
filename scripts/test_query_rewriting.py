#!/usr/bin/env python3
"""クエリ書き換え機能のテストスクリプト

最適化で選択されたMVを使って、元のクエリを書き換えます。
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from src.core.query_parser import QueryParser
from src.optimization.factory import OptimizerFactory
from src.rewrite.query_rewriter import QueryRewriter


def test_query_rewriting(algorithm: str = "bigsubs", num_queries: int = 3):
    """クエリ書き換えをテスト"""
    print("=" * 70)
    print(f"クエリ書き換えテスト - アルゴリズム: {algorithm}")
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
        
    except Exception as e:
        print(f"  ❌ 最適化エラー: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # ステップ3: クエリ書き換え
    print(f"\n[3/3] クエリを書き換え中...")
    
    try:
        # QueryRewriterを初期化
        rewriter = QueryRewriter(query_manager=qp.qm)
        
        # y_ijから各クエリで使用するMVを特定
        y_ij = result.metadata.get('y_ij', [])
        z_j = result.metadata.get('z_j', [])
        
        mv_selections = {}
        for i in range(min(num_queries, len(y_ij))):
            selected_mvs = []
            for j in range(len(z_j)):
                if y_ij[i][j] == 1 and z_j[j] == 1:
                    selected_mvs.append(qp.node_list[j])
            
            if selected_mvs:
                mv_selections[i] = selected_mvs
        
        print(f"  - 書き換え対象クエリ数: {len(mv_selections)}")
        
        # 元のクエリSQLを読み込み（簡易版：JSONからSQLを再構築）
        original_queries = {}
        sql_dir = Path(settings.benchmark.sql_dir) / "job"
        
        if sql_dir.exists():
            sql_files = sorted(sql_dir.glob("*.sql"))
            for i, sql_file in enumerate(sql_files[:num_queries]):
                with open(sql_file, 'r', encoding='utf-8') as f:
                    original_queries[i] = f.read()
        else:
            print(f"  ⚠️  SQL directory not found: {sql_dir}")
            # ダミーSQLを使用
            for i in mv_selections.keys():
                original_queries[i] = "SELECT * FROM placeholder;"
        
        # 出力ディレクトリ
        output_dir = Path("Output/test_query_rewrite")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # クエリ書き換え実行
        rewritten_files = rewriter.rewrite_workload(
            mv_selections=mv_selections,
            output_dir=str(output_dir),
            original_queries=original_queries
        )
        
        print(f"  ✓ {len(rewritten_files)}個のクエリを書き換え")
        
        # 結果表示
        print(f"\n{'=' * 70}")
        print(f"書き換え結果")
        print(f"{'=' * 70}")
        
        for i, (query_id, mv_nodes) in enumerate(mv_selections.items(), 1):
            print(f"\n📝 クエリ {query_id}:")
            print(f"   使用MV数: {len(mv_nodes)}")
            print(f"   MVリスト: {', '.join(mv_nodes[:5])}")
            if len(mv_nodes) > 5:
                print(f"            ... 他 {len(mv_nodes) - 5} 個")
            
            # 元のSQLと書き換え後のSQLを比較表示
            if query_id in original_queries:
                original_sql = original_queries[query_id]
                rewritten_file = output_dir / f"query_{query_id}.sql"
                
                if rewritten_file.exists():
                    with open(rewritten_file, 'r', encoding='utf-8') as f:
                        rewritten_sql = f.read()
                    
                    print(f"\n   元のSQL (最初の5行):")
                    for line in original_sql.split('\n')[:5]:
                        print(f"   | {line}")
                    if len(original_sql.split('\n')) > 5:
                        print(f"   | ...")
                    
                    print(f"\n   書き換え後のSQL:")
                    for line in rewritten_sql.split('\n'):
                        print(f"   | {line}")
        
        print(f"\n{'=' * 70}")
        print(f"📂 書き換えられたクエリの場所:")
        print(f"   {output_dir.absolute()}")
        print(f"{'=' * 70}")
        
        print(f"\n📊 統計:")
        total_mvs_used = sum(len(mvs) for mvs in mv_selections.values())
        avg_mvs = total_mvs_used / len(mv_selections) if mv_selections else 0
        print(f"  - 書き換えたクエリ数: {len(mv_selections)}")
        print(f"  - 使用したMV総数: {total_mvs_used}")
        print(f"  - クエリあたり平均MV数: {avg_mvs:.1f}")
        
        print(f"\n{'=' * 70}")
        print(f"✅ クエリ書き換えテスト成功！")
        print(f"{'=' * 70}")
        
        print(f"\n💡 次のステップ:")
        print(f"  1. 書き換え結果を確認: cat {output_dir}/query_0.sql")
        print(f"  2. 書き換えたクエリを実行: psql -f {output_dir}/query_0.sql")
        print(f"  3. 実行時間を比較")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 書き換えエラー: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="クエリ書き換えのテスト")
    parser.add_argument(
        "--algorithm",
        choices=["bigsubs", "normal", "utility", "utility_capacity", "frequency"],
        default="bigsubs",
        help="使用するアルゴリズム"
    )
    parser.add_argument(
        "--num-queries",
        type=int,
        default=3,
        help="書き換えるクエリ数"
    )
    
    args = parser.parse_args()
    
    success = test_query_rewriting(args.algorithm, args.num_queries)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
