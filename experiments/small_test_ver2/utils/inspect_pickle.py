"""Pickleファイルの内容をJSONで出力するツール

QueryParserのpickleファイルを読み込み、
内部データ構造をJSONファイルとして保存します。
"""

import sys
from pathlib import Path

# プロジェクトルートをsys.pathに追加(pickle.load前に必須)
# このスクリプトの位置: experiments/small_test_ver2/utils/inspect_pickle.py
# プロジェクトルート: 3階層上
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pickle
import json
from typing import Any


def serialize_object(obj: Any) -> Any:
    """オブジェクトをJSON形式にシリアライズ可能な形式に変換
    
    Args:
        obj: シリアライズするオブジェクト
        
    Returns:
        JSON形式で保存可能なオブジェクト
    """
    # 基本型はそのまま
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    
    # リスト
    if isinstance(obj, list):
        return [serialize_object(item) for item in obj]
    
    # タプル（リストに変換）
    if isinstance(obj, tuple):
        return [serialize_object(item) for item in obj]
    
    # 辞書
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            # キーが文字列でない場合は文字列に変換
            str_key = str(key) if not isinstance(key, str) else key
            result[str_key] = serialize_object(value)
        return result
    
    # setはリストに変換
    if isinstance(obj, set):
        return [serialize_object(item) for item in sorted(obj)]
    
    # カスタムオブジェクト（__dict__を持つもの）
    if hasattr(obj, '__dict__'):
        result = {
            '_type': obj.__class__.__name__,
        }
        for key, value in obj.__dict__.items():
            result[key] = serialize_object(value)
        return result
    
    # その他は文字列表現
    return str(obj)


