#!/usr/bin/env python3
"""クエリ読み込みのデバッグスクリプト"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from src.utils.legacy import get_red_queries, natural_sort_key

def debug_query_loading():
    settings = Settings()
    
    query_path = settings.benchmark.queries_dir
    workloads_dir = settings.benchmark.workloads_dir
    get_ceb = settings.benchmark.type == "ceb"
    
    print(f"設定:")
    print(f"  query_path: {query_path}")
    print(f"  workloads_dir: {workloads_dir}")
    print(f"  get_ceb: {get_ceb}")
    print()
    
    # get_red_queries関数を実行
    files, file_freq = get_red_queries(query_path, workloads_dir, get_ceb)
    files = sorted(files, key=natural_sort_key)
    
    print(f"結果:")
    print(f"  読み込まれたクエリ数: {len(files)}")
    print()
    
    # 最初の10個と最後の10個を表示
    print("最初の10個のクエリファイル:")
    for i, f in enumerate(files[:10], 1):
        print(f"  {i}. {f} (頻度: {file_freq[f]})")
    
    if len(files) > 20:
        print(f"  ... ({len(files) - 20}個省略)")
    
    print("\n最後の10個のクエリファイル:")
    for i, f in enumerate(files[-10:], len(files)-9):
        print(f"  {i}. {f} (頻度: {file_freq[f]})")
    
    # 全JOBクエリファイルを確認
    print("\n\n全JSONファイル確認:")
    json_dir = Path(query_path) / "job"
    all_json_files = sorted(json_dir.glob("*.json"))
    print(f"  dataset/RED_JSON/job/ にあるJSONファイル数: {len(all_json_files)}")
    
    # どのファイルが使われていないか確認
    used_files = set(Path(f).name for f in files)
    all_files = set(f.name for f in all_json_files)
    unused_files = all_files - used_files
    
    print(f"\n未使用のクエリファイル数: {len(unused_files)}")
    if unused_files:
        print(f"未使用ファイルの例 (最初の10個):")
        for f in sorted(list(unused_files))[:10]:
            print(f"  - {f}")

if __name__ == "__main__":
    debug_query_loading()
