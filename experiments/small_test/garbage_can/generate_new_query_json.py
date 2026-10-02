#!/usr/bin/env python3
"""
新しいクエリ（query4, query5, query6）のEXPLAIN JSON生成スクリプト
"""

import subprocess
import json
from pathlib import Path


def generate_explain_json_for_new_queries():
    """新しいクエリのEXPLAIN JSONを生成"""
    
    queries_dir = Path("experiments/small_test/01_queries")
    json_dir = Path("experiments/small_test/02_json/job")
    json_dir.mkdir(parents=True, exist_ok=True)
    
    database = "mv_small_test"
    
    # 新しいクエリファイル
    new_queries = ["query4.sql", "query5.sql", "query6.sql"]
    
    print("=" * 70)
    print("新しいクエリのEXPLAIN JSON生成")
    print("=" * 70)
    
    for query_file in new_queries:
        query_path = queries_dir / query_file
        output_file = json_dir / query_file.replace('.sql', '.json')
        
        if not query_path.exists():
            print(f"✗ {query_file} が見つかりません")
            continue
        
        print(f"\n→ {query_file} を処理中...")
        
        # クエリを読み込み（コメント行を除去）
        with open(query_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # コメント行と空行を除去
        query_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith('--'):
                query_lines.append(line)
        
        query_sql = ''.join(query_lines).strip()
        
        # EXPLAIN JSONを実行
        explain_sql = f"EXPLAIN (FORMAT JSON, COSTS TRUE, VERBOSE FALSE) {query_sql}"
        
        try:
            result = subprocess.run(
                ['psql', '-U', 'postgres', '-d', database,
                 '-t', '-A', '-c', explain_sql],
                capture_output=True,
                text=True,
                check=True,
                encoding='utf-8',
                errors='replace'
            )
            
            # JSONとして保存
            json_data = json.loads(result.stdout.strip())
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            
            print(f"  ✓ {output_file.name} を生成")
            
        except subprocess.CalledProcessError as e:
            print(f"  ✗ エラー: {e}")
            if e.stderr:
                print(f"     {e.stderr}")
        except json.JSONDecodeError as e:
            print(f"  ✗ JSON解析エラー: {e}")
    
    print("\n" + "=" * 70)
    print("完了！")
    print("=" * 70)
    print("\n次のステップ:")
    print("1. 時刻依存型パースを実行:")
    print("   python experiments/small_test/run_experiment.py --mode time-dependent --phase 2")
    print("\n2. 最適化を実行:")
    print("   python experiments/small_test/run_experiment.py --mode time-dependent --phase 3 --algorithm normal")


if __name__ == "__main__":
    generate_explain_json_for_new_queries()
