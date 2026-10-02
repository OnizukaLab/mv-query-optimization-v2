#!/usr/bin/env python3
"""
CEBクエリのEXPLAIN (FORMAT JSON)を取得してRED_JSON/ceb/に保存するスクリプト
Bitmap scanを有効にした状態で実行
"""

import os
import json
import psycopg2
import argparse
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
SQL_BASE_DIR = PROJECT_ROOT / "dataset" / "RED_SQL" / "ceb"
OUTPUT_BASE_DIR = PROJECT_ROOT / "dataset" / "RED_JSON" / "ceb"


def get_explain_json(cursor, sql_query: str) -> dict:
    """クエリのEXPLAIN (FORMAT JSON)を取得
    
    Args:
        cursor: PostgreSQLカーソル
        sql_query: 解析するSQLクエリ
        
    Returns:
        EXPLAIN JSON結果
    """
    explain_query = f"EXPLAIN (FORMAT JSON) {sql_query}"
    cursor.execute(explain_query)
    result = cursor.fetchone()[0]
    return result


def process_ceb_queries(cursor, template: str, limit: int = None, verbose: bool = False):
    """指定したCEBテンプレート（例: 1a）のクエリを処理
    
    Args:
        cursor: PostgreSQLカーソル
        template: CEBテンプレート（例: "1a", "2a"）
        limit: 処理するクエリ数の上限（Noneで全て）
        verbose: 詳細ログを出力するか
    """
    sql_dir = SQL_BASE_DIR / template
    output_dir = OUTPUT_BASE_DIR / template
    
    if not sql_dir.exists():
        print(f"❌ ディレクトリが存在しません: {sql_dir}")
        return
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # SQLファイルを取得（自然順ソート）
    sql_files = sorted(sql_dir.glob("*.sql"), key=lambda f: natural_sort_key(f.name))
    
    if limit:
        sql_files = sql_files[:limit]
    
    total = len(sql_files)
    print(f"処理するクエリ数: {total}")
    print(f"入力: {sql_dir}")
    print(f"出力: {output_dir}")
    print("-" * 50)
    
    success_count = 0
    error_count = 0
    errors = []
    
    for i, sql_file in enumerate(sql_files, 1):
        query_name = sql_file.stem
        output_file = output_dir / f"{query_name}.json"
        
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
            
            success_count += 1
            
            if verbose:
                print(f"✓ [{i}/{total}] {query_name}")
            elif i % 100 == 0 or i == total:
                print(f"  進捗: {i}/{total} ({100*i//total}%)")
            
        except Exception as e:
            error_count += 1
            errors.append((query_name, str(e)))
            if verbose:
                print(f"✗ [{i}/{total}] {query_name}: {e}")
    
    print("-" * 50)
    print(f"完了: 成功={success_count}, エラー={error_count}")
    
    if errors and not verbose:
        print("\nエラー一覧（最初の10件）:")
        for name, err in errors[:10]:
            print(f"  - {name}: {err}")


def natural_sort_key(s: str) -> list:
    """自然順ソート用のキー生成"""
    import re
    return [int(text) if text.isdigit() else text.lower() 
            for text in re.split('([0-9]+)', s)]


def list_templates():
    """利用可能なCEBテンプレートを一覧表示"""
    print("\n利用可能なCEBテンプレート:")
    print("-" * 40)
    
    if not SQL_BASE_DIR.exists():
        print(f"❌ ディレクトリが存在しません: {SQL_BASE_DIR}")
        return
    
    for template_dir in sorted(SQL_BASE_DIR.iterdir()):
        if template_dir.is_dir():
            sql_count = len(list(template_dir.glob("*.sql")))
            json_dir = OUTPUT_BASE_DIR / template_dir.name
            json_count = len(list(json_dir.glob("*.json"))) if json_dir.exists() else 0
            
            status = "✅" if json_count == sql_count and sql_count > 0 else "❌" if json_count == 0 else "⚠️"
            print(f"  {status} {template_dir.name}: SQL={sql_count}, JSON={json_count}")


def main():
    parser = argparse.ArgumentParser(
        description='CEB用EXPLAIN JSON生成',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  # CEB 1a の全クエリを処理
  python scripts/get_explain_json_ceb.py --template 1a

  # テスト用: 最初の100クエリのみ処理
  python scripts/get_explain_json_ceb.py --template 1a --limit 100

  # 詳細ログ付きで実行
  python scripts/get_explain_json_ceb.py --template 1a --verbose

  # 利用可能なテンプレートを一覧表示
  python scripts/get_explain_json_ceb.py --list
        """
    )
    parser.add_argument(
        '--template', '-t',
        type=str,
        default='1a',
        help='CEBテンプレート（例: 1a, 2a, 3b）。デフォルト: 1a'
    )
    parser.add_argument(
        '--limit', '-l',
        type=int,
        default=None,
        help='処理するクエリ数の上限（テスト用）'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='詳細ログを出力'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='利用可能なテンプレートを一覧表示'
    )
    parser.add_argument(
        '--host',
        type=str,
        default=DB_CONFIG['host'],
        help=f'データベースホスト（デフォルト: {DB_CONFIG["host"]}）'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=DB_CONFIG['port'],
        help=f'データベースポート（デフォルト: {DB_CONFIG["port"]}）'
    )
    parser.add_argument(
        '--database', '-d',
        type=str,
        default=DB_CONFIG['database'],
        help=f'データベース名（デフォルト: {DB_CONFIG["database"]}）'
    )
    parser.add_argument(
        '--user', '-u',
        type=str,
        default=DB_CONFIG['user'],
        help=f'データベースユーザー（デフォルト: {DB_CONFIG["user"]}）'
    )
    parser.add_argument(
        '--password', '-p',
        type=str,
        default=DB_CONFIG['password'],
        help='データベースパスワード'
    )
    
    args = parser.parse_args()
    
    # テンプレート一覧表示
    if args.list:
        list_templates()
        return
    
    # データベース接続設定を更新
    db_config = {
        'host': args.host,
        'port': args.port,
        'database': args.database,
        'user': args.user,
        'password': args.password
    }
    
    print(f"CEB {args.template} の EXPLAIN JSON を生成します")
    print(f"データベース: {db_config['host']}:{db_config['port']}/{db_config['database']}")
    
    try:
        # データベース接続
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        
        # Bitmap scanを有効にする
        cursor.execute("SET enable_bitmapscan = on;")
        
        # クエリを処理
        process_ceb_queries(cursor, args.template, args.limit, args.verbose)
        
        cursor.close()
        conn.close()
        
    except psycopg2.OperationalError as e:
        print(f"❌ データベース接続エラー: {e}")
        print("\nヒント: PostgreSQLが起動しているか、接続設定が正しいか確認してください。")
        return 1
    except Exception as e:
        print(f"❌ エラー: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
