#!/usr/bin/env python3
"""
EXPLAIN ANALYZE 実行スクリプト

すべてのJOBクエリに対して EXPLAIN (ANALYZE, FORMAT JSON) を実行し、
実測時間を含むJSON結果を保存します。

使い方:
    python experiments/small_test_ver2/scripts/run_explain_analyze.py
    python experiments/small_test_ver2/scripts/run_explain_analyze.py --timeout 300
    python experiments/small_test_ver2/scripts/run_explain_analyze.py --queries 1a 17a 20a
    python experiments/small_test_ver2/scripts/run_explain_analyze.py --use-local  # ローカルpsql使用

    python experiments/small_test_ver2/scripts/run_explain_analyze.py --force

オプション:
    --timeout: クエリタイムアウト秒数（デフォルト: 600秒）
    --queries: 実行する特定のクエリ名（指定しない場合は全クエリ）
    --use-docker: Docker経由でpsql実行
    --use-local: ローカルpsqlを使用
"""

import argparse
import json
import os
import sys
from pathlib import Path
import psycopg2
import psycopg2.extras

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# 実験ディレクトリのutilsを追加
exp_dir = Path(__file__).parent.parent
sys.path.insert(0, str(exp_dir))

from utils.postgres_executor import PostgresExecutor, add_docker_args
from config.settings import Settings


def natural_sort_key(s):
    """自然順ソートのためのキー関数（1a, 1b, 2a... の順にソート）"""
    import re
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split('([0-9]+)', str(s))]


