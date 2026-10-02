#!/usr/bin/env python3
"""データベースセットアップスクリプト

実験用のデータベース環境をセットアップする
"""
import argparse
import os
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def run_sql_file(sql_file: str, verbose: bool = False) -> bool:
    """SQLファイルを実行

    Args:
        sql_file: SQLファイルパス
        verbose: 詳細出力

    Returns:
        成功したかどうか
    """
    if not os.path.exists(sql_file):
        print(f"Error: SQL file not found: {sql_file}")
        return False

    print(f"Executing: {sql_file}")

    # psqlコマンドで実行（環境に応じて調整）
    redirect = "" if verbose else "> /dev/null 2>&1"
    cmd = f"psql -f {sql_file} {redirect}"

    result = os.system(cmd)

    if result == 0:
        print("  ✓ Success")
        return True
    else:
        print("  ✗ Failed")
        return False


def drop_all_mvs(verbose: bool = False) -> None:
    """すべてのマテリアライズドビューを削除

    Args:
        verbose: 詳細出力
    """
    print("\n=== Dropping existing materialized views ===")

    if os.path.exists("delete_mv.sh"):
        redirect = "" if verbose else "> /dev/null 2>&1"
        result = os.system(f"bash delete_mv.sh {redirect}")

        if result == 0:
            print("  ✓ Dropped all MVs")
        else:
            print("  ✗ Failed to drop MVs")
    else:
        print("  Warning: delete_mv.sh not found")


def setup_schema(schema_file: str, verbose: bool = False) -> bool:
    """スキーマをセットアップ

    Args:
        schema_file: スキーマファイル
        verbose: 詳細出力

    Returns:
        成功したかどうか
    """
    print("\n=== Setting up database schema ===")
    return run_sql_file(schema_file, verbose)


def load_data(data_file: str, verbose: bool = False) -> bool:
    """データをロード

    Args:
        data_file: データファイル
        verbose: 詳細出力

    Returns:
        成功したかどうか
    """
    print("\n=== Loading data ===")
    return run_sql_file(data_file, verbose)


def setup_triggers(trigger_file: str, verbose: bool = False) -> bool:
    """トリガーをセットアップ

    Args:
        trigger_file: トリガーファイル
        verbose: 詳細出力

    Returns:
        成功したかどうか
    """
    print("\n=== Setting up triggers ===")
    return run_sql_file(trigger_file, verbose)


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(description="Setup database for MV optimization experiments")

    parser.add_argument("--schema", type=str, default="data/schema.sql", help="Schema SQL file")

    parser.add_argument("--data", type=str, help="Data SQL file")

    parser.add_argument(
        "--triggers", type=str, default="data/triggers.sql", help="Triggers SQL file"
    )

    parser.add_argument(
        "--drop-existing", action="store_true", help="Drop existing materialized views"
    )

    parser.add_argument(
        "--clean", action="store_true", help="Clean setup (drop MVs, recreate schema)"
    )

    parser.add_argument("--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    print("=" * 60)
    print("Database Setup")
    print("=" * 60)

    try:
        # MVクリーンアップ
        if args.drop_existing or args.clean:
            drop_all_mvs(args.verbose)

        # スキーマセットアップ
        if args.schema:
            if not setup_schema(args.schema, args.verbose):
                print("\nWarning: Schema setup failed, continuing...")

        # データロード
        if args.data:
            if not load_data(args.data, args.verbose):
                print("\nError: Data loading failed")
                sys.exit(1)

        # トリガーセットアップ
        if args.triggers and os.path.exists(args.triggers):
            if not setup_triggers(args.triggers, args.verbose):
                print("\nWarning: Trigger setup failed, continuing...")

        print("\n" + "=" * 60)
        print("Database setup completed!")
        print("=" * 60)

    except Exception as e:
        print(f"\nError: Setup failed: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
