#!/usr/bin/env python3
"""
JOBクエリのEXPLAIN (FORMAT JSON)を取得してRED_JSON/jobに保存するスクリプト
Bitmap scanを有効にした状態で実行
"""

import os
import json
import psycopg2
from pathlib import Path

# データベース接続設定
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'imdbload',
    'user': 'postgres',
    'password': 'pass'
}

# パス設定
PROJECT_ROOT = Path(__file__).parent.parent
SQL_DIR = PROJECT_ROOT / "dataset" / "RED_SQL" / "job"
OUTPUT_DIR = PROJECT_ROOT / "dataset" / "RED_JSON" / "job"

def get_explain_json(cursor, sql_query):
    """クエリのEXPLAIN (FORMAT JSON)を取得"""
    explain_query = f"EXPLAIN (FORMAT JSON) {sql_query}"
    cursor.execute(explain_query)
    result = cursor.fetchone()[0]
    return result

def main():
    # 出力ディレクトリ作成
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # データベース接続
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    # Bitmap scanが有効か確認
    cursor.execute("SHOW enable_bitmapscan;")
    bitmap_status = cursor.fetchone()[0]
    print(f"enable_bitmapscan: {bitmap_status}")
    
    if bitmap_status != 'on':
        print("Bitmap scanを有効にします...")
        cursor.execute("SET enable_bitmapscan = on;")
    
    # SQLファイルを取得
    sql_files = sorted(SQL_DIR.glob("*.sql"))
    print(f"処理するクエリ数: {len(sql_files)}")
    
    success_count = 0
    error_count = 0
    
    for sql_file in sql_files:
        query_name = sql_file.stem
        output_file = OUTPUT_DIR / f"{query_name}.json"
        
        try:
            # SQLファイルを読み込み
            sql_query = sql_file.read_text().strip()
            
            # セミコロンを削除（EXPLAINで問題になる場合がある）
            if sql_query.endswith(';'):
                sql_query = sql_query[:-1]
            
            # EXPLAIN (FORMAT JSON)を実行
            explain_result = get_explain_json(cursor, sql_query)
            
            # JSON形式で保存
            with open(output_file, 'w') as f:
                json.dump(explain_result, f, indent=4)
            
            print(f"✓ {query_name}")
            success_count += 1
            
        except Exception as e:
            print(f"✗ {query_name}: {e}")
            error_count += 1
    
    cursor.close()
    conn.close()
    
    print(f"\n完了: 成功={success_count}, エラー={error_count}")
    print(f"出力先: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
