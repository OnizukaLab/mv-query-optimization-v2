#!/usr/bin/env python3
"""
データベースのテーブルデータを表示するスクリプト
psqlコマンドを使ってデータを表示します。
"""

import subprocess
import sys
from pathlib import Path


def run_psql_command(command: str, description: str):
    """psqlコマンドを実行して結果を表示"""
    print(f"\n{'='*60}")
    print(f"{description}")
    print(f"{'='*60}")
    
    # ページャーをオフにしてすべての結果を表示
    full_command = f"\\pset pager off\n{command}"
    
    try:
        result = subprocess.run(
            ['psql', '-U', 'postgres', '-d', 'mv_small_test', '-c', full_command],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        if result.returncode == 0:
            print(result.stdout)
        else:
            print(f"エラー: {result.stderr}")
            
    except Exception as e:
        print(f"エラー: {e}")


def display_table_data():
    """テーブルデータを表示"""
    
    # 各テーブルのレコード数
    run_psql_command(
        "SELECT 'users' as table_name, COUNT(*) as count FROM users UNION ALL SELECT 'products', COUNT(*) FROM products UNION ALL SELECT 'orders', COUNT(*) FROM orders;",
        "テーブルごとのレコード数"
    )
    
    # usersテーブルのデータ
    run_psql_command(
        "SELECT user_id, name, age, city, registered_date FROM users ORDER BY user_id LIMIT 10;",
        "USERSテーブル（最初の10件）"
    )
    
    # productsテーブルのデータ
    run_psql_command(
        "SELECT product_id, name, category, price, stock FROM products ORDER BY product_id LIMIT 10;",
        "PRODUCTSテーブル（最初の10件）"
    )
    
    # ordersテーブルのデータ
    run_psql_command(
        "SELECT order_id, user_id, product_id, quantity, order_date, total_amount FROM orders ORDER BY order_id LIMIT 10;",
        "ORDERSテーブル（最初の10件）"
    )
    
    # 統計情報
    run_psql_command(
        "SELECT city, COUNT(*) as user_count FROM users GROUP BY city ORDER BY user_count DESC;",
        "都市別ユーザー数"
    )
    
    run_psql_command(
        "SELECT category, COUNT(*) as product_count FROM products GROUP BY category ORDER BY product_count DESC;",
        "カテゴリ別商品数"
    )


if __name__ == "__main__":
    display_table_data()