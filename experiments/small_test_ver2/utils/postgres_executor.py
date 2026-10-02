#!/usr/bin/env python3
"""
PostgreSQL Executor - Docker/Local switching helper

環境変数 MV_USE_DOCKER=true/false または --use-docker/--use-local フラグで切り替え可能
"""

import os
import subprocess
from typing import Optional


class PostgresExecutor:
    """PostgreSQLコマンド実行のラッパークラス
    
    Docker経由またはローカルpsqlを使い分ける
    
    使い方:
        executor = PostgresExecutor(use_docker=True)
        result = executor.run_psql_command("SELECT 1;", database="imdbload")
    """
    
    def __init__(
        self, 
        use_docker: Optional[bool] = None, 
        container_name: str = "mv_postgres",
        default_user: str = "postgres",
        default_password: str = ""
    ):
        """初期化
        
        Args:
            use_docker: Dockerを使用するかどうか。Noneの場合は環境変数を参照
            container_name: Dockerコンテナ名
            default_user: デフォルトのPostgreSQLユーザー
            default_password: デフォルトのパスワード
        """
        if use_docker is None:
            # 環境変数から取得（デフォルトはTrue = Docker使用）
            env_value = os.environ.get("MV_USE_DOCKER", "true").lower()
            self.use_docker = env_value in ("true", "1", "yes")
        else:
            self.use_docker = use_docker
        
        self.container_name = container_name
        self.default_user = default_user
        self.default_password = default_password
    
    def _build_psql_command(
        self,
        database: str,
        user: Optional[str] = None,
        extra_args: Optional[list] = None
    ) -> list:
        """psqlコマンドを構築
        
        Args:
            database: データベース名
            user: ユーザー名（省略時はdefault_user）
            extra_args: 追加の引数リスト
            
        Returns:
            コマンド引数のリスト
        """
        user = user or self.default_user
        extra_args = extra_args or []
        
        if self.use_docker:
            cmd = [
                "docker", "exec", "-i", self.container_name,
                "psql", "-U", user, "-d", database
            ] + extra_args
        else:
            cmd = ["psql", "-U", user, "-d", database] + extra_args
        
        return cmd
    
    def run_psql_command(
        self,
        sql: str,
        database: str,
        user: Optional[str] = None,
        capture_output: bool = True,
        check: bool = True,
        extra_args: Optional[list] = None,
        env: Optional[dict] = None
    ) -> subprocess.CompletedProcess:
        """SQLコマンドを実行
        
        Args:
            sql: 実行するSQL文
            database: データベース名
            user: ユーザー名
            capture_output: 出力をキャプチャするか
            check: エラー時に例外を発生させるか
            extra_args: 追加のpsql引数
            env: 環境変数（省略時はPGPASSWORDを設定）
            
        Returns:
            subprocess.CompletedProcess
        """
        cmd = self._build_psql_command(database, user, extra_args)
        cmd.extend(["-c", sql])
        
        # 環境変数を設定（ローカルの場合のみPGPASSWORDが必要）
        if env is None:
            env = {**os.environ}
            if not self.use_docker:
                env["PGPASSWORD"] = self.default_password
        
        return subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            check=check,
            encoding='utf-8',
            errors='replace',
            env=env
        )
    
    def run_psql_commands(
        self,
        sql_commands: list,
        database: str,
        user: Optional[str] = None,
        capture_output: bool = True,
        check: bool = True,
        extra_args: Optional[list] = None
    ) -> subprocess.CompletedProcess:
        """複数のSQLコマンドを順次実行
        
        Args:
            sql_commands: 実行するSQL文のリスト
            database: データベース名
            user: ユーザー名
            capture_output: 出力をキャプチャするか
            check: エラー時に例外を発生させるか
            extra_args: 追加のpsql引数
            
        Returns:
            subprocess.CompletedProcess（最後のコマンドの結果）
        """
        base_extra_args = extra_args or []
        cmd = self._build_psql_command(database, user, base_extra_args)
        
        # 各SQLコマンドを-cオプションで追加
        for sql in sql_commands:
            cmd.extend(["-c", sql])
        
        env = {**os.environ}
        if not self.use_docker:
            env["PGPASSWORD"] = self.default_password
        
        return subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            check=check,
            encoding='utf-8',
            errors='replace',
            env=env
        )
    
    def run_explain_json(
        self,
        query_sql: str,
        database: str,
        user: Optional[str] = None,
        set_options: Optional[list] = None
    ) -> subprocess.CompletedProcess:
        """EXPLAIN JSONを実行
        
        Args:
            query_sql: 実行計画を取得するSQL
            database: データベース名
            user: ユーザー名
            set_options: 事前に実行するSET文のリスト
            
        Returns:
            subprocess.CompletedProcess
        """
        explain_sql = f"EXPLAIN (FORMAT JSON, COSTS TRUE, VERBOSE FALSE) {query_sql}"
        
        sql_commands = []
        if set_options:
            sql_commands.extend(set_options)
        sql_commands.append(explain_sql)
        
        return self.run_psql_commands(
            sql_commands,
            database,
            user,
            extra_args=["-t", "-A"]
        )
    
    def get_mode_description(self) -> str:
        """現在のモードの説明を取得"""
        if self.use_docker:
            return f"Docker ({self.container_name})"
        else:
            return "Local psql"


def get_executor_from_args(args) -> PostgresExecutor:
    """argparseの引数からExecutorを作成
    
    Args:
        args: argparse.Namespaceオブジェクト（use_docker属性を持つ）
        
    Returns:
        PostgresExecutor
    """
    use_docker = getattr(args, 'use_docker', None)
    return PostgresExecutor(use_docker=use_docker)


def add_docker_args(parser):
    """argparserにDocker関連の引数を追加
    
    Args:
        parser: argparse.ArgumentParser
    """
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--use-docker',
        action='store_true',
        dest='use_docker',
        default=None,
        help='Docker経由でpsqlを実行（デフォルト、環境変数MV_USE_DOCKERで変更可能）'
    )
    group.add_argument(
        '--use-local',
        action='store_false',
        dest='use_docker',
        help='ローカルのpsqlを使用'
    )
