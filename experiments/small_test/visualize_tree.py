# filepath: experiments/small_test/visualize_tree.py
import json
import sys

def print_tree(node, prefix="", is_last=True):
    """ツリー構造をASCIIアートで出力"""
    # ノードのラベルを作成
    if node['type'] == 'leaf':
        label = f"{node['operator']} ({node['table']} AS {node['alias']})"
        if node.get('filter'):
            label += f" WHERE {node['filter']}"
    else:
        label = f"{node['operator']} ({node['join_type']})"
        if node.get('filter'):
            label += f" FILTER: {node['filter']}"
    
    # 現在のノードを出力
    connector = "└── " if is_last else "├── "
    print(prefix + connector + label)
    
    # 子ノードを再帰的に出力
    if 'children' in node and node['children']:
        new_prefix = prefix + ("    " if is_last else "│   ")
        for i, child in enumerate(node['children']):
            is_last_child = (i == len(node['children']) - 1)
            print_tree(child, new_prefix, is_last_child)

def visualize_query_tree(json_file, query_index=0):
    """指定したクエリのツリーを可視化"""
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    if 'query' not in data or query_index >= len(data['query']):
        print(f"Query index {query_index} not found.")
        return
    
    root_nodes = data['query'][query_index]
    print(f"=== Query {query_index} Tree ===")
    
    for i, root in enumerate(root_nodes):
        is_last = (i == len(root_nodes) - 1)
        print_tree(root, "", is_last)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python visualize_tree.py <json_file> [query_index]")
        sys.exit(1)
    
    json_file = sys.argv[1]
    query_index = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    visualize_query_tree(json_file, query_index)