def inspect_query_parser(pickle_path: str, output_path: str = None) -> None:
    """QueryParserのpickleファイルを読み込んでJSONで出力
    
    Args:
        pickle_path: pickleファイルのパス
        output_path: 出力JSONファイルのパス(省略時は自動生成)
    """
    pickle_file = Path(pickle_path)
    
    if not pickle_file.exists():
        print(f"エラー: ファイルが見つかりません: {pickle_path}")
        return
    
    # pickleファイルを読み込み
    print(f"読み込み中: {pickle_path}")
    with open(pickle_file, 'rb') as f:
        qp = pickle.load(f)
    
    print(f"型: {type(qp).__name__}")
    
    # 出力パスの決定
    if output_path is None:
        output_path = pickle_file.with_suffix('.json')
    
    output_file = Path(output_path)
    
    # QueryParserの主要な属性を抽出
    data = {
        "_metadata": {
            "type": type(qp).__name__,
            "source_pickle": str(pickle_file),
        },
        "qm": serialize_object(qp.qm) if hasattr(qp, 'qm') else None,
        "s_num": qp.s_num if hasattr(qp, 's_num') else None,
        "node_list": qp.node_list if hasattr(qp, 'node_list') else None,
        "m_cost": qp.m_cost if hasattr(qp, 'm_cost') else None,
        "U_j_max": qp.U_j_max if hasattr(qp, 'U_j_max') else None,
        "b_j": qp.b_j if hasattr(qp, 'b_j') else None,
        "q_s_list": qp.q_s_list if hasattr(qp, 'q_s_list') else None,
        "u_ij": qp.u_ij if hasattr(qp, 'u_ij') else None,
        "position_node_id": serialize_object(qp.position_node_id) if hasattr(qp, 'position_node_id') else None,
        "deeplist": qp.deeplist if hasattr(qp, 'deeplist') else None,
        "query": serialize_object(qp.query) if hasattr(qp, 'query') else None,
        "subqlist": serialize_object(qp.subqlist) if hasattr(qp, 'subqlist') else None,
    }
    
    # JSONファイルとして保存
    print(f"書き込み中: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"完了: {output_file}")
    print(f"ファイルサイズ: {output_file.stat().st_size:,} bytes")
    
    # サマリー情報を表示
    print("\n=== サマリー ===")
    print(f"ノード数: {data['s_num']}")
    if data['node_list']:
        print(f"ノードリスト: {len(data['node_list'])} 個")
        print(f"  - leaf nodes: {sum(1 for n in data['node_list'] if n.startswith('leaf_'))}")
        print(f"  - non-leaf nodes: {sum(1 for n in data['node_list'] if n.startswith('non_leaf_'))}")
    
    if data['qm']:
        qm_data = data['qm']
        if 'leaf_nodes_map_r' in qm_data:
            print(f"Leaf nodes: {len(qm_data['leaf_nodes_map_r'])} 個")
        if 'non_leaf_nodes_info' in qm_data:
            print(f"Non-leaf nodes: {len(qm_data['non_leaf_nodes_info'])} 個")


def main():
    """メイン処理"""
    import argparse
    
    # コマンドライン引数の処理
    parser = argparse.ArgumentParser(description="QueryParserのpickleファイルをJSONに変換")
    parser.add_argument(
        "--query-set",
        type=str,
        default="job_like",
        help="使用するクエリセットの名前 (デフォルト: job_like)"
    )
    
    args = parser.parse_args()
    
    # パス設定
    base_dir = Path(__file__).parent.parent
    pickle_path = base_dir / "03_parsed" / args.query_set / "qp_class.pkl"
    output_path = base_dir / "03_parsed" / args.query_set / "qp_class.json"
    
    # ファイルが存在するかチェック
    if not pickle_path.exists():
        print(f"エラー: pickleファイルが見つかりません: {pickle_path}")
        print(f"使用可能なクエリセット:")
        parsed_dir = base_dir / "03_parsed"
        if parsed_dir.exists():
            for subdir in sorted(parsed_dir.iterdir()):
                if subdir.is_dir() and (subdir / "qp_class.pkl").exists():
                    print(f"  - {subdir.name}")
        return
    
    inspect_query_parser(str(pickle_path), str(output_path))
    
    # JSONファイルが生成された場合、特定のノードを表示
    if output_path.exists():
        print("\n" + "=" * 60)
        print("ノード情報の表示例")
        print("=" * 60)
        
        # サンプルノードを表示
        display_node_info(str(output_path), "non_leaf_5")
        print()
        display_node_info(str(output_path), "leaf_2")


def display_node_info(json_path: str, node_id: str) -> None:
    """特定のノード情報を見やすく表示
    
    Args:
        json_path: JSONファイルのパス
        node_id: 表示するノードID
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    qm = data.get('qm', {})
    
    print(f"\n--- {node_id} ---")
    
    # Leaf nodeの場合
    if node_id.startswith('leaf_'):
        leaf_info = qm.get('leaf_nodes_map_r', {}).get(node_id)
        if leaf_info:
            print(f"Type: Leaf Node")
            print(f"Operator: {leaf_info[0]}")
            print(f"Table: {leaf_info[1]}")
            print(f"Alias: {leaf_info[2]}")
            print(f"Filter: {leaf_info[3] if leaf_info[3] else '(なし)'}")
        else:
            print(f"ノードが見つかりません: {node_id}")
        return
    
    # Non-leaf nodeの場合
    if node_id.startswith('non_leaf_'):
        non_leaf_info = qm.get('non_leaf_nodes_info', {}).get(node_id)
        if non_leaf_info:
            print(f"Type: Non-Leaf Node")
            print(f"Operator: {non_leaf_info.get('operator', 'N/A')}")
            print(f"Join Type: {non_leaf_info.get('join_type', 'N/A')}")
            print(f"Children: {non_leaf_info.get('children', [])}")
            
            # JOIN条件
            join_conditions = non_leaf_info.get('join_conditions', [])
            if join_conditions:
                print(f"Join Conditions ({len(join_conditions)} 個):")
                for jc in join_conditions:
                    print(f"  - {jc.get('left_table')}.{jc.get('left_column')} "
                          f"{jc.get('operator')} "
                          f"{jc.get('right_table')}.{jc.get('right_column')}")
                    print(f"    (Type: {jc.get('condition_type')})")
            else:
                print("Join Conditions: (なし)")
            
            # フィルタ
            filters = non_leaf_info.get('filters', [])
            if filters:
                print(f"Filters ({len(filters)} 個):")
                for f in filters:
                    print(f"  - {f}")
            else:
                print("Filters: (なし)")
            
            # 追加フィルタ
            additional_filters = non_leaf_info.get('additional_filters', [])
            if additional_filters:
                print(f"Additional Filters ({len(additional_filters)} 個):")
                for af in additional_filters:
                    print(f"  - {af}")
        else:
            print(f"ノードが見つかりません: {node_id}")
        return
    
    print(f"不明なノードタイプ: {node_id}")


if __name__ == "__main__":
    main()