class ExplainAnalyzeRunner:
    """EXPLAIN ANALYZE 実行クラス"""
    
    def __init__(self, use_docker: bool = None, timeout: int = 600):
        """初期化
        
        Args:
            use_docker: Docker経由でpsql実行するか
            timeout: クエリタイムアウト秒数
        """
        self.timeout = timeout
        self.project_root = project_root
        self.exp_dir = exp_dir
        self.queries_dir = self.exp_dir / "01_queries" / "job"
        self.output_dir = self.exp_dir / "02_json" / "job_real"
        
        # PostgresExecutorを使用
        self.pg_executor = PostgresExecutor(use_docker=use_docker)
        
        # 設定を読み込み
        self.settings = Settings()
        
        # 出力ディレクトリ作成
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # データベース接続（再利用）
        self.conn = None
        
        print(f"PostgreSQL実行モード: {self.pg_executor.get_mode_description()}")
        print(f"データベース: {self.settings.database.database}")
    
    def _connect_db(self):
        """データベースに接続（1回のみ）"""
        if self.conn is None:
            self.conn = psycopg2.connect(
                host=self.settings.database.host,
                port=self.settings.database.port,
                database=self.settings.database.database,
                user=self.settings.database.user,
                password=self.settings.database.password
            )
            self.conn.autocommit = True
            
            # 初期設定を実行
            with self.conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = '{self.timeout}s'")
                cur.execute("SET enable_bitmapscan = off")
                cur.execute("SET random_page_cost = 1.1")
    
    def _close_db(self):
        """データベース接続をクローズ"""
        if self.conn is not None:
            self.conn.close()
            self.conn = None
    
    def get_query_files(self, query_names: list = None) -> list:
        """クエリファイル一覧を取得
        
        Args:
            query_names: 特定のクエリ名リスト（Noneの場合は全クエリ）
            
        Returns:
            クエリファイルのパスリスト
        """
        if query_names:
            files = []
            for name in query_names:
                sql_file = self.queries_dir / f"{name}.sql"
                if sql_file.exists():
                    files.append(sql_file)
                else:
                    print(f"⚠ クエリファイルが見つかりません: {sql_file}")
            return sorted(files, key=natural_sort_key)
        else:
            return sorted(self.queries_dir.glob("*.sql"), key=natural_sort_key)
    
    def _convert_select_to_star(self, sql: str) -> str:
        """SELECT句をSELECT *に変換（集約処理を除去）
        
        Args:
            sql: 元のSQL文
            
        Returns:
            SELECT *に変換されたSQL文
        """
        import re
        
        # SELECT ... FROM のパターンをSELECT * FROM に置き換え
        # 大文字小文字区別なし、複数行にまたがる可能性を考慮
        pattern = r'(SELECT\s+).*?(\s+FROM\s+)'
        replacement = r'\1*\2'
        
        converted_sql = re.sub(
            pattern,
            replacement,
            sql,
            count=1,
            flags=re.IGNORECASE | re.DOTALL
        )
        
        return converted_sql
    
    def run_explain_analyze(self, query_file: Path) -> dict:
        """単一クエリに対してEXPLAIN ANALYZEを実行
        
        Args:
            query_file: SQLファイルパス
            
        Returns:
            実行結果のJSON辞書、失敗時はNone
        """
        query_name = query_file.stem
        
        with open(query_file, 'r', encoding='utf-8') as f:
            sql = f.read().strip()
        
        # コメント行を除去
        lines = sql.split('\n')
        sql_lines = [line for line in lines if line.strip() and not line.strip().startswith('--')]
        sql = '\n'.join(sql_lines).strip()
        
        # クエリ終端のセミコロンを削除
        if sql.endswith(';'):
            sql = sql[:-1]
        
        # SELECT句をSELECT *に変換（集約処理を除去）
        sql = self._convert_select_to_star(sql)
        
        # EXPLAIN ANALYZE SQL
        explain_sql = f"EXPLAIN (ANALYZE, FORMAT JSON) {sql}"
        
        try:
            # 既存の接続を使用して実行
            with self.conn.cursor() as cur:
                cur.execute(explain_sql)
                result = cur.fetchone()
                
                if result:
                    return result[0]  # JSON結果を返す
                return None
            
        except psycopg2.errors.QueryCanceled:
            print(f"  ⏱ タイムアウト ({self.timeout}秒)")
            return None
        except Exception as e:
            error_msg = str(e)
            print(f"  ✗ エラー: {error_msg[:100]}")
            return None
    
    def run_all(self, query_names: list = None, force: bool = False):
        """すべてのクエリに対してEXPLAIN ANALYZEを実行
        
        Args:
            query_names: 特定のクエリ名リスト（Noneの場合は全クエリ）
            force: 既存ファイルを上書き
        """
        query_files = self.get_query_files(query_names)
        total = len(query_files)
        
        print("=" * 60)
        print("EXPLAIN ANALYZE 実行")
        print("=" * 60)
        print(f"クエリ数: {total}")
        print(f"タイムアウト: {self.timeout}秒")
        print(f"出力先: {self.output_dir}")
        print("=" * 60)
        
        # データベースに接続（1回のみ）
        print("データベースに接続中...")
        self._connect_db()
        print("接続完了")
        
        success_count = 0
        fail_count = 0
        skip_count = 0
        
        try:
            for i, query_file in enumerate(query_files, 1):
                query_name = query_file.stem
                output_file = self.output_dir / f"{query_name}.json"
                
                # 既に存在する場合はスキップ（forceでない場合）
                if output_file.exists() and not force:
                    print(f"[{i}/{total}] {query_name}: 既に存在（スキップ）")
                    skip_count += 1
                    continue
                
                print(f"[{i}/{total}] {query_name}: 実行中...", end="", flush=True)
                
                result = self.run_explain_analyze(query_file)
                
                if result:
                    # JSON保存
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(result, f, indent=2, ensure_ascii=False)
                    
                    # 実行時間を取得
                    try:
                        exec_time = result[0]["Execution Time"]
                        print(f" ✓ {exec_time:.1f}ms")
                    except (KeyError, IndexError, TypeError):
                        print(" ✓ 完了")
                    
                    success_count += 1
                else:
                    fail_count += 1
        
        finally:
            # データベース接続をクローズ
            self._close_db()
            print("データベース接続をクローズしました")
        
        # サマリー
        print()
        print("=" * 60)
        print("完了サマリー")
        print("=" * 60)
        print(f"成功: {success_count}")
        print(f"失敗: {fail_count}")
        print(f"スキップ: {skip_count}")
        print(f"出力先: {self.output_dir}")


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description='EXPLAIN ANALYZE 実行スクリプト',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--timeout', type=int, default=600,
                        help='クエリタイムアウト秒数（デフォルト: 600）')
    parser.add_argument('--queries', nargs='+',
                        help='実行する特定のクエリ名（例: 1a 17a 20a）')
    parser.add_argument('--force', action='store_true',
                        help='既存ファイルを上書き')
    
    # Docker/Local切り替え引数を追加
    add_docker_args(parser)
    
    args = parser.parse_args()
    
    runner = ExplainAnalyzeRunner(
        use_docker=args.use_docker, 
        timeout=args.timeout
    )
    
    runner.run_all(query_names=args.queries, force=args.force)


if __name__ == "__main__":
    main()
