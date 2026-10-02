#!/usr/bin/env python3
"""
実測コストベースのクエリパーサ（完全版）

EXPLAIN ANALYZEの結果から直接パースし、QueryParserと同じ属性を
すべて生成します。既存のpickleには依存しません。

使い方:
    python experiments/small_test_ver2/scripts/parse_actual_costs.py

前提条件:
    1. run_explain_analyze.py を実行済み
    2. 02_json/job_real/ にEXPLAIN ANALYZE結果のJSONが存在
"""

import argparse
import json
import pickle
import re
import sys
from pathlib import Path
from typing import Any, Optional

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from src.core.query_manager import QueryManager
from src.core.query_parser import QueryParser


def natural_sort_key(s):
    """自然順ソートのためのキー関数"""
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split('([0-9]+)', str(s))]


class ActualCostQueryParser(QueryParser):
    """EXPLAIN ANALYZE結果からQueryParser互換のデータ構造を生成
    
    QueryParserを継承し、EXPLAIN ANALYZEの実測値を使用するように
    オーバーライドします。
    """
    
    def __init__(self, settings: Optional[Settings] = None):
        """初期化（QueryParserを継承）"""
        super().__init__(settings)
        
        # 実測値フラグ
        self.cost_type = "actual"
    
    def convert_node(
        self,
        node: dict[str, Any],
        subquery_list: list[dict[str, Any]],
        deep_list: list[int],
        order_list: list[int],
        order: int,
        depth: int = 0,
        table_info: list[str] = None,
    ) -> tuple[dict[str, Any], int]:
        """EXPLAIN ANALYZEノードを内部表現に変換（QueryParserと同様）"""
        if table_info is None:
            table_info = []
        
        deep_list.append(depth)
        
        # 実測時間を取得（ミリ秒）
        actual_time = node.get("Actual Total Time", 0.0)
        actual_loops = node.get("Actual Loops", 1)
        
        # PostgreSQLのActual Total Timeは1ループあたりの累積時間
        # 総実行時間 = Actual Total Time（子ノードの時間も含む累積値）
        # MVの利得として使うには、このノード自体のコストを知りたい
        # → 子ノードの時間を引くのが理想だが、複雑なので累積時間をそのまま使用
        cost = actual_time * actual_loops
        
        # サイズ情報（実測行数を使用）
        actual_rows = node.get("Actual Rows", node.get("Plan Rows", 0))
        width = node.get("Plan Width", 1)
        if width == 0:
            width = 1
        size = actual_rows * width
        
        if "Plans" in node:  # Non-leaf node
            children = []
            new_order = order
            
            # Bitmap Heap Scan の特殊処理
            if node["Node Type"] == "Bitmap Heap Scan":
                table_info = [node.get("Relation Name", ""), node.get("Alias", "")]
            
            # 子ノードを再帰的に処理
            for child in node["Plans"]:
                converted_child, order_1 = self.convert_node(
                    child,
                    subquery_list,
                    deep_list,
                    order_list,
                    new_order + 1,
                    depth + 1,
                    table_info,
                )
                children.append(converted_child)
                new_order = order_1
            
            # フィルタ条件を抽出
            filter_condition = ""
            for key in ["Filter"]:
                if key in node:
                    filter_condition = node[key]
                    break
            
            # 親クラスのextract_join_conditionsを使ってJOIN条件を抽出
            join_conditions = self.extract_join_conditions(node)
            
            # cost=0 for scans without filter (query_parser.py と同じロジック)
            # フィルタ条件がないSeq ScanはMV候補から除外
            if "Seq Scan" in node["Node Type"] and filter_condition == "":
                cost = 0.0
            # HashノードでchildにFilterがない場合もcost=0
            elif node["Node Type"] == "Hash" and "Plans" in node and "Filter" not in node["Plans"][0]:
                cost = 0.0
            
            subquery_list.append({
                "type": "non_leaf",
                "operator": node["Node Type"],
                "filter": filter_condition,
                "cost": cost,
                "size": size,
                "rows": actual_rows,
                "width": width,
                "children": children,
                # process_non_leaf_node_v2 を呼ぶために必要
                "join_type": "Inner",
                "join_conditions": join_conditions,
                "additional_filters": [filter_condition] if filter_condition else [],
            })
            order_list.append(order)
            return subquery_list[-1], new_order
        
        else:  # Leaf node
            # フィルタ条件
            filter_condition = node.get("Filter", "")
            
            # テーブル情報
            if node["Node Type"] == "Bitmap Index Scan":
                table = table_info[0] if len(table_info) > 0 else ""
                alias = table_info[1] if len(table_info) > 1 else ""
            else:
                table = node.get("Relation Name", "")
                alias = node.get("Alias", "")
            
            # cost=0 for scans without filter (query_parser.py と同じロジック)
            # フィルタなしのScanはMV候補から除外
            if "Scan" in node["Node Type"] and "Filter" not in node:
                cost = 0.0
            
            subquery_list.append({
                "type": "leaf",
                "operator": node["Node Type"],
                "table": table,
                "alias": alias,
                "filter": filter_condition,
                "cost": cost,
                "size": size,
                "width": width,
            })
            order_list.append(order)
            return subquery_list[-1], order
    
    def convert_json(self, json_data: list[dict[str, Any]]) -> tuple[list, list, list]:
        """JSONデータを内部表現に変換"""
        subquery_list = []
        deep_list = []
        order_list = []
        order = 0
        
        for plan in json_data:
            self.convert_node(
                plan["Plan"], subquery_list, deep_list, order_list, order
            )
        
        return subquery_list, deep_list, order_list
    
    def query_parse(self, path: str) -> None:
        """EXPLAIN ANALYZE JSONをパース（メインエントリポイント）"""
        json_dir = Path(path)
        
        files = sorted(json_dir.glob("*.json"), key=natural_sort_key)
        self.query_files = [f.stem for f in files]
        
        q_num_len = len(files)
        print(f"クエリ数: {q_num_len}")
        
        query = []
        deeplist = []
        orderlist = []
        
        # 各クエリファイルを処理
        for i, file_path in enumerate(files):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            converted_data, deep_list, order_list = self.convert_json(data)
            deeplist.append(deep_list)
            orderlist.append(order_list)
            
            # ノードをDFSで処理してQueryManagerに登録
            for j, subquery in zip(order_list, converted_data):
                self.qm.depth_first_search(subquery, [i, j])
            
            query.append(converted_data)
        
        self.query = query
        self.deeplist = deeplist
        
        # ノードリストを構築
        leaf_nodes = sorted(
            self.qm.leaf_nodes_map.values(),
            key=lambda x: int(x.split("_")[-1])
        )
        non_leaf_nodes = sorted(
            self.qm.non_leaf_nodes_map.values(),
            key=lambda x: int(x.split("_")[-1])
        )
        node_list = leaf_nodes + non_leaf_nodes
        self.node_list = node_list
        s_num = len(node_list)
        self.s_num = s_num
        
        print(f"Leaf nodes: {len(leaf_nodes)}")
        print(f"Non-leaf nodes: {len(non_leaf_nodes)}")
        print(f"Total nodes: {s_num}")
        
        # position_node_id マッピング
        position_node_id = {}
        for node_id, positions in self.qm.subquery_positions.items():
            for pos in positions:
                position_node_id[tuple(pos)] = node_id
        self.position_node_id = position_node_id
        
        # 共有カウンタ（複数クエリで使われるノード）
        s_counter = [0] * s_num
        for j in range(s_num):
            node_id = node_list[j]
            if node_id in self.qm.subquery_positions:
                if len(self.qm.subquery_positions[node_id]) > 1:
                    s_counter[j] = 1
        
        # u_ij, y_ij, q_s_list を構築
        q_s_list = []
        q_s_order_list = []
        u_ij = []
        us_ij = []
        y_ij = []
        
        for i in range(q_num_len):
            q_by_s = [0] * s_num
            q_s_order = []
            u_ij_seed = [0.0] * s_num
            y_ij_seed = [0] * s_num
            us_ij_seed = [0.0] * s_num
            
            for j in range(s_num):
                node_id = node_list[j]
                if node_id in self.qm.subquery_positions:
                    for item in self.qm.subquery_positions[node_id]:
                        if item[0] == i:
                            q_s_order.append(item[1])
                            q_by_s[j] = 1
                            u_ij_seed[j] = self.qm.subquery_costs[node_id]
                            us_ij_seed[j] = self.qm.subquery_costs[node_id] * (1 if s_counter[j] == 0 else s_counter[j])
            
            q_s_list.append(q_by_s)
            q_s_order_list.append(q_s_order)
            u_ij.append(u_ij_seed)
            us_ij.append(us_ij_seed)
            y_ij.append(y_ij_seed)
        
        self.q_s_list = q_s_list
        self.q_s_order_list = q_s_order_list
        self.u_ij = u_ij
        self.us_ij = us_ij
        self.y_ij = y_ij
        
        # b_j（サイズ）を構築
        b_j = [1] * s_num
        for j, node_id in enumerate(node_list):
            if node_id in self.qm.subquery_sizes:
                b_j[j] = max(self.qm.subquery_sizes[node_id], 1)
        self.b_j = b_j
        
        # U_j_max（各ノードの合計利得）を計算
        U_j_max = [0.0] * s_num
        for i in range(len(u_ij)):
            for j in range(s_num):
                U_j_max[j] += u_ij[i][j]
        self.U_j_max = U_j_max
        self.U_max = sum(U_j_max)
        
        # 依存行列 X を構築
        self.subqlist = {v: k for k, v in self.qm.non_leaf_nodes_map.items()}
        X = [[0] * s_num for _ in range(s_num)]
        for j in range(s_num):
            node_id = node_list[j]
            if node_id in self.subqlist:
                for child in self.subqlist[node_id]:
                    if child in node_list:
                        child_idx = node_list.index(child)
                        X[j][child_idx] = 1
                        # 推移的依存関係も設定
                        self._set_transitive_deps(X, j, child, node_list)
        self.X = X
        
        # メンテナンスコスト（ここでは0とする）
        self.m_cost = [0.0] * s_num
        
        # インデックスビルドコスト
        self.index_build_costs = [
            self.qm.index_build_costs.get(node_id, 0.0)
            for node_id in node_list
        ]
        
        # original_subquery_costs
        self.original_subquery_costs = self.qm.original_subquery_costs.copy()
        
        print(f"u_ij shape: {len(u_ij)} x {s_num}")
        print(f"Total utility: {self.U_max:.2f} ms")
    
    def _set_transitive_deps(self, X, parent_idx, child_id, node_list):
        """推移的依存関係を設定"""
        if child_id not in self.subqlist:
            return
        for grandchild in self.subqlist[child_id]:
            if grandchild in node_list:
                grandchild_idx = node_list.index(grandchild)
                X[parent_idx][grandchild_idx] = 1
                self._set_transitive_deps(X, parent_idx, grandchild, node_list)


