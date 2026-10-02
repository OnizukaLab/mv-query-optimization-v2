#!/usr/bin/env python
"""クエリ書き換え実行スクリプト"""
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import argparse  # noqa: E402

from src.rewrite.query_rewriter import QueryRewriter, load_mv_selections  # noqa: E402


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(description="Rewrite queries using materialized views")
    parser.add_argument("ilp_type", help="ILP algorithm type (normal, bigsubs, etc.)")
    parser.add_argument("--mv-list", help="Path to mv_y_list.csv")
    parser.add_argument("--output", help="Output directory")
    parser.add_argument("--qm-state", help="QueryManager state file (pickle)")

    args = parser.parse_args()

    # MV選択結果の読み込み
    mv_list_file = args.mv_list or f"Output/{args.ilp_type}/mv_y_list.csv"

    if not Path(mv_list_file).exists():
        print(f"Error: MV list file not found: {mv_list_file}")
        sys.exit(1)

    print(f"Loading MV selections from: {mv_list_file}")
    mv_selections = load_mv_selections(mv_list_file)
    print(f"Loaded {len(mv_selections)} query MV selections")

    # QueryManager状態の読み込み（オプション）
    qm = None
    if args.qm_state and Path(args.qm_state).exists():
        import pickle

        print(f"Loading QueryManager state from: {args.qm_state}")
        with open(args.qm_state, "rb") as f:
            qm = pickle.load(f)

    # QueryRewriter初期化
    rewriter = QueryRewriter(qm)

    # 出力ディレクトリ
    output_base = args.output or "Output/query_rewrite"

    # 1. MV作成スクリプト生成
    mv_dir = Path(output_base) / "mv"
    print("\n=== Generating MV creation scripts ===")

    # 全MVノードを収集
    all_mv_nodes = set()
    for nodes in mv_selections.values():
        all_mv_nodes.update(nodes)
    all_mv_nodes.discard("NONE")

    if qm:
        mv_files = rewriter.generate_mv_creation_scripts(list(all_mv_nodes), mv_dir)
        print(f"Generated {len(mv_files)} MV creation scripts in {mv_dir}")
    else:
        print("Warning: No QueryManager available, skipping MV generation")

    # 2. クエリ書き換え
    rewrite_dir = Path(output_base) / "re_sql" / args.ilp_type
    print("\n=== Rewriting queries ===")

    rewritten_files = rewriter.rewrite_workload(mv_selections, str(rewrite_dir))

    print(f"Rewrote {len(rewritten_files)} queries in {rewrite_dir}")

    print("\n=== Query rewriting completed ===")


if __name__ == "__main__":
    main()