class ActualCostParserRunner:
    """実測コストパーサの実行クラス"""
    
    def __init__(self):
        self.exp_dir = project_root / "experiments" / "small_test_ver2"
        self.json_real_dir = self.exp_dir / "02_json" / "job_real"
        self.pickle_dir = self.exp_dir / "03_parsed"
        self.output_pickle_path = self.pickle_dir / "job_real" / "qp_class.pkl"
    
    def run(self):
        """全処理を実行"""
        print("=" * 60)
        print("実測コストベースのクエリパース（完全版）")
        print("=" * 60)
        
        if not self.json_real_dir.exists():
            print(f"エラー: {self.json_real_dir} が見つかりません")
            print("先に run_explain_analyze.py を実行してください")
            return False
        
        json_files = list(self.json_real_dir.glob("*.json"))
        if not json_files:
            print(f"エラー: {self.json_real_dir} にJSONファイルがありません")
            return False
        
        print(f"入力ディレクトリ: {self.json_real_dir}")
        print(f"JSONファイル数: {len(json_files)}")
        print()
        
        # パース実行（ActualCostQueryParserを使用）
        actual_qp = ActualCostQueryParser()
        actual_qp.query_parse(str(self.json_real_dir))
        
        # QueryParserインスタンスを作成してデータをコピー（pickle互換性のため）
        qp = QueryParser()
        
        # 全属性をコピー
        qp.qm = actual_qp.qm
        qp.s_num = actual_qp.s_num
        qp.m_cost = actual_qp.m_cost
        qp.node_list = actual_qp.node_list
        qp.position_node_id = actual_qp.position_node_id
        qp.deeplist = actual_qp.deeplist
        qp.U_j_max = actual_qp.U_j_max
        qp.b_j = actual_qp.b_j
        qp.q_s_list = actual_qp.q_s_list
        qp.q_s_order_list = actual_qp.q_s_order_list
        qp.u_ij = actual_qp.u_ij
        qp.us_ij = actual_qp.us_ij
        qp.y_ij = actual_qp.y_ij
        qp.X = actual_qp.X
        qp.U_max = actual_qp.U_max
        qp.query = actual_qp.query
        qp.subqlist = actual_qp.subqlist
        qp.original_subquery_costs = actual_qp.original_subquery_costs
        qp.query_files = actual_qp.query_files
        qp.index_build_costs = actual_qp.index_build_costs
        
        # 実測値フラグを追加
        qp.cost_type = "actual"
        
        # pickle保存
        self.output_pickle_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_pickle_path, 'wb') as f:
            pickle.dump(qp, f)
        
        print()
        print(f"保存完了: {self.output_pickle_path}")
        
        # サマリー
        summary = {
            "cost_type": "actual",
            "num_queries": len(qp.query_files),
            "num_nodes": qp.s_num,
            "u_ij_shape": [len(qp.u_ij), qp.s_num],
            "total_utility_ms": qp.U_max,
        }
        
        summary_path = self.output_pickle_path.parent / "parse_summary_actual.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        print(f"サマリー保存: {summary_path}")
        print()
        print("=" * 60)
        print("完了")
        print("=" * 60)
        print()
        print("次のステップ:")
        print("  python scripts/run_experiment_normal.py --query-set job_real --phase post-opt ...")
        
        return True


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description='実測コストベースのクエリパーサ（完全版）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    args = parser.parse_args()
    
    runner = ActualCostParserRunner()
    success = runner.run()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
