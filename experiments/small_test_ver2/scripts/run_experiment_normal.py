#!/usr/bin/env python3
"""
小規模実験 - 通常モード実行スクリプト

単一の頻度設定でMV最適化を実行します。

使い方:
    python experiments/small_test/run_experiment_normal.py --phase all
    python experiments/small_test/run_experiment_normal.py --phase 2
"""

import argparse
import json
import logging
import pickle
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# ロギング設定（プルーニングのログを表示するため）
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(name)s - %(message)s'
)

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from src.core.query_parser import QueryParser
from src.optimization.factory import OptimizerFactory
from src.utils.legacy import get_all_job_queries, natural_sort_key

# Docker/Local switching helper
experiment_dir = Path(__file__).parent.parent
sys.path.insert(0, str(experiment_dir))
from utils.postgres_executor import PostgresExecutor, add_docker_args


class NormalModeExperiment:
    """通常モード実験の段階的実行クラス"""
    
    def __init__(self, exp_dir: str = "experiments/small_test_ver2", query_set: str = "job", exp_suffix: str = "", use_docker: Optional[bool] = None, recalc_mode: bool = False, window_size: int = 4):
        """初期化
        
        Args:
            exp_dir: 実験ディレクトリのパス
            query_set: 使用するクエリセット名 (例: job, job_like, explicit_join)
            exp_suffix: 実験識別用サフィックス (例: _16_2, _16_4)
            use_docker: Dockerを使用するかどうか (None: 環境変数から判定)
            recalc_mode: 再計算コストを使用するかどうか
            window_size: 適応的最適化で使用する移動平均の幅（デフォルト: 4）
        """
        self.exp_dir = Path(exp_dir)
        self.query_set = query_set  # クエリセット名を保存
        self.exp_suffix = exp_suffix  # サフィックスを保存
        self.recalc_mode = recalc_mode
        self.window_size = window_size  # 移動平均の幅を保存
        
        # PostgreSQL Executorを初期化
        self.pg_executor = PostgresExecutor(use_docker=use_docker)
        
        # config.yamlを使わず、settings.pyのデフォルト値を使用
        # デフォルト値:
        #   database.password: ""
        #   database.timeout: 1800
        #   optimization.storage_limit_mb: 50
        #   optimization.storage_limit_bytes: 52428800
        #   optimization.insert_queries: 1000
        self.settings = Settings()
        
        # 各ディレクトリのパス（クエリセット別）
        self.queries_dir = self.exp_dir / "01_queries" / self.query_set
        self.json_dir = self.exp_dir / "02_json" / self.query_set
        self.parsed_dir = self.exp_dir / "03_parsed" / self.query_set
        self.optimized_dir = self.exp_dir / "04_optimized" / self.query_set
        self.mv_sql_dir = self.exp_dir / "05_mv_sql" / self.query_set
        self.rewritten_dir = self.exp_dir / "06_rewritten" / self.query_set

        # pickleファイルも03_parsedフォルダ内にクエリセット別で保存
        self.pickle_path = self.parsed_dir / "qp_class.pkl"

        self.qp: Optional[QueryParser] = None
        self.result = None
        
        # 各フェーズの実行時間を記録
        self.phase_times = {}
        
        # クエリセットの存在確認
        if not self.queries_dir.exists():
            print(f"警告: クエリディレクトリが見つかりません: {self.queries_dir}")
            print(f"利用可能なクエリセット:")
            base_dir = self.exp_dir / "01_queries"
            if base_dir.exists():
                for d in base_dir.iterdir():
                    if d.is_dir():
                        print(f"  - {d.name}")
    
    def print_header(self, title: str, phase: int = 0):
        """フェーズヘッダーを表示"""
        print("\n" + "=" * 70)
        if phase > 0:
            print(f"フェーズ {phase}: {title}")
        else:
            print(title)
        print("=" * 70)
    
    def print_success(self, message: str):
        """成功メッセージを表示"""
        print(f"  [OK] {message}")
    
    def print_info(self, message: str):
        """情報メッセージを表示"""
        print(f"  → {message}")
    
    def print_error(self, message: str):
        """エラーメッセージを表示"""
        print(f"  [ERROR] {message}")
    
    def _drop_all_mvs(self):
        """既存のマテリアライズドビューを全て削除"""
        import psycopg2
        
        try:
            conn = psycopg2.connect(
                database=self.settings.database.database,
                user=self.settings.database.user,
                password=self.settings.database.password,
                host='localhost'
            )
            
            with conn.cursor() as cursor:
                # 既存のMVを取得
                cursor.execute("""
                    SELECT schemaname, matviewname 
                    FROM pg_matviews 
                    WHERE schemaname = 'public'
                """)
                mvs = cursor.fetchall()
                
                if not mvs:
                    self.print_info("削除するMVはありません")
                    conn.close()
                    return True
                
                # 全てのMVを削除
                dropped_count = 0
                for schema, mv_name in mvs:
                    try:
                        cursor.execute(f"DROP MATERIALIZED VIEW IF EXISTS {schema}.{mv_name} CASCADE;")
                        dropped_count += 1
                    except Exception as e:
                        self.print_error(f"  {mv_name}の削除に失敗: {e}")
            
            conn.commit()
            conn.close()
            
            self.print_success(f"{dropped_count}個の既存MVを削除完了")
            return True
            
        except Exception as e:
            self.print_error(f"MV削除エラー: {e}")
            return False
    
    def _analyze_base_tables(self):
        """ベーステーブルに対してANALYZEを実行"""
        import psycopg2
        
        # JOB（IMDB）データセットの全ベーステーブル（21テーブル）
        base_tables = [
            # 主要な大規模テーブル
            'title', 'cast_info', 'movie_info', 'movie_companies',
            'movie_keyword', 'name', 'person_info', 'movie_info_idx',
            # その他のエンティティテーブル
            'aka_name', 'aka_title', 'char_name', 'complete_cast',
            'movie_link',
            # ディメンションテーブル（小規模だが重要）
            'keyword', 'company_name', 'company_type', 'info_type',
            'kind_type', 'role_type', 'link_type', 'comp_cast_type'
        ]
        
        try:
            conn = psycopg2.connect(
                database=self.settings.database.database,
                user=self.settings.database.user,
                password=self.settings.database.password,
                host='localhost'
            )
            
            analyzed_count = 0
            with conn.cursor() as cursor:
                # セッションレベルで統計ターゲットを引き上げる（デフォルト100 -> 1000）
                # これによりヒストグラムの粒度が上がり、JOBのような偏ったデータの推定精度が向上する
                # テーブルレベルの永続化は容量とANALYZE時間を圧迫するため、セッションのみで十分
                try:
                    cursor.execute("SET default_statistics_target = 1000;")
                    cursor.execute("SET random_page_cost = 1.1;")
                except Exception as e:
                    pass
                
                for table in base_tables:
                    try:
                        cursor.execute(f"ANALYZE {table};")
                        analyzed_count += 1
                    except Exception:
                        pass  # テーブルが存在しない場合はスキップ
            
            conn.commit()
            conn.close()
            
            self.print_success(f"{analyzed_count}個のベーステーブルをANALYZE完了")
            return True
            
        except Exception as e:
            self.print_error(f"ANALYZE実行エラー: {e}")
            return False

    def _update_u_ij_if_recalc(self):
        """--recalcモードが有効な場合、コストを読み込んでu_ijを更新する
        
        Returns:
            Tuple[Dict[int, float], List[float]]: (migration_cost, b_j) 
            recalcが無効な場合は (None, None) を返す
        """
        if not self.recalc_mode:
            return None, None
            
        from experiments.small_test_ver2.core.io_loaders import load_full_build_costs_and_sizes
        
        self.print_info("RECALC MODE: u_ij（利得）を utility で上書き中...")
        migration_cost, utilities, b_j = load_full_build_costs_and_sizes(
            str(self.exp_dir), 
            self.qp.node_list, 
            self.query_set
        )
        
        updated_count = 0
        for i in range(len(self.qp.u_ij)):
            for j in range(len(self.qp.u_ij[i])):
                # 既存の構造（使用関係）がある場所のみ更新
                if self.qp.u_ij[i][j] > 0:
                    # utilities を使って利得を更新（migration_cost ではなく）
                    if j in utilities:
                        self.qp.u_ij[i][j] = utilities[j]
                        updated_count += 1
                        
        self.print_success(f"  {updated_count}箇所の利得エントリを更新しました")
        return migration_cost, b_j  # migration_cost はそのまま返す（作成コスト用）
    
    def _clear_caches(self):
        """PostgreSQLのキャッシュをクリア
        
        pg_prewarm拡張のpg_drop_caches()を使用してshared_buffersをクリアします。
        PostgreSQL 14以降で利用可能。古いバージョンでは警告を出してスキップします。
        """
        import psycopg2
        
        try:
            conn = psycopg2.connect(
                database=self.settings.database.database,
                user=self.settings.database.user,
                password=self.settings.database.password,
                host='localhost'
            )
            
            with conn.cursor() as cursor:
                # まずpg_prewarm拡張を確認・作成
                try:
                    cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_prewarm;")
                    conn.commit()
                except Exception:
                    pass  # 権限がない場合はスキップ
                
                # pg_drop_caches()を実行してshared_buffersをクリア
                try:
                    cursor.execute("SELECT pg_drop_caches();")
                    conn.commit()
                    self.print_success("PostgreSQLキャッシュをクリア完了")
                except psycopg2.errors.UndefinedFunction:
                    # pg_drop_caches()が存在しない（PostgreSQL 14未満）
                    self.print_info("pg_drop_caches()は利用不可（PostgreSQL 14+が必要）")
                    # 代替手段: DISCARDコマンドでセッションキャッシュをクリア
                    try:
                        cursor.execute("DISCARD ALL;")
                        conn.commit()
                        self.print_info("セッションキャッシュをクリア（DISCARD ALL）")
                    except Exception:
                        pass
                except Exception as e:
                    self.print_info(f"キャッシュクリアをスキップ: {e}")
            
            conn.close()
            return True
            
        except Exception as e:
            self.print_error(f"キャッシュクリアエラー: {e}")
            return False
    
    def _disable_autovacuum(self):
        """全テーブルのautovacuumを無効化（ベンチマーク用）
        
        すべてのユーザーテーブル（ベーステーブルとMV）に対してautovacuumを無効化します。
        これにより、ベンチマーク中のバックグラウンド処理による時間のばらつきを軽減します。
        """
        import psycopg2
        
        try:
            conn = psycopg2.connect(
                database=self.settings.database.database,
                user=self.settings.database.user,
                password=self.settings.database.password,
                host='localhost'
            )
            
            disabled_count = 0
            with conn.cursor() as cursor:
                # publicスキーマ内のすべてのテーブルとMVを取得
                cursor.execute("""
                    SELECT tablename FROM pg_tables WHERE schemaname = 'public'
                    UNION
                    SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'
                """)
                tables = cursor.fetchall()
                
                # 各テーブル/MVに対してautovacuumを無効化
                for (table_name,) in tables:
                    try:
                        cursor.execute(f"ALTER TABLE {table_name} SET (autovacuum_enabled = false);")
                        disabled_count += 1
                    except Exception as e:
                        # テーブルが削除されている場合などはスキップ
                        pass
            
            conn.commit()
            conn.close()
            
            self.print_success(f"Autovacuumを無効化: {disabled_count}個のテーブル/MV")
            return True
            
        except Exception as e:
            self.print_error(f"Autovacuum無効化エラー: {e}")
            return False
    
    def _enable_autovacuum(self):
        """全テーブルのautovacuumを有効化（デフォルトに戻す）
        
        ベンチマーク終了後、すべてのテーブルのautovacuum設定をデフォルトに戻します。
        """
        import psycopg2
        
        try:
            conn = psycopg2.connect(
                database=self.settings.database.database,
                user=self.settings.database.user,
                password=self.settings.database.password,
                host='localhost'
            )
            
            enabled_count = 0
            with conn.cursor() as cursor:
                # publicスキーマ内のすべてのテーブルとMVを取得
                cursor.execute("""
                    SELECT tablename FROM pg_tables WHERE schemaname = 'public'
                    UNION
                    SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'
                """)
                tables = cursor.fetchall()
                
                # 各テーブル/MVのautovacuum設定をリセット（デフォルトに戻す）
                for (table_name,) in tables:
                    try:
                        cursor.execute(f"ALTER TABLE {table_name} RESET (autovacuum_enabled);")
                        enabled_count += 1
                    except Exception as e:
                        # テーブルが削除されている場合などはスキップ
                        pass
            
            conn.commit()
            conn.close()
            
            self.print_success(f"Autovacuumを有効化: {enabled_count}個のテーブル/MV")
            return True
            
        except Exception as e:
            self.print_error(f"Autovacuum有効化エラー: {e}")
            return False
    
    def _force_checkpoint(self):
        """強制的にチェックポイントを実行
        
        ベンチマーク前にチェックポイントを実行することで：
        - WAL（Write-Ahead Log）バッファをクリアして同じ状態からスタート
        - ベンチマーク中の不規則なチェックポイント発生を遅らせる
        - 各実行で同じ初期条件を保証し、時間のばらつきを軽減
        
        チェックポイントは数十秒〜数百秒かかることがあるため、ベンチマーク中に
        ランダムに発生すると大きなばらつきの原因になる。
        """
        import psycopg2
        
        try:
            conn = psycopg2.connect(
                database=self.settings.database.database,
                user=self.settings.database.user,
                password=self.settings.database.password,
                host='localhost'
            )
            
            self.print_info("強制チェックポイントを実行中（WALバッファをクリア）...")
            checkpoint_start = time.time()
            
            with conn.cursor() as cursor:
                # CHECKPOINTコマンドを実行
                # これにより全てのダーティバッファがディスクに書き込まれる
                cursor.execute("CHECKPOINT;")
            
            conn.commit()
            conn.close()
            
            checkpoint_time = time.time() - checkpoint_start
            self.print_success(f"チェックポイント完了 ({checkpoint_time:.2f}秒)")
            return True
            
        except Exception as e:
            self.print_error(f"チェックポイント実行エラー: {e}")
            return False
    
    def _convert_select_to_star(self, query: str) -> str:
        """SELECT句を * に書き換え
        
        MVは SELECT * で作成されるため、EXPLAINも SELECT * で実行することで
        Plan Widthが実際のMVサイズと一致し、サイズ推定精度が向上します。
        
        Args:
            query: 元のSQLクエリ
            
        Returns:
            SELECT句を * に書き換えたクエリ
        """
        import re
        
        # SELECT と FROM の間の部分を * に置き換える
        # グループ1: SELECT + 空白
        # グループ2: FROM + 空白（これは保持）
        # 間の部分（.*?）を * に置き換え
        pattern = r'(SELECT\s+).*?(\s+FROM\s+)'
        replacement = r'\1*\2'
        
        converted = re.sub(pattern, replacement, query, count=1, flags=re.IGNORECASE | re.DOTALL)
        
        return converted
    
    def _create_extended_statistics(self):
        """JOBクエリの推定精度向上のための多変量統計情報（Extended Statistics）を作成
        
        PostgreSQLプランナーが列間の相関を理解できるようにするために、
        複数列の依存関係とMCV（Most Common Values）統計を作成します。
        これにより、複雑なWHERE句を持つクエリの行数推定精度が向上し、
        より適切な結合順序が選択されます。
        """
        import psycopg2
        
        # 作成する統計情報のリスト（効果の高いものだけに厳選）
        # (統計名, 統計タイプ, 対象カラム, テーブル名)
        extended_stats = [
            # ===== 最重要: 大きなテーブルのフィルタ列相関 =====
            # title: 種類と制作年の相関（ほぼ全クエリで効果）
            ("stts_title_kind_year", "(dependencies, mcv)", "kind_id, production_year", "title"),
            
            # movie_info: 情報タイプと内容の相関（クエリの30%で使用）
            ("stts_movie_info_corr", "(dependencies, mcv)", "info_type_id, info", "movie_info"),
            
            # cast_info: 役割と注釈の相関（10c, 25c, 20aなどで効果大）
            ("stts_cast_info_note", "(dependencies, mcv)", "role_id, note", "cast_info"),
            
            # ===== 重要: 結合キー+フィルタの相関（結合後の行数推定に効果）=====
            # movie_info: 映画IDと情報タイプ（結合の中間結果推定）
            ("stts_mi_movie_info", "(dependencies, mcv)", "movie_id, info_type_id", "movie_info"),
            
            # cast_info: 映画IDと役割（大規模JOIN推定）
            ("stts_ci_join_corr", "(dependencies, mcv)", "movie_id, role_id", "cast_info"),
            
            # movie_companies: 映画と会社種別（17系クエリで効果）
            ("stts_mc_movie_company", "(dependencies, mcv)", "movie_id, company_type_id", "movie_companies"),
            
            # ===== やや重要: よく使われる中規模テーブル =====
            # movie_keyword: 映画とキーワード（6f, 29cなどで使用）
            ("stts_mk_movie_keyword", "(dependencies, mcv)", "movie_id, keyword_id", "movie_keyword"),
            
            # person_info: 情報タイプと内容（7c, 29cで効果）
            ("stts_person_info_corr", "(dependencies, mcv)", "info_type_id, info", "person_info"),
        ]
        
        try:
            conn = psycopg2.connect(
                database=self.settings.database.database,
                user=self.settings.database.user,
                password=self.settings.database.password,
                host='localhost'
            )
            
            created_count = 0
            skipped_count = 0
            
            with conn.cursor() as cursor:
                for stat_name, stat_type, columns, table in extended_stats:
                    try:
                        # 既存の統計情報をドロップ（存在する場合）
                        cursor.execute(f"DROP STATISTICS IF EXISTS {stat_name};")
                        
                        # 新しい統計情報を作成
                        sql = f"CREATE STATISTICS {stat_name} {stat_type} ON {columns} FROM {table};"
                        cursor.execute(sql)
                        created_count += 1
                        
                    except psycopg2.errors.UndefinedTable:
                        # テーブルが存在しない場合はスキップ
                        conn.rollback()
                        skipped_count += 1
                    except psycopg2.errors.UndefinedColumn:
                        # カラムが存在しない場合はスキップ
                        conn.rollback()
                        skipped_count += 1
                    except Exception as e:
                        # その他のエラーはログに記録してスキップ
                        conn.rollback()
                        self.print_info(f"  統計 {stat_name} の作成をスキップ: {e}")
                        skipped_count += 1
                
                conn.commit()
            
            conn.close()
            
            if created_count > 0:
                self.print_success(f"{created_count}個の拡張統計情報を作成完了")
                if skipped_count > 0:
                    self.print_info(f"  {skipped_count}個はスキップ（テーブルまたはカラムが存在しない）")
            else:
                self.print_info("拡張統計情報の作成をスキップ（対象テーブルが存在しない）")
            
            return True
            
        except Exception as e:
            self.print_error(f"拡張統計情報作成エラー: {e}")
            return False
    
    def phase1_generate_explain_json(self):
        """フェーズ1: EXPLAIN JSON 生成"""
        self.print_header("EXPLAIN JSON 生成", 1)
        
        # 既存のMVを全て削除
        self.print_info("既存のMVをクリーンアップ中...")
        if not self._drop_all_mvs():
            self.print_error("MVの削除に失敗しました")
            # 失敗しても続行（警告のみ）
        
        # ベーステーブルの統計情報を更新（実験全体で統計を固定するため）
        # NOTE: Phase 9のベンチマークでは実行しない（統計情報のばらつき防止）
        # ANALYZEはランダムサンプリングを使用するため、実行ごとに微妙に異なる統計が生成され、
        # クエリプランが変動してベンチマーク結果にばらつきが生じる可能性がある
        self.print_info("ベーステーブルの統計情報を更新中（実験全体で固定）...")
        if not self._analyze_base_tables():
            self.print_error("ベーステーブルのANALYZEに失敗しました")
            # 失敗しても続行（警告のみ）
        
        # 拡張統計情報（Extended Statistics）を作成
        # JOBクエリの結合順序推定精度を向上させるための多変量統計

        # self.print_info("拡張統計情報を作成中...")
        # if not self._create_extended_statistics():
        #     self.print_error("拡張統計情報の作成に失敗しました")
        #     # 失敗しても続行（警告のみ）
        
        # PostgreSQLキャッシュをクリア
        # self.print_info("PostgreSQLキャッシュをクリア中...")
        # self._clear_caches()
        # クリーンアップが完了してから計測開始
        phase_start = time.time()
        
        # クエリディレクトリの確認
        if not self.queries_dir.exists():
            self.print_error(f"クエリディレクトリが見つかりません: {self.queries_dir}")
            return False
        
        query_files = sorted(self.queries_dir.glob("*.sql"))
        
        if not query_files:
            self.print_error(f"{self.queries_dir} にクエリファイルが見つかりません")
            return False
        
        self.print_info(f"クエリセット: {self.query_set}")
        self.print_info(f"{len(query_files)}個のクエリファイルを処理します")
        
        # 出力ディレクトリを作成(クエリセット別)
        self.json_dir.mkdir(parents=True, exist_ok=True)
        
        for query_file in query_files:
            output_file = self.json_dir / f"{query_file.stem}.json"
            
            self.print_info(f"処理中: {query_file.name}")
            
            # クエリを読み込み（コメント行を除去）
            with open(query_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            query_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped and not stripped.startswith('--'):
                    query_lines.append(line)
            
            query_sql = ''.join(query_lines).strip()
            
            # ★★★ SELECT句を * に書き換え ★★★
            # MVは SELECT * で作成されるため、EXPLAINも SELECT * で実行することで
            # Plan Widthが実際のMVサイズと一致し、サイズ推定精度が向上する
            query_sql_star = self._convert_select_to_star(query_sql)
            
            # EXPLAIN JSON を実行（Bitmap Scanを無効化 + 統計精度向上）
            # SET文とEXPLAINを分けて実行し、EXPLAIN結果のみを取得
            
            try:
                result = self.pg_executor.run_explain_json(
                    query_sql_star,  # ← SELECT * 版を使用
                    database=self.settings.database.database,
                    set_options=[
                        "SET enable_bitmapscan = off;",
                        "SET default_statistics_target = 1000;",
                        "SET random_page_cost = 1.1;"
                    ]
                )
                
                # 出力から最後のJSON部分のみを抽出（SET文の出力を除外）
                output_lines = result.stdout.strip().split('\n')
                # "SET"行を除外してJSONのみを取得
                json_lines = [line for line in output_lines if line and line != 'SET']
                json_text = '\n'.join(json_lines)
                json_data = json.loads(json_text)
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, indent=2, ensure_ascii=False)
                
                self.print_success(f"{output_file.name} を生成")
                
            except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
                self.print_error(f"{query_file.name} の処理に失敗: {e}")
                return False
        
        return True
    
    def phase2_parse_queries(self):
        """フェーズ2: クエリパース（頻度重み付けを行わないように変更済み）"""
        self.print_header("クエリパース", 2)
        phase_start = time.time()
        
        # from experiments.small_test_ver2.frequency_weighted_parser import FrequencyWeightedParser
        
        # self.print_info("FrequencyWeightedParser を初期化")
        
        # frequency_file = self.queries_dir / "frequency.json"
        
        # if frequency_file.exists():
           # self.print_info(f"頻度情報ファイル: {frequency_file}")
           # self.qp = FrequencyWeightedParser(self.settings, str(frequency_file))
    
        # self.print_info("頻度情報ファイルが見つかりません。通常のパーサーを使用")
        self.qp = QueryParser(self.settings)
        
        self.print_info("クエリをパース中...")
        try:
            query_dir = str(self.json_dir)
            
            # JSONファイルの確認
            json_files = list(self.json_dir.glob("*.json"))
            self.print_info(f"検出されたJSONファイル: {len(json_files)}個")
            if json_files:
                self.print_info(f"  例: {json_files[0].name}")
            
            # モンキーパッチ: query_parser モジュール内の get_all_job_queries を置き換え
            # この部分ややこしいから簡単にしたいけどquery_parser.pyをいじる必要がある
            import src.core.query_parser as qp_module
            original_get_all_job_queries = qp_module.get_all_job_queries
            
            def custom_get_all_job_queries(path):
                """カスタム関数: 指定ディレクトリから直接JSONファイルを取得"""
                import re
                
                def natural_sort_key(s):
                    return [int(text) if text.isdigit() else text.lower() for text in re.split("([0-9]+)", str(s))]
                
                query_paths = []
                query_count = {}
                
                job_dir = Path(path)
                print(f"  [DEBUG] custom_get_all_job_queries called with path: {path}")
                print(f"  [DEBUG] Directory exists: {job_dir.exists()}")
                
                if not job_dir.exists():
                    return [], {}
                
                # 自然順でソート
                json_files = sorted(job_dir.glob("*.json"), key=lambda x: natural_sort_key(x.name))
                
                for json_file in json_files:
                    query_path = str(json_file)
                    query_paths.append(query_path)
                    query_count[query_path] = 1
                
                print(f"  [DEBUG] Found {len(query_paths)} JSON files (sorted naturally)")
                return query_paths, query_count
            
            # query_parser モジュール内の参照を置き換え
            qp_module.get_all_job_queries = custom_get_all_job_queries
            
            try:
                self.qp.query_parse(
                    q_num=0,
                    path=str(self.json_dir),
                    insert_query=self.settings.optimization.insert_queries,
                    sql_dir=str(self.queries_dir)
                )
            finally:
                # 元の関数に戻す
                qp_module.get_all_job_queries = original_get_all_job_queries
            
            insert_query = self.settings.optimization.insert_queries
            
            #if isinstance(self.qp, FrequencyWeightedParser):
             #   self.qp.apply_frequency_weights(files)
              #  self.qp.calculate_maintenance_costs(insert_query)
            
            self.print_success(f"{len(self.qp.query)}個のクエリをパース完了")
            self.print_info(f"  リーフノード数: {len(self.qp.qm.leaf_nodes_map)}")
            self.print_info(f"  非リーフノード数: {len(self.qp.qm.non_leaf_nodes_map)}")
            self.print_info(f"  総ノード数: {self.qp.s_num}")
            
            self._save_parse_results()
            
            # フェーズ時間を記録
            self.phase_times['phase2_parse'] = time.time() - phase_start
            
            return True
            
        except Exception as e:
            self.print_error(f"クエリパースに失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
    
# フェーズ2.5のみ実行
# python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 2.5 --query-set job

    def phase3_annotate_json(self):
        """フェーズ3: JSONファイルへのノードID付加"""
        self.print_header("JSONファイルへのノードID付加", 3)
        phase_start = time.time()
        
        if self.qp is None:
            if not self.pickle_path.exists():
                self.print_error(f"{self.pickle_path} が見つかりません")
                self.print_info("先にフェーズ2を実行してください")
                return False
            
            self.print_info(f"パース結果を読み込み中: {self.pickle_path}")
            try:
                with open(self.pickle_path, 'rb') as f:
                    self.qp = pickle.load(f)
                self.print_success(f"{self.qp.s_num}個のノードを読み込み完了")
            except Exception as e:
                self.print_error(f"パース結果の読み込みに失敗: {e}")
                return False
        
        # JSONファイルの一覧を取得
        json_files = sorted(self.json_dir.glob("*.json"))
        
        if not json_files:
            self.print_error(f"{self.json_dir} にJSONファイルが見つかりません")
            return False
        
        self.print_info(f"{len(json_files)}個のJSONファイルを処理します")
        
        try:
            from src.core.parse_exporter import ParseExporter
            
            # ParseExporterを初期化
            exporter = ParseExporter(self.qp.qm)
            
            # JSONファイルを直接上書きする（output_dirを同じディレクトリに設定）
            self.print_info("ノードIDを付加中...")
            
            # 一時ディレクトリに出力してから上書き
            temp_dir = self.json_dir.parent / f".temp_{self.query_set}"
            
            # 注釈付きファイルを一時ディレクトリに出力
            exporter.annotate_query_files(
                [str(f) for f in json_files],
                temp_dir
            )
            
            # 一時ディレクトリから元の場所に移動（上書き）
            annotated_files = list(temp_dir.glob("*.json"))
            for annotated_file in annotated_files:
                target_file = self.json_dir / annotated_file.name
                import shutil
                shutil.move(str(annotated_file), str(target_file))
            
            # 一時ディレクトリを削除
            if temp_dir.exists():
                import shutil
                shutil.rmtree(temp_dir)
            
            self.print_success(f"{len(json_files)}個のJSONファイルにノードIDを付加完了")
            self.print_info(f"  更新先: {self.json_dir}")
            
            # フェーズ時間を記録
            self.phase_times['phase3_annotate_json'] = time.time() - phase_start
            
            return True
            
        except Exception as e:
            self.print_error(f"ノードID付加に失敗: {e}")
            import traceback
            traceback.print_exc()
            
            # エラー時に一時ディレクトリをクリーンアップ
            if temp_dir.exists():
                import shutil
                shutil.rmtree(temp_dir)
            
            return False
    
    def _save_parse_results(self):
        """パース結果を保存"""
        # pickleファイル保存先のディレクトリを作成
        self.pickle_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.pickle_path, 'wb') as f:
            pickle.dump(self.qp, f)
        
        self.print_success(f"パース結果を {self.pickle_path} に保存")
        
        summary = {
            "num_queries": len(self.qp.query),
            "num_leaf_nodes": len(self.qp.qm.leaf_nodes_map),
            "num_non_leaf_nodes": len(self.qp.qm.non_leaf_nodes_map),
            "total_nodes": self.qp.s_num,
            "node_list": self.qp.node_list,
            "u_ij_shape": [len(self.qp.u_ij), len(self.qp.u_ij[0]) if self.qp.u_ij else 0],
            "b_j_length": len(self.qp.b_j),
            "m_cost_length": len(self.qp.m_cost),
        }
        summary_path = self.parsed_dir / "parse_summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        self.print_success(f"サマリーを {summary_path} に保存")
    
    def phase4_enumerate_migration_plans(self):
        """フェーズ4: マイグレーションプラン列挙"""
        self.print_header("マイグレーションプラン列挙", 4)
        phase_start = time.time()
        
        if self.qp is None:
            if not self.pickle_path.exists():
                self.print_error(f"{self.pickle_path} が見つかりません")
                self.print_info("先にフェーズ2を実行してください")
                return False
            
            self.print_info(f"パース結果を読み込み中: {self.pickle_path}")
            try:
                with open(self.pickle_path, 'rb') as f:
                    self.qp = pickle.load(f)
                self.print_success(f"{self.qp.s_num}個のノードを読み込み完了")
            except Exception as e:
                self.print_error(f"パース結果の読み込みに失敗: {e}")
                return False
        
        try:
            from experiments.small_test_ver2.migration.enumerate_simple_migration_plan import GetSimpleMigrationPlans
            
            self.print_info("マイグレーションプランを列挙中...")
            
            # GetSimpleMigrationPlansのインスタンスを作成
            migrator = GetSimpleMigrationPlans(
                settings=self.settings,
                query_set=self.query_set
            )
            
            # マイグレーションプランを取得・保存
            migrator.get_migration_sqls()
            
            # 出力ファイルのパスを確認
            output_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_plans.json"
            
            if output_file.exists():
                self.print_success(f"マイグレーションプランを保存: {output_file}")
                
                # ファイルの統計情報を表示
                with open(output_file, 'r', encoding='utf-8') as f:
                    plans = json.load(f)
                self.print_info(f"  {len(plans)}個のノードのプランを生成")
            else:
                self.print_error("マイグレーションプランファイルが見つかりません")
                return False
            
            # フェーズ時間を記録
            self.phase_times['phase4_migration_plans'] = time.time() - phase_start
            
            return True
            
        except Exception as e:
            self.print_error(f"マイグレーションプラン列挙に失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def phase5_calculate_migration_costs(self, use_neurocard=False, use_deepdb=False, use_sampling=True, compare=False):
        """フェーズ5: マイグレーションコスト計算"""
        self.print_header("マイグレーションコスト計算", 5)
        phase_start = time.time()
        
        # job_realの場合は実測値からコストを生成
        if self.query_set == "job_real":
            from experiments.small_test_ver2.migration.actual_cost_migration_calculator import ActualCostMigrationCalculator
            CalculatorClass = ActualCostMigrationCalculator
            self.print_info("実測値（job_real）を使用してコストを生成します")
        else:
            # マイグレーションプランファイルの存在確認
            plans_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_plans.json"
            
            if not plans_file.exists():
                self.print_error("マイグレーションプランが見つかりません")
                self.print_info("先にフェーズ2.7を実行してください")
                return False
        
        try:
            # job_real以外の場合、使用するCalculatorを選択
            if self.query_set != "job_real":
                if use_neurocard:
                    from experiments.small_test_ver2.migration.neurocard_migration_cost_calculator import NeuroCardMigrationCostCalculator
                    CalculatorClass = NeuroCardMigrationCostCalculator
                    self.print_info("NeuroCardを使用してサイズ推定を行います")
                elif use_deepdb:
                    from experiments.small_test_ver2.migration.deepdb_migration_cost_calculator import DeepDBMigrationCostCalculator
                    CalculatorClass = DeepDBMigrationCostCalculator
                    self.print_info("DeepDBを使用してサイズ推定を行います")
                elif use_sampling:
                    from experiments.small_test_ver2.migration.sampling_migration_cost_calculator import SamplingMigrationCostCalculator
                    CalculatorClass = SamplingMigrationCostCalculator
                    self.print_info("サンプリングを使用してサイズ推定を行います")
                else:
                    from experiments.small_test_ver2.migration.simple_migration_cost_calculator import SimpleMigrationCostCalculator
                    CalculatorClass = SimpleMigrationCostCalculator

            
            self.print_info("マイグレーションコストを計算中...")
            
            # CostCalculatorのインスタンスを作成
            if self.recalc_mode and use_sampling and self.query_set != "job_real":
                recalc_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_costs.json"
                # SamplingMigrationCostCalculatorのみがprecomputed_costs_fileを受け取る
                calculator = CalculatorClass(
                    settings=self.settings,
                    query_set=self.query_set,
                    precomputed_costs_file=str(recalc_file)
                )
            else:
                calculator = CalculatorClass(
                    settings=self.settings,
                    query_set=self.query_set
                )
            
            if compare and use_deepdb:
                self.print_info("PostgreSQL と DeepDB の推定値を比較します")
                calculator.compare_with_postgresql()
                # 比較のみの場合はここで終了（コスト保存は行わない）
                self.phase_times['phase5_migration_costs'] = time.time() - phase_start
                return True
            
            # コストを計算・保存
            costs = calculator.calculate_all_costs()
            
            # 出力ファイルのパスを確認（Calculatorによって出力ファイル名が異なる可能性があるため、ここではチェックを柔軟にするか統一する）
            # deepdb_migration_cost_calculator も simple_migration_costs.json に保存するように修正済み
            output_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_costs.json"
            
            if output_file.exists():
                self.print_success(f"マイグレーションコストを保存: {output_file}")
                self.print_info(f"  {len(costs)}個のノードのコストを計算")
            else:
                # ファイルが見つからない場合でも、計算処理自体が正常終了していれば成功とみなす場合もあるが、
                # 基本的にはファイル生成が目的
                self.print_warning("マイグレーションコストファイルが見つかりません (保存処理がスキップされた可能性があります)")
            
            # フェーズ時間を記録
            self.phase_times['phase5_migration_costs'] = time.time() - phase_start
            
            return True
            
        except Exception as e:
            self.print_error(f"マイグレーションコスト計算に失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
        
    def phase6_optimize(self, mode='dynamic', use_pruning=False, pruning_parallel=False, pruning_workers=None, static_timestep='last', use_static_protection=False, static_algorithm='normal', b_max=None, inherit_parent_constraints=True):
        """フェーズ6: MV最適化

        Args:
            mode: 'static', 'dynamic', または 'adaptive' (デフォルト: 'dynamic')
            use_pruning: プルーニングを使用するかどうか (デフォルト: False)
            pruning_parallel: プルーニングを並列実行するかどうか (デフォルト: False)
            pruning_workers: 並列実行時のワーカー数 (デフォルト: CPUコア数)
            static_timestep: 静的最適化時のタイムステップ ('first' or 'last')
            use_static_protection: 静的最適化のMVを聖域として保護する (デフォルト: False)
            static_algorithm: 静的最適化アルゴリズム ('normal', 'bigsubs', 'both')
            inherit_parent_constraints: WSTにおける親ノードからの境界制約伝播 (デフォルト: True)
        """
        # 最初にモードで分岐
        if mode == 'static':
            return self.phase6b_optimize_static(timestep_position=static_timestep, static_algorithm=static_algorithm, b_max=b_max)
        elif mode == 'adaptive':
            return self.phase6c_optimize_adaptive(window_size=self.window_size, b_max=b_max)
        
        # 以下は dynamic モードの処理
        self.print_header("ILP最適化（時間依存型）", 6)
        
        if not self.pickle_path.exists():
            self.print_error(f"{self.pickle_path} が見つかりません")
            self.print_info("先にフェーズ2を実行してください")
            return False
        
        if self.qp is None:
            self.print_info(f"パース結果を読み込み中: {self.pickle_path}")
            try:
                with open(self.pickle_path, 'rb') as f:
                    self.qp = pickle.load(f)
                self.print_success(f"{self.qp.s_num}個のノードを読み込み完了")
            except Exception as e:
                self.print_error(f"パース結果の読み込みに失敗: {e}")
                return False
        
        self.print_info("時間依存型最適化（マイグレーションコスト考慮）を実行")
        if use_pruning:
            mode_str = "並列" if pruning_parallel else "逐次"
            self.print_info(f"  プルーニングを使用します（{mode_str}実行）")
            if use_static_protection:
                self.print_info(f"  静的保護: 有効（ハイブリッドアプローチ）")
            self.print_info(f"  WST親制約伝播: {'有効' if inherit_parent_constraints else '無効'}")
            if pruning_parallel:
                import multiprocessing
                workers = pruning_workers or multiprocessing.cpu_count()
                self.print_info(f"  ワーカー数: {workers}")
        
        # フェーズ時間計測開始
        phase_start = time.time()
        
        try:
            from experiments.small_test_ver2.core.io_loaders import (
                load_timesteps_and_frequencies,
                load_full_build_costs_and_sizes,
            )
            from experiments.small_test_ver2.core.time_dependent_optimizer import TimeDependentOptimizer
            
            # ストレージ予算
            B_max = float((b_max if b_max is not None else 100) * 1024 * 1024)
            
            # タイムステップと頻度を読み込み
            self.print_info("タイムステップと頻度情報を読み込み中...")
            timesteps, frequencies = load_timesteps_and_frequencies(str(self.exp_dir), self.query_set, freq_suffix=self.exp_suffix)
            self.print_success(f"  タイムステップ数: {len(timesteps)}")
            
            # 頻度の次元を検証・調整
            query_count = len(self.qp.u_ij)
            for ts in timesteps:
                if len(frequencies[ts]) != query_count:
                    self.print_info(f"  頻度数を調整: {ts} ({len(frequencies[ts])} -> {query_count})")
                    if len(frequencies[ts]) < query_count:
                        frequencies[ts].extend([1.0] * (query_count - len(frequencies[ts])))
                    else:
                        frequencies[ts] = frequencies[ts][:query_count]
            
            # マイグレーションコストをsubquery_costsから取得（u_ijとスケール一致）
            # self.print_info("マイグレーションコストを計算中...")
            # migration_cost = {
            #     j: self.qp.qm.subquery_costs[node_id]
            #     for j, node_id in enumerate(self.qp.node_list)
            # }
            
            # --recalc モードの場合、ロードしたコストで u_ij を上書きし、そのコストを使用
            migration_cost, b_j_from_migration = self._update_u_ij_if_recalc()
            
            if migration_cost is None:
                # 通常モード：サイズとコストを読み込む
                migration_cost, _, b_j_from_migration = load_full_build_costs_and_sizes(
                    str(self.exp_dir), 
                    self.qp.node_list, 
                    self.query_set
                )
                self.print_success(f"  {len(migration_cost)}個のMVのマイグレーションコストを計算完了（subquery_costsベース）")

            # プルーニングを実行（オプション）
            pruning_info = None
            candidate_filter = None
            if use_pruning:
                from experiments.small_test_ver2.core.cf_pruner import CFPruner
                
                self.print_info("CF Pruningを実行中...")
                pruning_start = time.time()
                
                pruner = CFPruner(
                    node_list=self.qp.node_list,
                    u_ij=self.qp.u_ij,
                    X=self.qp.X,
                    b_j=b_j_from_migration,
                    B_max=B_max,
                    timesteps=timesteps,
                    migration_cost=migration_cost,
                    query_frequency_by_timestep=frequencies,
                    gurobi_output=0,  # プルーニング中は静かに
                    use_parallel=pruning_parallel,
                    max_workers=pruning_workers,
                    inherit_parent_constraints=inherit_parent_constraints,
                )
                
                promising_mvs = pruner.prune_candidates(use_static_protection=use_static_protection)
                pruning_time = time.time() - pruning_start
                
                pruning_info = pruner.get_filtering_info(promising_mvs)
                candidate_filter = promising_mvs
                
                self.print_success(
                    f"  プルーニング完了 ({pruning_time:.2f}秒): "
                    f"{pruning_info['promising_candidates']}/{pruning_info['total_candidates']} MVが有望 "
                    f"({pruning_info['reduction_rate']*100:.1f}% 削減)"
                )
                
                # 結果ディレクトリを準備
                result_dir = self.exp_dir / "time_dependent_output" / self.query_set
                result_dir.mkdir(parents=True, exist_ok=True)
                
                # プルーニング結果を保存
                pruning_result_file = result_dir / f"pruning_result{self.exp_suffix}.json"
                with open(pruning_result_file, 'w', encoding='utf-8') as f:
                    json.dump(pruning_info, f, indent=2, ensure_ascii=False)
                self.print_success(f"  プルーニング結果を {pruning_result_file} に保存")
            
            # オプティマイザを初期化
            self.print_info("オプティマイザを初期化中...")
            optimizer = TimeDependentOptimizer(
                node_list=self.qp.node_list,
                u_ij=self.qp.u_ij,
                X=self.qp.X,
                b_j=b_j_from_migration,  # Phase 5のEXPLAIN結果からのサイズを使用
                B_max=B_max,
                timesteps=timesteps,
                migration_cost=migration_cost,
                query_frequency_by_timestep=frequencies,
                gurobi_output=1,
            )
            
            # プルーニング結果を適用（候補フィルタリング）
            if candidate_filter is not None:
                original_cand = optimizer.cand_j.copy()
                optimizer.set_candidates([j for j in optimizer.cand_j if j in candidate_filter])
                self.print_info(
                    f"  候補をフィルタリング: {len(original_cand)} -> {len(optimizer.cand_j)}"
                )
            
            # 最適化を実行
            self.print_info("最適化を実行中...")
            result = optimizer.optimize()
            
            # マイグレーション分析
            self.print_info("マイグレーション分析を実行中...")
            enhanced_result = self._analyze_migration_transitions(result, migration_cost, b_j_from_migration, B_max)
            
            # プルーニング情報を結果に追加
            if pruning_info:
                enhanced_result['pruning_info'] = pruning_info
                enhanced_result['pruning_time_sec'] = pruning_time
            
            # フェーズ時間を記録
            phase_time = time.time() - phase_start
            self.phase_times['phase6_optimization'] = phase_time
            enhanced_result['phase_time_sec'] = phase_time
            
            # 結果を表示
            self.print_success("最適化完了")
            self.print_info(f"  総目的関数値: {enhanced_result['objective']:.4f}")
            self.print_info(f"  ワークロードコスト: {enhanced_result['workload_cost']:.4f}")
            self.print_info(f"  マイグレーションコスト: {enhanced_result['migration_cost']:.4f}")
            self.print_info(f"  ILP求解時間: {enhanced_result['solve_time_sec']:.2f} 秒")
            if pruning_info:
                self.print_info(f"  プルーニング時間: {pruning_time:.2f} 秒")
            self.print_info(f"  フェーズ総実行時間: {phase_time:.2f} 秒")
            
            # 結果を保存（run_time_dependent_with_migration.pyと同じディレクトリ構造）
            # z_by_timestep と y_by_timestep は Phase 7以降で不要なので除外してファイルサイズを削減
            result_to_save = {k: v for k, v in enhanced_result.items() 
                            if k not in ('z_by_timestep', 'y_by_timestep')}
            
            result_dir = self.exp_dir / "time_dependent_output" / self.query_set
            result_dir.mkdir(parents=True, exist_ok=True)
            result_file = result_dir / f"td_mv_optimization_result{self.exp_suffix}.json"
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result_to_save, f, indent=2, ensure_ascii=False)
            self.print_success(f"結果を {result_file} に保存")
            
            # 結果をインスタンス変数に保存（後続フェーズで使用）
            self.result = enhanced_result
            
            return True

        except Exception as e:
            self.print_error(f"最適化に失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _analyze_migration_transitions(self, result: dict, migration_cost: dict, b_j: list, B_max: float) -> dict:
        """マイグレーション遷移を分析
        
        Args:
            result: 最適化結果
            migration_cost: マイグレーションコスト（フルビルド）
            b_j: 各MVのサイズリスト（Phase 5のEXPLAIN結果から取得）
            B_max: ストレージ予算
        """
        timesteps = result["timesteps"]
        z_by_timestep = result["z_by_timestep"]
        
        migration_analysis = []
        
        for t in range(len(timesteps)):
            timestep_name = timesteps[t]
            current_mvs = set(j for j, v in enumerate(z_by_timestep[t]) if v == 1)
            
            # タイムステップごとの情報
            selected_nodes = [self.qp.node_list[j] for j in sorted(current_mvs)]
            total_size = sum(b_j[j] for j in current_mvs)  # 正しいb_jを使用
            utilization = (total_size / B_max * 100) if B_max > 0 else 0
            
            timestep_info = {
                "timestep": timestep_name,
                "selected_mvs": selected_nodes,
                "mv_count": len(current_mvs),
                "total_size": round(total_size, 2),
                "storage_budget": round(B_max, 2),
                "utilization_percent": round(utilization, 2)
            }
            
            # マイグレーション情報（t > 0の場合）
            if t > 0:
                prev_mvs = set(j for j, v in enumerate(z_by_timestep[t-1]) if v == 1)
                
                maintained = current_mvs & prev_mvs
                created = current_mvs - prev_mvs
                deleted = prev_mvs - current_mvs
                
                migration_details = {
                    "from_timestep": timesteps[t-1],
                    "to_timestep": timestep_name,
                    "maintained": {
                        "count": len(maintained),
                        "mvs": [self.qp.node_list[j] for j in sorted(maintained)],
                        "total_size": round(sum(b_j[j] for j in maintained), 2)  # 正しいb_jを使用
                    },
                    "created": {
                        "count": len(created),
                        "mvs": [self.qp.node_list[j] for j in sorted(created)],
                        "total_size": round(sum(b_j[j] for j in created), 2)  # 正しいb_jを使用
                    },
                    "deleted": {
                        "count": len(deleted),
                        "mvs": [self.qp.node_list[j] for j in sorted(deleted)],
                        "total_size": round(sum(b_j[j] for j in deleted), 2)  # 正しいb_jを使用
                    }
                }
                
                # 作成コストの計算
                creation_cost = 0.0
                creation_details = []
                
                for j in sorted(created):
                    cost = migration_cost.get(j, float("inf"))
                    creation_cost += cost
                    creation_details.append({
                        "mv": self.qp.node_list[j],
                        "size": round(b_j[j], 2),
                        "cost": round(cost, 2),
                        "dependencies": [] # 簡易化のため依存関係は空（フルビルド）
                    })
                
                migration_details["creation_cost"] = round(creation_cost, 2)
                migration_details["creation_details"] = creation_details
                
                timestep_info["migration"] = migration_details
            else:
                # 初期タイムステップ
                initial_cost = 0.0
                creation_details = []
                
                for j in sorted(current_mvs):
                    cost = migration_cost.get(j, 0.0)
                    initial_cost += cost
                    creation_details.append({
                        "mv": self.qp.node_list[j],
                        "size": round(b_j[j], 2),
                        "cost": round(cost, 2),
                        "dependencies": []
                    })
                
                timestep_info["initial_creation"] = {
                    "total_cost": round(initial_cost, 2),
                    "creation_details": creation_details
                }
            
            migration_analysis.append(timestep_info)
        
        # 拡張結果を作成
        enhanced = result.copy()
        enhanced["migration_analysis"] = migration_analysis
        
        # サマリー統計を追加
        total_created = sum(
            len(ma.get("migration", {}).get("created", {}).get("mvs", []))
            for ma in migration_analysis if "migration" in ma
        )
        total_deleted = sum(
            len(ma.get("migration", {}).get("deleted", {}).get("mvs", []))
            for ma in migration_analysis if "migration" in ma
        )
        total_maintained = sum(
            len(ma.get("migration", {}).get("maintained", {}).get("mvs", []))
            for ma in migration_analysis if "migration" in ma
        )
        
        enhanced["summary"] = {
            "total_timesteps": len(timesteps),
            "total_mvs_created": total_created + len(migration_analysis[0].get("initial_creation", {}).get("creation_details", [])),
            "total_mvs_deleted": total_deleted,
            "total_transitions_maintained": total_maintained,
            "avg_mvs_per_timestep": round(sum(ma["mv_count"] for ma in migration_analysis) / len(migration_analysis), 2),
            "avg_storage_utilization": round(sum(ma["utilization_percent"] for ma in migration_analysis) / len(migration_analysis), 2)
        }
        
        return enhanced
    
    def phase6b_optimize_static(self, timestep_position='last', static_algorithm='normal', b_max=None):
        """フェーズ6b: 静的最適化（時間依存なし・単一タイムステップのみ）
        
        Args:
            timestep_position: 使用するタイムステップ 
                'first': 最初, 'last': 最後, 'average': 全時刻の平均,
                'addmv': 頻度の和で重み付け + MV作成コスト考慮
            static_algorithm: 使用するアルゴリズム ('normal': 通常ILP, 'bigsubs': BigSubs, 'both': 両方)
        """
        if timestep_position == 'first':
            position_name = "最初"
        elif timestep_position == 'average':
            position_name = "全時刻平均"
        elif timestep_position == 'addmv':
            position_name = "頻度和+MV作成コスト"
        else:
            position_name = "最終"
        self.print_header(f"静的最適化（{position_name}タイムステップ）", 6.5)
        
        if not self.pickle_path.exists():
            self.print_error(f"{self.pickle_path} が見つかりません")
            return False
            
        if self.qp is None:
            self.print_info(f"パース結果を読み込み中: {self.pickle_path}")
            try:
                with open(self.pickle_path, 'rb') as f:
                    self.qp = pickle.load(f)
            except Exception as e:
                self.print_error(f"パース結果の読み込みに失敗: {e}")
                return False

        self.print_info("静的最適化（初期タイムステップのワークロードのみ）を実行")
        phase_start = time.time()
        
        try:
            from experiments.small_test_ver2.core.io_loaders import (
                load_timesteps_and_frequencies,
                load_full_build_costs_and_sizes,
            )
            from src.optimization.normal import NormalOptimizer
            
            # ストレージ予算
            B_max = float((b_max if b_max is not None else 100) * 1024 * 1024)
            
            # タイムステップと頻度を読み込み
            timesteps, frequencies = load_timesteps_and_frequencies(str(self.exp_dir), self.query_set, freq_suffix=self.exp_suffix)
            
            if not timesteps:
                self.print_error("タイムステップ情報がありません")
                return False
                
            # タイムステップの選択
            if timestep_position == 'first':
                selected_timestep = timesteps[0]
                selected_frequencies = frequencies[selected_timestep]
                self.print_info(f"使用タイムステップ: {selected_timestep} (最初)")
            elif timestep_position == 'average':
                # 全時刻での頻度の和を計算（normal/bigsubs用には和、utilityではこれを後で平均化）
                selected_timestep = "average"
                self.print_info(f"使用タイムステップ: 全時刻の頻度平均/和")
                
                # 各クエリについて全タイムステップでの頻度の和を計算
                query_count = len(self.qp.u_ij)
                selected_frequencies = [0.0] * query_count
                
                for timestep in timesteps:
                    timestep_freq = frequencies[timestep]
                    # 頻度の次元を調整
                    if len(timestep_freq) < query_count:
                        timestep_freq = timestep_freq + [1.0] * (query_count - len(timestep_freq))
                    else:
                        timestep_freq = timestep_freq[:query_count]
                    
                    # 累積加算
                    for i in range(query_count):
                        selected_frequencies[i] += timestep_freq[i]
                
                num_timesteps = len(timesteps)
                if static_algorithm == 'utility':
                    for i in range(query_count):
                        selected_frequencies[i] /= num_timesteps
                    self.print_info(f"  {num_timesteps}個のタイムステップの頻度を平均化（Utility用）")
                else:
                    self.print_info(f"  {num_timesteps}個のタイムステップの頻度を合計")
            elif timestep_position == 'addmv':
                # 頻度の和で重み付け（MV作成コストとスケールを合わせるため）
                selected_timestep = "addmv"
                self.print_info(f"使用タイムステップ: 頻度の和 + MV作成コスト考慮")
                
                # 各クエリについて全タイムステップでの頻度の和を計算（平均ではなく）
                query_count = len(self.qp.u_ij)
                selected_frequencies = [0.0] * query_count
                
                for timestep in timesteps:
                    timestep_freq = frequencies[timestep]
                    # 頻度の次元を調整
                    if len(timestep_freq) < query_count:
                        timestep_freq = timestep_freq + [1.0] * (query_count - len(timestep_freq))
                    else:
                        timestep_freq = timestep_freq[:query_count]
                    
                    # 累積加算（平均化しない）
                    for i in range(query_count):
                        selected_frequencies[i] += timestep_freq[i]
                
                self.print_info(f"  {len(timesteps)}個のタイムステップの頻度を合計")
            else:  # 'last'
                selected_timestep = timesteps[-1]
                selected_frequencies = frequencies[selected_timestep]
                self.print_info(f"使用タイムステップ: {selected_timestep} (最後)")
            
            # 頻度の次元調整（average/addmvの場合はすでに調整済み）
            query_count = len(self.qp.u_ij)
            if timestep_position not in ('average', 'addmv'):
                if len(selected_frequencies) < query_count:
                    selected_frequencies.extend([1.0] * (query_count - len(selected_frequencies)))
                else:
                    selected_frequencies = selected_frequencies[:query_count]
                
            # --recalc モードの場合、u_ij を更新し、コストを取得
            recalc_migration_cost, _ = self._update_u_ij_if_recalc()

            # 重み付き効用を計算 (u_ij * frequency)
            weighted_u_ij = []
            for i in range(len(self.qp.u_ij)):
                freq = selected_frequencies[i]
                weighted_row = [u * freq for u in self.qp.u_ij[i]]
                weighted_u_ij.append(weighted_row)
            
            # サイズデータの読み込み（MV作成コストはsubquery_costsを使用するためcreation_costsは不要）
            _, _, b_j_from_migration = load_full_build_costs_and_sizes(
                str(self.exp_dir), 
                self.qp.node_list, 
                self.query_set
            )
            
            # m_costは0とする（マイグレーションコストを考慮しないため）
            m_cost = [0.0] * len(self.qp.node_list)
            
            # addmvモードの場合、MV作成コストをindex_build_costsとして使用
            # 動的最適化と同様にsubquery_costsを使用（u_ijとスケール一致）
            if timestep_position == 'addmv':
                if self.recalc_mode and recalc_migration_cost is not None:
                     # Recalcモード: 再計算されたコストを使用
                    index_build_costs = [
                        recalc_migration_cost.get(j, float('inf'))
                        for j in range(len(self.qp.node_list))
                    ]
                    self.print_info(f"  MV作成コストを目的関数に含めます（Recalcコストベース）")
                else:
                    # 通常モード: subquery_costsを使用
                    index_build_costs = [
                        self.qp.qm.subquery_costs[node_id]
                        for node_id in self.qp.node_list
                    ]
                    self.print_info(f"  MV作成コストを目的関数に含めます（subquery_costsベース）")
                
                total_creation_cost = sum(val for val in index_build_costs if val != float('inf'))
                self.print_info(f"  総MV作成コスト上限: {total_creation_cost:.4f}")
            else:
                index_build_costs = None  # デフォルト（作成コストを考慮しない）
            
            # 結果保存用の変数
            result_dir = self.exp_dir / "time_dependent_output" / self.query_set
            result_dir.mkdir(parents=True, exist_ok=True)
            
            # NormalOptimizer実行 (normal or both)
            if static_algorithm in ('normal', 'both'):
                self.print_info(f"NormalOptimizer で最適化を実行中...")
                
                optimizer = NormalOptimizer(
                    qm=self.qp.qm,
                    s_num=len(self.qp.node_list),
                    m_cost=m_cost,
                    node_list=self.qp.node_list,
                    B_max=B_max,
                    b_j=b_j_from_migration,
                    u_ij=weighted_u_ij,
                    X=self.qp.X,
                    q_s_list=[],
                    settings=self.settings,
                    index_build_costs=index_build_costs  # addmvモードでMV作成コストを渡す
                )
                
                result = optimizer.optimize()
                
                # 結果の整形
                selected_mvs = [mv.node_id for mv in result.selected_views]
                selected_indices = [self.qp.node_list.index(mv.node_id) for mv in result.selected_views]
                total_size = result.total_storage
                
                # addmvモードの場合はアルゴリズム名を変更
                algorithm_name = "static_normal_with_creation_cost" if timestep_position == 'addmv' else "static_normal"
                
                static_result = {
                    "algorithm": algorithm_name,
                    "timestep": selected_timestep,
                    "selected_mvs": selected_mvs,
                    "mv_count": len(selected_mvs),
                    "total_size": total_size,
                    "storage_budget": B_max,
                    "utilization_percent": (total_size / B_max * 100) if B_max > 0 else 0,
                    "objective_value": result.total_utility,
                    "execution_time": result.execution_time,
                    "considers_creation_cost": timestep_position == 'addmv'
                }
                
                # addmvモードの場合、利得とMV作成コストを分けて計算
                if timestep_position == 'addmv' and index_build_costs is not None:
                    # 選択されたMVの利得の総和を計算（y_ij=1のペアのみ）
                    # y_ijはGurobiの最適化結果から取得
                    y_ij = result.metadata.get("y_ij", [[0] * len(self.qp.node_list) for _ in range(len(weighted_u_ij))])
                    total_utility_gain = 0.0
                    for i in range(len(weighted_u_ij)):
                        for j in selected_indices:
                            if y_ij[i][j] == 1:  # 実際に使用される場合のみ
                                total_utility_gain += weighted_u_ij[i][j]
                    
                    # 選択されたMVの初期作成コストの和を計算
                    total_creation_cost = sum(index_build_costs[j] for j in selected_indices)
                    
                    static_result["total_utility_gain"] = total_utility_gain
                    static_result["total_creation_cost"] = total_creation_cost
                    
                    self.print_success("NormalOptimizer 完了")
                    self.print_info(f"  選択されたMV数: {len(selected_mvs)}")
                    self.print_info(f"  使用ストレージ: {total_size / 1024 / 1024:.2f} MB")
                    self.print_info(f"  利得の総和: {total_utility_gain:.4f}")
                    self.print_info(f"  初期MV作成コストの和: {total_creation_cost:.4f}")
                    self.print_info(f"  目的関数値 (利得 - 作成コスト): {result.total_utility:.4f}")
                else:
                    self.print_success("NormalOptimizer 完了")
                    self.print_info(f"  選択されたMV数: {len(selected_mvs)}")
                    self.print_info(f"  使用ストレージ: {total_size / 1024 / 1024:.2f} MB")
                
                # 結果保存
                result_file = result_dir / f"static_mv_optimization_result{self.exp_suffix}.json"
                with open(result_file, 'w', encoding='utf-8') as f:
                    json.dump(static_result, f, indent=2, ensure_ascii=False)
                self.print_success(f"NormalOptimizer結果を {result_file} に保存")
            
            # utility実行
            if static_algorithm == 'utility':
                from experiments.small_test_ver2.core.utility_v2 import UtilityOptimizerV2
                
                self.print_info(f"UtilityOptimizerV2 で最適化を実行中...")
                
                utility_optimizer = UtilityOptimizerV2(
                    qm=self.qp.qm,
                    s_num=len(self.qp.node_list),
                    m_cost=m_cost,
                    node_list=self.qp.node_list,
                    B_max=B_max,
                    b_j=b_j_from_migration,
                    u_ij=weighted_u_ij,
                    X=self.qp.X,
                    q_s_list=self.qp.q_s_list,
                    settings=self.settings
                )
                
                utility_result = utility_optimizer.optimize()
                
                # 結果の整形
                # UtilityOptimizerV2 の場合は最適化結果が dict 形式で一部キーが異なるかもしれないが、
                # 返される OptimizationResult オブジェクトか辞書かに応じて対処（ここでは BaseILPOptimizer.create_result の返り値が辞書だと想定）
                if isinstance(utility_result, dict):
                    utility_selected_mvs = utility_result.get("selected_mvs_t1", utility_result.get("materialized_nodes", []))
                    utility_total_size = utility_result.get("storage_used", 0)
                    utility_objective = utility_result.get("objective_value", 0)
                    utility_execution_time = utility_result.get("execution_time", 0)
                else:
                    utility_selected_mvs = [mv.node_id for mv in utility_result.selected_views]
                    utility_total_size = utility_result.total_storage
                    utility_objective = utility_result.total_utility
                    utility_execution_time = utility_result.execution_time
                
                utility_static_result = {
                    "algorithm": "static_utility",
                    "timestep": selected_timestep,
                    "selected_mvs": utility_selected_mvs,
                    "mv_count": len(utility_selected_mvs),
                    "total_size": utility_total_size,
                    "storage_budget": B_max,
                    "utilization_percent": (utility_total_size / B_max * 100) if B_max > 0 else 0,
                    "objective_value": utility_objective,
                    "execution_time": utility_execution_time
                }
                
                self.print_success("UtilityOptimizerV2 完了")
                self.print_info(f"  選択されたMV数: {len(utility_selected_mvs)}")
                self.print_info(f"  使用ストレージ: {utility_total_size / 1024 / 1024:.2f} MB")
                
                # 結果保存（averageモードと同様に上書き可能にするか別名にするか、指定によりaverage形式に合わせる）
                utility_result_file = result_dir / f"static_mv_optimization_result{self.exp_suffix}.json"
                with open(utility_result_file, 'w', encoding='utf-8') as f:
                    json.dump(utility_static_result, f, indent=2, ensure_ascii=False)
                self.print_success(f"UtilityOptimizerV2結果を {utility_result_file} に保存")

            # BigSubsOptimizer実行 (bigsubs or both)
            if static_algorithm in ('bigsubs', 'both'):
                from src.optimization.bigsubs import BigSubsOptimizer
                
                self.print_info(f"BigSubsOptimizer で最適化を実行中...")
                
                # weighted_u_ij に基づいて U_j_max と U_max を計算
                # オリジナルのBigSubsに合わせて、max ではなく sum を使用
                weighted_U_j_max = [
                    sum((weighted_u_ij[i][j] for i in range(len(weighted_u_ij))))
                    for j in range(len(self.qp.node_list))
                ]
                weighted_U_max = sum(weighted_U_j_max)
                
                # y_ijはクエリパーサから取得（オリジナルの静的実験と同様）
                initial_y_ij = self.qp.y_ij if hasattr(self.qp, 'y_ij') else [[0] * len(self.qp.node_list) for _ in range(len(weighted_u_ij))]
                
                bigsubs_optimizer = BigSubsOptimizer(
                    qm=self.qp.qm,
                    s_num=len(self.qp.node_list),
                    m_cost=m_cost,
                    node_list=self.qp.node_list,
                    B_max=B_max,
                    b_j=b_j_from_migration,
                    u_ij=weighted_u_ij,
                    X=self.qp.X,
                    q_s_list=self.qp.q_s_list,
                    settings=self.settings,
                    U_j_max=weighted_U_j_max,
                    U_max=weighted_U_max,
                    y_ij=initial_y_ij
                )
                
                bigsubs_result = bigsubs_optimizer.optimize(iter_max=200)
                
                # 結果の整形
                bigsubs_selected_mvs = [mv.node_id for mv in bigsubs_result.selected_views]
                bigsubs_total_size = bigsubs_result.total_storage
                
                bigsubs_static_result = {
                    "algorithm": "static_bigsubs",
                    "timestep": selected_timestep,
                    "selected_mvs": bigsubs_selected_mvs,
                    "mv_count": len(bigsubs_selected_mvs),
                    "total_size": bigsubs_total_size,
                    "storage_budget": B_max,
                    "utilization_percent": (bigsubs_total_size / B_max * 100) if B_max > 0 else 0,
                    "objective_value": bigsubs_result.total_utility,
                    "execution_time": bigsubs_result.execution_time,
                    "iterations": bigsubs_result.metadata.get('iterations'),
                    "convergence_summary": bigsubs_result.metadata.get('convergence_summary', {})
                }
                
                self.print_success("BigSubsOptimizer 完了")
                self.print_info(f"  選択されたMV数: {len(bigsubs_selected_mvs)}")
                self.print_info(f"  使用ストレージ: {bigsubs_total_size / 1024 / 1024:.2f} MB")
                
                # 結果保存（BigSubs用のファイル名）
                bigsubs_result_file = result_dir / f"static_bigsubs_optimization_result{self.exp_suffix}.json"
                with open(bigsubs_result_file, 'w', encoding='utf-8') as f:
                    json.dump(bigsubs_static_result, f, indent=2, ensure_ascii=False)
                self.print_success(f"BigSubsOptimizer結果を {bigsubs_result_file} に保存")
            
            # SQL生成はPhase 7に移動
            self.phase_times['phase6b_static_optimization'] = time.time() - phase_start
            return True
            
        except Exception as e:
            self.print_error(f"静的最適化に失敗: {e}")
            import traceback
            traceback.print_exc()
            return False

    def phase6c_optimize_adaptive(self, window_size: Optional[int] = None, b_max=None):
        """フェーズ6c: 適応的MV最適化（スライディングウィンドウ方式）
        
        2タイムステップILPを用いた適応的最適化。
        - 初期MV: 全時刻の平均頻度で計算
        - 各ステップ: 現在のMVを固定し、次のMVを最適化
        
        Args:
            window_size: 移動平均の幅（Noneの場合はself.window_sizeを使用）
        
        出力形式は動的最適化と同じ構造。
        """
        if window_size is None:
            window_size = self.window_size
        
        self.print_header("ILP最適化（適応型）", 6)
        
        if not self.pickle_path.exists():
            self.print_error(f"{self.pickle_path} が見つかりません")
            self.print_info("先にフェーズ2を実行してください")
            return False
        
        if self.qp is None:
            self.print_info(f"パース結果を読み込み中: {self.pickle_path}")
            try:
                with open(self.pickle_path, 'rb') as f:
                    self.qp = pickle.load(f)
                self.print_success(f"{self.qp.s_num}個のノードを読み込み完了")
            except Exception as e:
                self.print_error(f"パース結果の読み込みに失敗: {e}")
                return False
        
        self.print_info("適応型最適化（スライディングウィンドウ方式）を実行")
        
        # フェーズ時間計測開始
        phase_start = time.time()
        
        try:
            from experiments.small_test_ver2.core.io_loaders import (
                load_timesteps_and_frequencies,
                load_full_build_costs_and_sizes,
            )
            from experiments.small_test_ver2.core.two_step_optimizer import TwoStepOptimizer
            from experiments.small_test_ver2.core.time_dependent_optimizer import TimeDependentOptimizer
            
            # ストレージ予算
            B_max = float((b_max if b_max is not None else 100) * 1024 * 1024)
            
            # タイムステップと頻度を読み込み
            self.print_info("タイムステップと頻度情報を読み込み中...")
            timesteps, frequencies = load_timesteps_and_frequencies(str(self.exp_dir), self.query_set, freq_suffix=self.exp_suffix)
            self.print_success(f"  タイムステップ数: {len(timesteps)}")
            
            # 頻度の次元を検証・調整
            query_count = len(self.qp.u_ij)
            for ts in timesteps:
                if len(frequencies[ts]) != query_count:
                    if len(frequencies[ts]) < query_count:
                        frequencies[ts].extend([1.0] * (query_count - len(frequencies[ts])))
                    else:
                        frequencies[ts] = frequencies[ts][:query_count]
            
            # マイグレーションコストとサイズを読み込み
            migration_cost, b_j_from_migration = self._update_u_ij_if_recalc()
            
            if migration_cost is None:
                migration_cost, _, b_j_from_migration = load_full_build_costs_and_sizes(
                    str(self.exp_dir), 
                    self.qp.node_list, 
                    self.query_set
                )
                self.print_success(f"  {len(migration_cost)}個のMVのマイグレーションコストを計算完了")
            
            b_j = b_j_from_migration
            
            # 最初のタイムステップの頻度を取得
            self.print_info("最初のタイムステップの頻度を使用...")
            initial_freq = frequencies[timesteps[0]]
            
            # === 初期MV計算（最初のタイムステップの頻度で静的最適化）===
            # 初期MVはマイグレーションコストを考慮せず、純粋にワークロードに最適なものを選択
            self.print_info("初期MVを計算中（最初のタイムステップの頻度、マイグレーションコストなし）...")
            initial_start = time.time()
            
            # マイグレーションコストを0にする（初期MVでは考慮しない）
            zero_migration_cost = {j: 0.0 for j in range(len(self.qp.node_list))}
            
            initial_optimizer = TimeDependentOptimizer(
                node_list=self.qp.node_list,
                u_ij=self.qp.u_ij,
                X=self.qp.X,
                b_j=b_j,
                B_max=B_max,
                timesteps=["initial"],
                migration_cost=zero_migration_cost,  # マイグレーションコストを0に設定
                query_frequency_by_timestep={"initial": initial_freq},
                gurobi_output=0,
            )
            initial_result = initial_optimizer.optimize()
            initial_z = initial_result["z_by_timestep"][0]
            current_mvs = set(j for j, v in enumerate(initial_z) if v == 1)
            
            initial_solve_time = time.time() - initial_start
            self.print_success(f"  初期MV数: {len(current_mvs)}, 計算時間: {initial_solve_time:.2f}s")
            
            # === 各タイムステップで適応的最適化 ===
            # 適応的最適化の原則（過去N時刻の単純移動平均を使用）:
            # - 時刻tのビューは時刻(t-N+1, ..., t-1, t)の平均頻度で最適化
            # - 例: window_size=4の場合、時刻5のビューは時刻2,3,4,5の平均頻度で最適化
            # - タイムステップが不足する場合は、最初のタイムステップを拡張して使用
            self.print_info(f"適応的最適化を開始（過去{window_size}時刻の単純移動平均使用）...")
            
            z_by_timestep = []
            step_solve_times = []
            migration_analysis = []
            prev_freq = initial_freq
            
            # pending_migration: 次のタイムステップで記録する移行情報
            pending_migration = None
            
            for t, ts_name in enumerate(timesteps):
                self.print_info(f"  Timestep {t}: {ts_name}...")
                step_start = time.time()
                
                # 現在の状態を記録
                z_t = [1 if j in current_mvs else 0 for j in range(len(self.qp.node_list))]
                z_by_timestep.append(z_t)
                
                # N時刻の単純移動平均を計算（過去N時刻: t-N+1, ..., t-1, t）
                # 時刻tのビューは時刻t-N+1, ..., t-1, tの平均頻度で最適化
                freq_window = []
                for offset in range(-window_size + 1, 1):  # -N+1, ..., -1, 0
                    target_idx = t + offset
                    if target_idx < 0:
                        # タイムステップが足りない場合、最初のタイムステップを拡張して使用
                        freq_window.append(frequencies[timesteps[0]])
                    else:
                        # 通常のタイムステップ
                        freq_window.append(frequencies[timesteps[target_idx]])
                
                # N時刻の平均を計算
                query_count = len(self.qp.u_ij)
                curr_freq = [0.0] * query_count
                for i in range(query_count):
                    total = sum(freq_window[j][i] for j in range(window_size))
                    curr_freq[i] = total / window_size
                
                # どの時刻の平均を使用したかをログ出力
                used_indices = [max(0, t + offset) for offset in range(-window_size + 1, 1)]
                self.print_info(f"    {window_size}時刻移動平均: timesteps[{used_indices}] の平均を使用")
                
                # 2タイムステップILP（現在のMVを固定、次のMVを最適化）
                step_optimizer = TwoStepOptimizer(
                    node_list=self.qp.node_list,
                    u_ij=self.qp.u_ij,
                    X=self.qp.X,
                    b_j=b_j,
                    B_max=B_max,
                    prev_freq=prev_freq,
                    curr_freq=curr_freq,
                    migration_cost=migration_cost,
                    fixed_mvs=current_mvs,
                    gurobi_output=0,
                )
                
                step_result = step_optimizer.optimize()
                next_mvs = step_result["selected_mvs_t1"]
                
                step_elapsed = time.time() - step_start
                step_solve_times.append(step_elapsed)
                
                # migration_analysis形式で記録
                timestep_info = {
                    "timestep": ts_name,
                    "selected_mvs": [self.qp.node_list[j] for j in sorted(current_mvs)],
                    "mv_count": len(current_mvs),
                    "total_size": sum(b_j[j] for j in current_mvs),
                    "utilization_percent": sum(b_j[j] for j in current_mvs) / B_max * 100 if B_max > 0 else 0,
                    "solve_time_sec": step_elapsed,
                }
                
                if t == 0:
                    # 初期タイムステップ: 初期MVの作成を記録
                    initial_cost = sum(migration_cost.get(j, 0.0) for j in current_mvs)
                    timestep_info["initial_creation"] = {
                        "total_cost": round(initial_cost, 2),
                        "creation_details": [
                            {
                                "mv": self.qp.node_list[j],
                                "size": round(b_j[j], 2),
                                "cost": round(migration_cost.get(j, 0.0), 2),
                                "dependencies": []
                            }
                            for j in sorted(current_mvs)
                        ]
                    }
                else:
                    # t>0: 前回の最適化で決定した移行を記録
                    if pending_migration is not None:
                        timestep_info["migration"] = pending_migration
                
                migration_analysis.append(timestep_info)
                
                # 次のタイムステップで記録する移行情報を計算
                created = next_mvs - current_mvs
                deleted = current_mvs - next_mvs
                maintained = current_mvs & next_mvs
                creation_cost = sum(migration_cost.get(j, 0.0) for j in created)
                
                pending_migration = {
                    "created": {
                        "count": len(created),
                        "mvs": [self.qp.node_list[j] for j in sorted(created)]
                    },
                    "deleted": {
                        "count": len(deleted),
                        "mvs": [self.qp.node_list[j] for j in sorted(deleted)]
                    },
                    "maintained": {
                        "count": len(maintained),
                        "mvs": [self.qp.node_list[j] for j in sorted(maintained)]
                    },
                    "creation_cost": round(creation_cost, 2),
                    "creation_details": [
                        {
                            "mv": self.qp.node_list[j],
                            "size": round(b_j[j], 2),
                            "cost": round(migration_cost.get(j, 0.0), 2),
                            "dependencies": []
                        }
                        for j in sorted(created)
                    ]
                }
                
                # 状態更新
                prev_freq = curr_freq
                current_mvs = next_mvs
            
            total_solve_time = time.time() - phase_start
            
            # 純粋な最適化時間の合計（初期MV + 各ステップ）
            total_optimization_time = initial_solve_time + sum(step_solve_times)
            
            # 結果を動的最適化形式で構築
            result = {
                "algorithm": "adaptive_sliding_window",
                "timesteps": timesteps,
                "node_list": self.qp.node_list,
                # "z_by_timestep": z_by_timestep,
                "phase_time_sec": total_solve_time,  # フェーズ全体の実行時間
                "total_optimization_time_sec": total_optimization_time,  # 純粋な最適化時間の合計
                "initial_solve_time_sec": initial_solve_time,
                "step_solve_times_sec": step_solve_times,
                "avg_step_time_sec": round(sum(step_solve_times) / len(step_solve_times), 2) if step_solve_times else 0,
                "migration_analysis": migration_analysis,
                "summary": {
                    "total_timesteps": len(timesteps),
                    "total_mvs_created": sum(
                        ma.get("migration", {}).get("created", {}).get("count", 0)
                        for ma in migration_analysis if "migration" in ma
                    ) + len(migration_analysis[0].get("initial_creation", {}).get("creation_details", [])),
                    "total_mvs_deleted": sum(
                        ma.get("migration", {}).get("deleted", {}).get("count", 0)
                        for ma in migration_analysis if "migration" in ma
                    ),
                    "avg_mvs_per_timestep": round(sum(ma["mv_count"] for ma in migration_analysis) / len(migration_analysis), 2),
                    "avg_storage_utilization": round(sum(ma["utilization_percent"] for ma in migration_analysis) / len(migration_analysis), 2)
                }
            }
            
            # 結果保存
            result_dir = self.exp_dir / "time_dependent_output" / self.query_set
            result_dir.mkdir(parents=True, exist_ok=True)
            result_file = result_dir / f"adaptive_mv_optimization_result_w{window_size}{self.exp_suffix}.json"
            
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            self.print_success(f"適応的最適化結果を {result_file} に保存")
            
            # サマリー表示
            self.print_info(f"\n=== 最適化サマリー ===")
            self.print_info(f"  初期MV計算時間: {initial_solve_time:.2f}s")
            self.print_info(f"  各ステップ計算時間合計: {sum(step_solve_times):.2f}s")
            self.print_info(f"  ステップ平均計算時間: {sum(step_solve_times)/len(step_solve_times):.2f}s")
            self.print_info(f"  純粋な最適化時間合計: {total_optimization_time:.2f}s")
            self.print_info(f"  フェーズ総実行時間: {total_solve_time:.2f}s")
            self.print_info(f"  平均MV数: {result['summary']['avg_mvs_per_timestep']}")
            self.print_info(f"  総作成MV数: {result['summary']['total_mvs_created']}")
            self.print_info(f"  総削除MV数: {result['summary']['total_mvs_deleted']}")
            
            self.phase_times['phase6c_adaptive_optimization'] = total_solve_time
            return True
            
        except Exception as e:
            self.print_error(f"適応的最適化に失敗: {e}")
            import traceback
            traceback.print_exc()
            return False

    def phase7_generate_mv_sql(self, mode='dynamic', static_algorithm='normal'):
        """フェーズ7: MV作成SQL生成
        
        Args:
            mode: 'static', 'dynamic', または 'adaptive' (デフォルト: 'dynamic')
            static_algorithm: 静的最適化アルゴリズム ('normal', 'bigsubs', 'both')
        """
        # Static mode: 静的最適化結果からSQL生成
        if mode == 'static':
            self.print_header("静的MV作成SQL生成", 7)
            phase_start = time.time()
            
            success = self._generate_static_mv_sql(static_algorithm=static_algorithm)
            
            self.phase_times['phase7_static_sql_generation'] = time.time() - phase_start
            if success:
                self.print_info(f"  SQL生成時間: {self.phase_times['phase7_static_sql_generation']:.2f} 秒")
            return success
        
        # Dynamic/Adaptive mode: タイムステップごとのマイグレーションSQL作成
        mode_name = "適応的" if mode == 'adaptive' else "動的"
        self.print_header(f"マイグレーションSQL作成（{mode_name}）", 7)
        
        if self.result is None:
            # Load optimization result (adaptive or dynamic)
            if mode == 'adaptive':
                result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"adaptive_mv_optimization_result_w{self.window_size}{self.exp_suffix}.json"
            else:
                result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"td_mv_optimization_result{self.exp_suffix}.json"
            
            if not result_file.exists():
                self.print_error(f"最適化結果が見つかりません: {result_file}")
                self.print_info("先にフェーズ6を実行してください")
                return False
            
            with open(result_file, 'r', encoding='utf-8') as f:
                result_data = json.load(f)
                self.result = result_data
        
        # Check if result is from time-dependent optimizer
        if 'migration_analysis' not in self.result:
            self.print_error("時間依存型/適応的最適化結果ではありません")
            return False
        
        return self._generate_time_dependent_migration_sql()
    
    def _generate_time_dependent_migration_sql(self):
        """時間依存型最適化の結果からタイムステップごとのマイグレーションSQLを生成"""
        
        # フェーズ時間計測開始
        phase_start = time.time()
        
        try:
            # マイグレーションプランを読み込み
            plans_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_plans.json"
            if not plans_file.exists():
                self.print_error("マイグレーションプランが見つかりません")
                self.print_info("先にフェーズ2.7を実行してください")
                return False
            
            with open(plans_file, 'r', encoding='utf-8') as f:
                migration_plans = json.load(f)
            
            self.print_info(f"マイグレーションプラン読み込み完了: {len(migration_plans)}個のMV")
            
            # 出力ディレクトリ（フェーズ3の最適化結果と同じ場所）
            output_dir = self.exp_dir / "time_dependent_output" / self.query_set
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 既存のマイグレーションSQLファイルを削除
            existing_sql_files = list(output_dir.glob("timestep_*.sql"))
            if existing_sql_files:
                self.print_info(f"既存のマイグレーションSQLファイルを削除中: {len(existing_sql_files)}個")
                for sql_file in existing_sql_files:
                    sql_file.unlink()
                self.print_success("既存ファイルを削除完了")
            
            # 各タイムステップについて処理
            migration_analysis = self.result['migration_analysis']
            timesteps = self.result['timesteps']
            
            self.print_info(f"タイムステップ数: {len(timesteps)}")
            
            total_sql_count = 0
            
            for t_idx, timestep_info in enumerate(migration_analysis):
                timestep_name = timestep_info['timestep']
                current_mvs = set(timestep_info.get('selected_mvs', []))
                
                # 前のタイムステップのMV
                prev_mvs = set()
                if t_idx > 0:
                    prev_mvs = set(migration_analysis[t_idx - 1].get('selected_mvs', []))
                
                # 新規作成が必要なMV
                mvs_to_create = current_mvs - prev_mvs
                # 削除が必要なMV
                mvs_to_drop = prev_mvs - current_mvs
                
                if not mvs_to_create and not mvs_to_drop:
                    self.print_info(f"  タイムステップ '{timestep_name}': 変更なし（スキップ）")
                    continue
                
                # タイムステップごとのSQLファイルを作成
                output_file = output_dir / f"timestep_{t_idx}_{timestep_name}.sql"
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(f"-- =====================================================\n")
                    f.write(f"-- タイムステップ {t_idx}: {timestep_name}\n")
                    f.write(f"-- =====================================================\n\n")
                    f.write(f"\\c {self.settings.database.database}\n\n")
                    
                    # 統計情報の詳細度を設定（ファイル全体に適用）
                    # if mvs_to_create:
                    #     f.write(f"-- 統計情報を拡大（statistics_target = 1000）\n")
                    #     f.write(f"SET default_statistics_target = 1000;\n\n")
                    
                    # 削除が必要なMV
                    if mvs_to_drop:
                        f.write(f"-- 削除するMV: {len(mvs_to_drop)}個\n")
                        for mv_id in sorted(mvs_to_drop):
                            f.write(f"DROP MATERIALIZED VIEW IF EXISTS {mv_id} CASCADE;\n")
                        f.write("\n")
                    
                    # 新規作成が必要なMV
                    if mvs_to_create:
                        f.write(f"-- 新規作成するMV: {len(mvs_to_create)}個\n\n")
                        
                        created_count = 0
                        for mv_id in sorted(mvs_to_create):
                            # マイグレーションプランから適切なSQLを取得
                            if mv_id not in migration_plans:
                                self.print_info(f"  警告: {mv_id} のマイグレーションプランが見つかりません")
                                continue
                            
                            plans = migration_plans[mv_id]
                            
                            # 依存MVなしで新規作成（"[]"キー）
                            # 時間依存型の場合、前のタイムステップのMVを使って作成することも可能だが、
                            # シンプルマイグレーションプランでは"[]"（依存なし）のみなのでそれを使用
                            if "[]" in plans:
                                sql = plans["[]"]
                                if sql and sql != "NON_MIGRATE":
                                    f.write(f"-- MV: {mv_id}\n")
                                    f.write(f"{sql}\n")
                                    f.write(f"ANALYZE {mv_id};\n\n")
                                    created_count += 1
                        
                        f.write(f"-- {created_count}個のMVを作成\n\n")
                        # 統計情報の設定を元に戻す
                        # f.write(f"-- 統計情報の設定を元に戻す\n")
                        # f.write(f"RESET default_statistics_target;\n")
                
                sql_count = len(mvs_to_create) + len(mvs_to_drop)
                total_sql_count += sql_count
                
                self.print_success(f"  タイムステップ '{timestep_name}': {output_file.name}")
                self.print_info(f"    作成: {len(mvs_to_create)}個, 削除: {len(mvs_to_drop)}個")
            
            # フェーズ時間を記録
            self.phase_times['phase7_mv_sql_generation'] = time.time() - phase_start
            
            self.print_success(f"タイムステップごとのマイグレーションSQLを生成 → {output_dir}")
            self.print_info(f"  総操作数: {total_sql_count}")
            self.print_info(f"  SQL生成時間: {self.phase_times['phase7_mv_sql_generation']:.2f} 秒")
            
            return True
            
        except Exception as e:
            self.print_error(f"SQL生成に失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
    


    
    
    def _generate_static_mv_sql(self, static_algorithm='normal'):
        """静的最適化結果からMV作成SQLを生成
        
        Args:
            static_algorithm: 使用するアルゴリズム ('normal' or 'bigsubs')
        """
        try:
            # 静的最適化結果を読み込み（アルゴリズムに応じてファイルを選択）
            if static_algorithm == 'bigsubs':
                result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"static_bigsubs_optimization_result{self.exp_suffix}.json"
                sql_file_name = "static_bigsubs_initial_mvs.sql"
            else:
                result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"static_mv_optimization_result{self.exp_suffix}.json"
                sql_file_name = "static_initial_mvs.sql"
            
            if not result_file.exists():
                self.print_error(f"静的最適化結果が見つかりません: {result_file}")
                self.print_info("先にフェーズ6.5を実行してください")
                return False
            
            with open(result_file, 'r', encoding='utf-8') as f:
                static_result = json.load(f)
            
            selected_mvs = static_result.get('selected_mvs', [])
            self.print_info(f"静的最適化結果を読み込み ({static_algorithm}): {len(selected_mvs)}個のMV")
            
            # マイグレーションプランを読み込み
            plans_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_plans.json"
            if not plans_file.exists():
                self.print_error(f"マイグレーションプランが見つかりません: {plans_file}")
                self.print_info("先にフェーズ4を実行してください")
                return False
            
            with open(plans_file, 'r', encoding='utf-8') as f:
                migration_plans = json.load(f)
            
            # SQLステートメントを生成
            sql_statements = []
            sql_statements.append(f"-- =====================================================")
            sql_statements.append(f"-- 静的最適化MV作成SQL ({static_algorithm})")
            sql_statements.append(f"-- 選択されたMV数: {len(selected_mvs)}")
            sql_statements.append(f"-- =====================================================")
            sql_statements.append(f"\\c {self.settings.database.database}")
            sql_statements.append("")
            
            # 統計情報の詳細度を設定（ファイル全体に適用）
            # sql_statements.append(f"-- 統計情報を拡大（statistics_target = 1000）")
            # sql_statements.append(f"SET default_statistics_target = 1000;")
            # sql_statements.append("")
            
            created_count = 0
            for node_id in selected_mvs:
                if node_id in migration_plans and "[]" in migration_plans[node_id]:
                    sql = migration_plans[node_id]["[]"]
                    if sql and sql != "NON_MIGRATE":
                        sql_statements.append(f"-- MV: {node_id}")
                        sql_statements.append(sql)
                        sql_statements.append(f"ANALYZE {node_id};")
                        sql_statements.append("")
                        created_count += 1
            
            # 統計情報の設定を元に戻す
            # sql_statements.append(f"-- 統計情報の設定を元に戻す")
            # sql_statements.append(f"RESET default_statistics_target;")
            
            # SQLファイルを保存
            output_dir = self.exp_dir / "time_dependent_output" / self.query_set
            output_dir.mkdir(parents=True, exist_ok=True)
            sql_file = output_dir / sql_file_name
            
            # 既存の静的MVファイルを削除
            if sql_file.exists():
                self.print_info(f"既存の静的MV SQLファイルを削除中: {sql_file_name}")
                sql_file.unlink()
            
            with open(sql_file, 'w', encoding='utf-8') as f:
                f.write("\n".join(sql_statements))
            
            self.print_success(f"静的MV作成SQLを生成: {sql_file}")
            self.print_info(f"  作成するMV数: {created_count}")
            return True
            
        except Exception as e:
            self.print_error(f"静的SQL生成に失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def phase8_rewrite_queries(self, mode='dynamic', static_algorithm='normal'):
        """フェーズ8: クエリ書き換え
        
        Args:
            mode: 'static', 'dynamic', または 'adaptive' (デフォルト: 'dynamic')
            static_algorithm: 静的最適化アルゴリズム ('normal', 'bigsubs', 'both')
        """
        # 最初にモードで分岐
        if mode == 'static':
            # Static mode
            self.print_header("クエリ書き換え（静的モード）", 8)
            
            # アルゴリズムに応じてファイルを選択
            if static_algorithm == 'bigsubs':
                static_result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"static_bigsubs_optimization_result{self.exp_suffix}.json"
            else:
                static_result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"static_mv_optimization_result{self.exp_suffix}.json"
            
            if not static_result_file.exists():
                self.print_error(f"静的最適化結果が見つかりません: {static_result_file}")
                self.print_info("先にフェーズ6を --optimization-mode static で実行してください")
                return False
            
            self.print_info(f"静的最適化結果を使用してクエリを書き換えます ({static_algorithm})。")
            
            phase_start = time.time()
            success = self._rewrite_static_queries(static_result_file, static_algorithm=static_algorithm)
            self.phase_times['phase8_rewrite_queries_static'] = time.time() - phase_start
            
            return success
        
        # Dynamic/Adaptive モードの処理
        mode_name = "適応的" if mode == 'adaptive' else "時間依存型"
        self.print_header(f"{mode_name}クエリ書き換え", 8)
        
        # フェーズ時間計測開始
        phase_start = time.time()
        
        from src.rewrite.query_rewriter import QueryRewriter
        from src.core.models import MaterializedView
        
        if self.qp is None:
            self.print_info("QueryParserを読み込み中...")
            if not self.pickle_path.exists():
                self.print_error("パース結果が見つかりません")
                return False
            
            with open(self.pickle_path, 'rb') as f:
                self.qp = pickle.load(f)
        
        # Load optimization result (adaptive or dynamic)
        if mode == 'adaptive':
            result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"adaptive_mv_optimization_result_w{self.window_size}{self.exp_suffix}.json"
        else:
            result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"td_mv_optimization_result{self.exp_suffix}.json"
        
        if not result_file.exists():
            self.print_error(f"最適化結果が見つかりません: {result_file}")
            self.print_info("先にフェーズ6を実行してください")
            return False
        
        with open(result_file, 'r', encoding='utf-8') as f:
            result_data = json.load(f)
        
        # Check if result is from time-dependent/adaptive optimizer
        if 'migration_analysis' not in result_data:
            self.print_error(f"{mode_name}最適化結果ではありません")
            return False
        
        # Get query files
        query_files = sorted(self.queries_dir.glob("*.sql"), key=lambda x: x.name)
        if not query_files:
            self.print_error("クエリファイルが見つかりません")
            return False
        
        self.print_info(f"クエリ数: {len(query_files)}")
        
        # Base output directory
        base_output_dir = self.exp_dir / "time_dependent_output" / self.query_set / "jobs"
        base_output_dir.mkdir(parents=True, exist_ok=True)
        
        migration_analysis = result_data['migration_analysis']
        self.print_info(f"タイムステップ数: {len(migration_analysis)}")
        
        # Load migration plans to get SQL for each MV
        plans_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_plans.json"
        if not plans_file.exists():
            self.print_error("マイグレーションプランが見つかりません")
            self.print_info("先にフェーズ2.7を実行してください")
            return False
        
        with open(plans_file, 'r', encoding='utf-8') as f:
            migration_plans = json.load(f)
        
        self.print_info(f"マイグレーションプラン読み込み完了: {len(migration_plans)}個のMV")
        
        total_rewritten = 0
        
        # Process each timestep
        for t_idx, timestep_info in enumerate(migration_analysis):
            timestep_name = timestep_info['timestep']
            selected_mvs = timestep_info.get('selected_mvs', [])
            
            self.print_info(f"\nタイムステップ {t_idx} ({timestep_name}): {len(selected_mvs)}個のMV")
            
            # Create MaterializedView objects for the selected MVs
            mv_objects = []
            for node_id in selected_mvs:
                # Find node index
                try:
                    node_idx = self.qp.node_list.index(node_id)
                except ValueError:
                    self.print_info(f"  警告: ノード {node_id} が見つかりません")
                    continue
                
                # Get node size
                node_size = self.qp.b_j[node_idx] if node_idx < len(self.qp.b_j) else 0
                
                # Get usage positions from qm (which queries use this node?)
                # For now, apply all MVs to all queries (safe but not optimal)
                # TODO: Use actual usage information from query manager
                usage_positions = self.qp.qm.subquery_positions.get(node_id, [])
                # Get create_sql from migration plans
                create_sql = ""
                if node_id in migration_plans:
                    plans = migration_plans[node_id]
                    # Use the plan with no dependencies ("[]" key)
                    if "[]" in plans:
                        sql = plans["[]"]
                        if sql and sql != "NON_MIGRATE":
                            create_sql = sql
                
                # Create MaterializedView object
                mv = MaterializedView(
                    view_id=f"mv_{node_id}",
                    node_id=node_id,
                    create_sql=create_sql,  # SQL from migration plans
                    size=node_size,
                    maintenance_cost=0.0,  # Not needed for rewriting
                    usage_positions=usage_positions  # Apply to all queries
                )
                mv_objects.append(mv)
            
            # Create output directory for this timestep
            timestep_output_dir = base_output_dir / f"timestep_{t_idx}_{timestep_name}"
            if timestep_output_dir.exists():
                existing_sql_files = list(timestep_output_dir.glob("*.sql"))
                if existing_sql_files:
                    self.print_info(f"  既存SQLをクリーンアップ: {len(existing_sql_files)}個")
                    for sql_file in existing_sql_files:
                        sql_file.unlink()
            timestep_output_dir.mkdir(parents=True, exist_ok=True)
            
            # Rewrite queries using QueryRewriter with settings
            # settingsをコピーしてクエリディレクトリを指定
            from copy import deepcopy
            rewrite_settings = deepcopy(self.settings)
            rewrite_settings.benchmark.sql_dir = str(self.queries_dir.parent)  # 01_queriesディレクトリを指定
            
            # 包含行列を渡して冗長MV除去を有効化
            rewriter = QueryRewriter(
                rewrite_settings,
                containment_matrix=self.qp.X,
                node_list=self.qp.node_list,
                query_set=self.query_set
            )
            rewritten_queries = rewriter.rewrite_queries(mv_objects)
            
            # Save rewritten queries
            rewritten_count = 0
            for query_id, rewritten_sql in rewritten_queries.items():
                output_file = timestep_output_dir / f"{query_id}.sql"
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(rewritten_sql)
                rewritten_count += 1
            
            total_rewritten += rewritten_count
            self.print_success(f"  {rewritten_count}個のクエリを書き換え → {timestep_output_dir}")
        
        # フェーズ時間を記録
        self.phase_times['phase8_query_rewriting'] = time.time() - phase_start
        
        self.print_success(f"\n合計 {total_rewritten}個のクエリを書き換え完了")
        self.print_info(f"  出力先: {base_output_dir}")
        self.print_info(f"  クエリ書き換え時間: {self.phase_times['phase8_query_rewriting']:.2f} 秒")
        
        return True
    
    def _rewrite_static_queries(self, result_file, static_algorithm='normal'):
        """静的最適化結果に基づいてクエリを書き換え
        
        Args:
            result_file: 最適化結果ファイルパス
            static_algorithm: 使用するアルゴリズム ('normal' or 'bigsubs')
        """
        try:
            from src.rewrite.query_rewriter import QueryRewriter
            from src.core.models import MaterializedView
            
            # Load QueryParser if not already loaded
            if self.qp is None:
                self.print_info("QueryParserを読み込み中...")
                if not self.pickle_path.exists():
                    self.print_error("パース結果が見つかりません")
                    return False
                
                with open(self.pickle_path, 'rb') as f:
                    self.qp = pickle.load(f)
            
            with open(result_file, 'r', encoding='utf-8') as f:
                result_data = json.load(f)
            
            selected_mvs = result_data.get('selected_mvs', [])
            self.print_info(f"静的モード ({static_algorithm}): {len(selected_mvs)}個のMVを使用してクエリを書き換え")
            
            # クエリファイル取得
            query_files = sorted(self.queries_dir.glob("*.sql"), key=lambda x: x.name)
            
            # マイグレーションプラン読み込み
            plans_file = self.exp_dir / "04_migration" / self.query_set / "simple_migration_plans.json"
            if not plans_file.exists():
                return
                
            with open(plans_file, 'r', encoding='utf-8') as f:
                migration_plans = json.load(f)
            
            # MVオブジェクト作成
            mv_objects = []
            for node_id in selected_mvs:
                # ノードインデックス検索
                try:
                    node_idx = self.qp.node_list.index(node_id)
                    node_size = self.qp.b_j[node_idx] if node_idx < len(self.qp.b_j) else 0
                except ValueError:
                    continue
                
                create_sql = ""
                if node_id in migration_plans and "[]" in migration_plans[node_id]:
                    sql = migration_plans[node_id]["[]"]
                    if sql and sql != "NON_MIGRATE":
                        create_sql = sql
                
                mv = MaterializedView(
                    view_id=f"mv_{node_id}",
                    node_id=node_id,
                    create_sql=create_sql,
                    size=node_size,
                    maintenance_cost=0.0,
                    usage_positions=self.qp.qm.subquery_positions.get(node_id, [])
                )
                mv_objects.append(mv)
            
            # 書き換え実行
            # settingsをコピーしてクエリディレクトリを指定
            from copy import deepcopy
            rewrite_settings = deepcopy(self.settings)
            rewrite_settings.benchmark.sql_dir = str(self.queries_dir.parent)  # 01_queriesディレクトリを指定
            
            # 包含行列を渡して冗長MV除去を有効化
            rewriter = QueryRewriter(
                rewrite_settings,
                containment_matrix=self.qp.X,
                node_list=self.qp.node_list,
                query_set=self.query_set
            )
            rewritten_queries = rewriter.rewrite_queries(mv_objects)
            
            # 保存先（アルゴリズムに応じて変更）
            if static_algorithm == 'bigsubs':
                output_dir = self.exp_dir / "time_dependent_output" / self.query_set / "jobs" / "rewritten_static_bigsubs"
            else:
                output_dir = self.exp_dir / "time_dependent_output" / self.query_set / "jobs" / "rewritten_static"
            if output_dir.exists():
                existing_sql_files = list(output_dir.glob("*.sql"))
                if existing_sql_files:
                    self.print_info(f"  静的モード既存SQLをクリーンアップ: {len(existing_sql_files)}個")
                    for sql_file in existing_sql_files:
                        sql_file.unlink()
            output_dir.mkdir(parents=True, exist_ok=True)
            
            for query_id, rewritten_sql in rewritten_queries.items():
                output_file = output_dir / f"{query_id}.sql"
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(rewritten_sql)
            
            self.print_success(f"  静的モード用クエリを書き換え完了 ({static_algorithm}): {output_dir}")
            return True
            
        except Exception as e:
            self.print_error(f"静的モード用クエリ書き換えに失敗: {e}")
            return False

    def phase9_execute_benchmark(self, mode='dynamic', static_algorithm='normal', ease_mode=False, noise_ratio=0.0, noise_query_dir=None):
        """フェーズ9: 時間依存型ベンチマーク実行
        
        Args:
            mode: ベンチマークモード
                - 'dynamic': 動的MV（マイグレーションあり）
                - 'adaptive': 適応的MV（スライディングウィンドウ）
                - 'static': 静的MV（最初のタイムステップのみ）
                - 'baseline': ベースライン（MVなし）
            static_algorithm: 静的最適化アルゴリズム ('normal', 'bigsubs', 'both')
            ease_mode: 簡易モード（各クエリを1回実行し、時間に頻度を掛ける）
            noise_ratio: ノイズ注入率（0.0〜1.0）。ease_mode=Trueの場合は無視される
            noise_query_dir: ノイズ用クエリが格納されているディレクトリ（Noneの場合はデフォルトのjobフォルダ）
        """
        mode_names = {
            'dynamic': '動的MV（マイグレーションあり）',
            'adaptive': '適応的MV（スライディングウィンドウ）',
            'static': '静的MV（最初のタイムステップのみ）',
            'baseline': 'ベースライン（MVなし）'
        }
        
        self.print_header(f"時間依存型ベンチマーク実行 - {mode_names.get(mode, mode)}", 9)
        phase_start = time.time()
        
        # 既存のMVを全て削除（統一された初期状態を保証）
        # MV削除数が実行ごとに異なるとWAL生成量が変わり、不平等になるため最初に実行
        self.print_info("既存のMVをクリーンアップ中...")
        if not self._drop_all_mvs():
            self.print_error("MVの削除に失敗しました")
            # 失敗しても続行（警告のみ）
        
        # ベーステーブルの統計情報を更新（フェーズ1と同様に統計ターゲットを拡大）
        # 実行ごとにANALYZEを行うことで、最新の統計情報でベンチマークを実行
        self.print_info("ベーステーブルの統計情報を更新中...")
        if not self._analyze_base_tables():
            self.print_error("ベーステーブルのANALYZEに失敗しました")
            # 失敗しても続行（警告のみ）
        
        # PostgreSQLキャッシュをクリア（公平なベンチマークのため）
        # self.print_info("PostgreSQLキャッシュをクリア中...")
        # self._clear_caches()
        
        # Autovacuumを無効化（ベンチマーク中のバックグラウンド処理を抑制）
        # NOTE: 一旦コメントアウト - 実行時間への影響を検証するため
        self.print_info("Autovacuumを無効化中...")
        self._disable_autovacuum()
        
        # 強制チェックポイントを実行（WALバッファをクリアして同じ初期状態から開始）
        # MV削除により生成されたWALもここで処理される
        # これによりベンチマーク中の不規則なチェックポイント発生を遅らせ、
        # 実行時間のばらつきを軽減する
        self._force_checkpoint()       
        
        from experiments.small_test_ver2.benchmark import TimeDependentQueryExecutor
        from experiments.small_test_ver2.core.io_loaders import load_timesteps_and_frequencies
        
        # モードに応じて最適化結果の読み込み要否を判定
        optimization_result = None
        migration_sql_dir = None
        rewritten_queries_base_dir = None # Initialize here
        
        if mode == 'dynamic':
            # 最適化結果を読み込み
            result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"td_mv_optimization_result{self.exp_suffix}.json"
            
            if not result_file.exists():
                self.print_error("時間依存型最適化結果が見つかりません")
                self.print_info("先にフェーズ6を実行してください")
                return False
            
            with open(result_file, 'r', encoding='utf-8') as f:
                optimization_result = json.load(f)
                
            migration_sql_dir = self.exp_dir / "time_dependent_output" / self.query_set # This should point to the directory containing timestep_X_Y.sql
            rewritten_queries_base_dir = self.exp_dir / "time_dependent_output" / self.query_set / "jobs"
        
        elif mode == 'adaptive':
            # 適応的最適化結果を読み込み
            result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"adaptive_mv_optimization_result_w{self.window_size}{self.exp_suffix}.json"
            
            if not result_file.exists():
                self.print_error("適応的最適化結果が見つかりません")
                self.print_info("先にフェーズ6を --optimization-mode adaptive で実行してください")
                return False
            
            with open(result_file, 'r', encoding='utf-8') as f:
                optimization_result = json.load(f)
                
            migration_sql_dir = self.exp_dir / "time_dependent_output" / self.query_set
            rewritten_queries_base_dir = self.exp_dir / "time_dependent_output" / self.query_set / "jobs"
            
        elif mode == 'static':
            # 静的最適化結果を読み込み（アルゴリズムに応じてファイルを選択）
            if static_algorithm == 'bigsubs':
                result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"static_bigsubs_optimization_result{self.exp_suffix}.json"
                rewritten_queries_base_dir = self.exp_dir / "time_dependent_output" / self.query_set / "jobs" / "rewritten_static_bigsubs"
            else:
                result_file = self.exp_dir / "time_dependent_output" / self.query_set / f"static_mv_optimization_result{self.exp_suffix}.json"
                rewritten_queries_base_dir = self.exp_dir / "time_dependent_output" / self.query_set / "jobs" / "rewritten_static"
            
            if not result_file.exists():
                self.print_error(f"静的最適化結果が見つかりません: {result_file}")
                self.print_info("先にフェーズ6bを実行してください")
                return False
                
            with open(result_file, 'r', encoding='utf-8') as f:
                optimization_result = json.load(f)
            
            self.print_info(f"静的最適化結果を使用 ({static_algorithm}): {result_file.name}")
                
            # 静的モード用の設定
            # migration_sql_dir は static_initial_mvs.sql があるディレクトリ
            migration_sql_dir = self.exp_dir / "time_dependent_output" / self.query_set
            
            if not rewritten_queries_base_dir.exists():
                self.print_error(f"静的モード用クエリディレクトリが見つかりません: {rewritten_queries_base_dir}")
                return False

        elif mode == 'baseline':
            # ベースラインモードでは最適化結果は不要だが、
            # タイムステップと頻度情報を取得するためにダミーで読み込むか、
            # あるいはoptimization_resultをNoneのままにする。
            # ここではNoneのままにして、executorに直接オリジナルクエリを渡す。
            optimization_result = None
            migration_sql_dir = None # ベースラインではMV操作SQLは不要
            rewritten_queries_base_dir = self.queries_dir # オリジナルクエリのディレクトリ
            
        # migration_sql_dirの存在確認 (dynamic/adaptiveモード)
        if mode in ('dynamic', 'adaptive') and (not migration_sql_dir or not migration_sql_dir.exists()):
            self.print_error(f"マイグレーションSQLディレクトリが見つかりません: {migration_sql_dir}")
            self.print_info("先にフェーズ7を実行してください")
            return False
        
        # 書き換えられたクエリファイルを使用
        # rewritten_base_dir = self.exp_dir / "time_dependent_output" / self.query_set / "jobs" # This line is now handled by rewritten_queries_base_dir
        
        # 元のクエリファイルリストを取得（クエリ名のリストとして使用）
        import re
        def natural_sort_key(s):
            return [int(text) if text.isdigit() else text.lower() for text in re.split("([0-9]+)", str(s))]
            
        original_query_files = sorted(self.queries_dir.glob("*.sql"), key=lambda x: natural_sort_key(x.name))
        
        if not original_query_files:
            self.print_error("クエリファイルが見つかりません")
            return False
        
        self.print_info(f"クエリ数: {len(original_query_files)}")
        
        # 頻度情報を読み込み
        self.print_info("頻度情報を読み込み中...")
        try:
            timesteps, frequencies_by_timestep = load_timesteps_and_frequencies(
                str(self.exp_dir), 
                self.query_set,
                freq_suffix=self.exp_suffix
            )
            self.print_success(f"  タイムステップ数: {len(timesteps)}")
        except Exception as e:
            self.print_error(f"頻度情報の読み込みに失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        # TimeDependentQueryExecutorを初期化
        self.print_info("ベンチマーク実行の準備中...")
        executor = TimeDependentQueryExecutor(self.settings)
        
        # ノイズ注入の設定（ease_modeでは無効）
        if noise_ratio > 0.0 and not ease_mode:
            executor.noise_ratio = noise_ratio
            
            # ノイズ用クエリフォルダの決定（デフォルト: 01_queries/job）
            if noise_query_dir is not None:
                resolved_noise_dir = Path(noise_query_dir)
            else:
                resolved_noise_dir = self.queries_dir  # 01_queries/{query_set} の元クエリ
            
            self.print_info(f"ノイズ注入設定: ratio={noise_ratio:.2f}, dir={resolved_noise_dir}")
            loaded_count = executor.load_noise_pool(resolved_noise_dir)
            if loaded_count == 0:
                self.print_error(f"ノイズ用クエリが見つかりません: {resolved_noise_dir}")
                self.print_info("ノイズなしで続行します")
                executor.noise_ratio = 0.0
            else:
                self.print_success(f"  ノイズプール: {loaded_count}個のクエリを事前ロード完了")
        else:
            if noise_ratio > 0.0 and ease_mode:
                self.print_info("ease_modeではノイズ注入は無効です")
        
        try:
            # モードに応じてベンチマークを実行
            self.print_info(f"ベンチマーク実行を開始します（モード: {mode}）...\n")
            
            if mode == 'baseline':
                # ベースライン: MVなし（元のクエリを使用）
                benchmark_results = executor.execute_baseline_benchmark(
                    query_files=original_query_files,
                    frequencies_by_timestep=frequencies_by_timestep,
                    timesteps=timesteps,
                    timeout_minutes=60,
                    verbose=True,
                    ease_mode=ease_mode
                )
            elif mode == 'static':
                # 静的MV: 最初のタイムステップのみ
                benchmark_results = executor.execute_static_mv_benchmark(
                    optimization_result=optimization_result,
                    migration_sql_dir=migration_sql_dir,
                    # query_files=query_files, # Not used directly, rewritten_queries_base_dir is used
                    rewritten_queries_base_dir = rewritten_queries_base_dir,
                    frequencies_by_timestep=frequencies_by_timestep,
                    timesteps=timesteps, # Pass timesteps for static mode as well
                    timeout_minutes=60,
                    verbose=True,
                    static_algorithm=static_algorithm,
                    ease_mode=ease_mode
                )
            else:  # dynamic or adaptive
                # 動的/適応的MV: マイグレーションあり
                benchmark_results = executor.execute_time_dependent_benchmark(
                    optimization_result=optimization_result,
                    migration_sql_dir=migration_sql_dir,
                    #query_files=query_files, # Not used directly, rewritten_queries_base_dir is used
                    rewritten_queries_base_dir = rewritten_queries_base_dir,
                    frequencies_by_timestep=frequencies_by_timestep,
                    timeout_minutes=60,
                    verbose=True,
                    ease_mode=ease_mode
                )
            
            # 結果を保存
            output_dir = self.exp_dir / "time_dependent_output" / self.query_set
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 静的モード + bigsubs の場合は別ファイル名
            # noise_ratio > 0 の場合はファイル名に _noise{XX} を付与して衝突を回避
            noise_suffix = f"_noise{int(noise_ratio * 100)}" if noise_ratio > 0.0 else ""
            window_suffix = f"_w{self.window_size}" if mode == 'adaptive' else ""
            if mode == 'static' and static_algorithm == 'bigsubs':
                output_file = output_dir / f"benchmark_results_static_bigsubs{self.exp_suffix}{noise_suffix}.json"
            else:
                output_file = output_dir / f"benchmark_results_{mode}{window_suffix}{self.exp_suffix}{noise_suffix}.json"
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(benchmark_results, f, indent=2, ensure_ascii=False)
            
            self.print_success(f"\nベンチマーク結果を保存: {output_file}")
            
            # サマリー表示
            summary = benchmark_results.get('summary', {})
            self.print_info(f"  総タイムステップ数: {summary.get('total_timesteps', 0)}")
            
            if mode == 'dynamic':
                self.print_info(f"  総マイグレーション時間: {summary.get('total_migration_time', 0):.2f}秒")
            elif mode == 'static':
                self.print_info(f"  初期MV作成時間: {summary.get('initial_mv_creation_time', 0):.2f}秒")
            
            self.print_info(f"  総クエリ実行時間: {summary.get('total_query_time', 0):.2f}秒")
            self.print_info(f"  総ベンチマーク時間: {summary.get('total_benchmark_time', 0):.2f}秒")
            
            # フェーズ時間を記録
            self.phase_times['phase9_benchmark'] = time.time() - phase_start
            
            return True
            
        except Exception as e:
            self.print_error(f"ベンチマーク実行に失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # Autovacuumを有効化（元に戻す）
            # NOTE: 無効化をコメントアウトしているため、こちらも実行不要
            self.print_info("Autovacuumを有効化中...")
            self._enable_autovacuum()
            
            executor.close()

    
    def run_post_optimization_phases(self, optimization_mode='dynamic', use_pruning=False, pruning_parallel=False, pruning_workers=None, static_timestep='last', use_static_protection=False, static_algorithm='normal', ease_mode=False, noise_ratio=0.0, noise_query_dir=None, b_max=None, inherit_parent_constraints=True):
        """最適化以降のフェーズを実行 (Phase 6-9)

        Args:
            optimization_mode: 'static' または 'dynamic' (デフォルト: 'dynamic')
            use_pruning: CF Pruningを使用するか (デフォルト: False)
            pruning_parallel: プルーニングを並列実行するか (デフォルト: False)
            pruning_workers: 並列実行時のワーカー数 (デフォルト: CPUコア数)
            static_timestep: 静的最適化時のタイムステップ ('first' or 'last')
            use_static_protection: 静的最適化のMVを聖域として保護する (デフォルト: False)
            static_algorithm: 静的最適化アルゴリズム ('normal', 'bigsubs', 'both')
            inherit_parent_constraints: WSTにおける親ノードからの境界制約伝播 (デフォルト: True)
        """
        self.print_header(f"最適化以降のフェーズ実行 ({optimization_mode}モード)")

        # 全体の開始時刻を記録
        total_start_time = time.time()

        # 最適化フェーズ（モードに応じて選択）
        optimization_phase = (6, "MV最適化", lambda: self.phase6_optimize(
            mode=optimization_mode,
            use_pruning=use_pruning,
            pruning_parallel=pruning_parallel,
            pruning_workers=pruning_workers,
            static_timestep=static_timestep,
            use_static_protection=use_static_protection,
            static_algorithm=static_algorithm,
            b_max=b_max,
            inherit_parent_constraints=inherit_parent_constraints,
        ))
        
        # SQL生成・クエリ書き換え・ベンチマークフェーズ
        post_optimization_phases = [
            (7, "MV生成SQL作成", lambda: self.phase7_generate_mv_sql(mode=optimization_mode, static_algorithm=static_algorithm)),
            (8, "クエリ書き換え", lambda: self.phase8_rewrite_queries(mode=optimization_mode, static_algorithm=static_algorithm)),
            (9, "ベンチマーク実行", lambda: self.phase9_execute_benchmark(mode=optimization_mode, static_algorithm=static_algorithm, ease_mode=ease_mode, noise_ratio=noise_ratio, noise_query_dir=noise_query_dir)),
        ]
        
        # 全フェーズをまとめる
        phases = [optimization_phase] + post_optimization_phases
        
        for phase_num, phase_name, phase_func in phases:
            try:
                if not phase_func():
                    self.print_error(f"フェーズ{phase_num}で失敗しました")
                    return False
            except Exception as e:
                self.print_error(f"フェーズ{phase_num}でエラー発生: {e}")
                import traceback
                traceback.print_exc()
                return False
        
        # 全体の実行時間を記録
        total_elapsed = time.time() - total_start_time
        
        self.print_header("最適化以降のフェーズ完了")
        self.print_success(f"総実行時間: {total_elapsed:.2f} 秒")
        
        if self.phase_times:
            self.print_info("フェーズ別実行時間:")
            for phase, elapsed in self.phase_times.items():
                if phase in ['phase6_optimization', 'phase7_mv_sql_generation', 'phase8_query_rewriting', 'phase9_benchmark']:
                    self.print_info(f"  {phase}: {elapsed:.2f} 秒")
        
        return True
    
    def run_all_phases(self, optimization_mode='dynamic', use_pruning=False, pruning_parallel=False, pruning_workers=None, static_timestep='last', use_static_protection=False, ease_mode=False, noise_ratio=0.0, noise_query_dir=None, b_max=None, inherit_parent_constraints=True):
        """全フェーズを順次実行

        Args:
            optimization_mode: 'static' または 'dynamic' (デフォルト: 'dynamic')
            use_pruning: CF Pruningを使用するか (デフォルト: False)
            pruning_parallel: プルーニングを並列実行するか (デフォルト: False)
            pruning_workers: 並列実行時のワーカー数 (デフォルト: CPUコア数)
            static_timestep: 静的最適化時のタイムステップ ('first' or 'last')
            use_static_protection: 静的最適化のMVを聖域として保護する (デフォルト: False)
            inherit_parent_constraints: WSTにおける親ノードからの境界制約伝播 (デフォルト: True)
        """
        self.print_header("小規模実験（通常モード） - 全フェーズ実行")

        success = True

        # 全体の開始時刻を記録
        total_start_time = time.time()

        # 基本フェーズ（モードに依存しない）
        basic_phases = [
            (1, "EXPLAIN JSON生成", self.phase1_generate_explain_json),
            (2, "クエリパース", self.phase2_parse_queries),
            (3, "JSONノードID付加", self.phase3_annotate_json),
            (4, "マイグレーションプラン列挙", self.phase4_enumerate_migration_plans),
            (5, "マイグレーションコスト計算", self.phase5_calculate_migration_costs),
        ]

        # 最適化フェーズ（モードに応じて選択）
        optimization_phase = (6, "MV最適化", lambda: self.phase6_optimize(
            mode=optimization_mode,
            use_pruning=use_pruning,
            pruning_parallel=pruning_parallel,
            pruning_workers=pruning_workers,
            static_timestep=static_timestep,
            use_static_protection=use_static_protection,
            b_max=b_max,
            inherit_parent_constraints=inherit_parent_constraints,
        ))
        
        # SQL生成・クエリ書き換え・ベンチマークフェーズ
        post_optimization_phases = [
            (7, "MV生成SQL作成", lambda: self.phase7_generate_mv_sql(mode=optimization_mode)),
            (8, "クエリ書き換え", lambda: self.phase8_rewrite_queries(mode=optimization_mode)),
            (9, "ベンチマーク実行", lambda: self.phase9_execute_benchmark(mode=optimization_mode, ease_mode=ease_mode, noise_ratio=noise_ratio, noise_query_dir=noise_query_dir)),
        ]
        
        # 全フェーズをまとめる
        phases = basic_phases + [optimization_phase] + post_optimization_phases
        
        for phase_num, phase_name, phase_func in phases:
            try:
                if not phase_func():
                    self.print_error(f"フェーズ{phase_num}で失敗しました")
                    return False
            except Exception as e:
                self.print_error(f"フェーズ{phase_num}でエラー発生: {e}")
                import traceback
                traceback.print_exc()
                return False
        
        # 全体の実行時間を記録
        total_elapsed = time.time() - total_start_time
        
        # フェーズ時間のサマリーを保存
        result_dir = self.exp_dir / "time_dependent_output" / self.query_set
        result_dir.mkdir(parents=True, exist_ok=True)
        
        summary = {
            "query_set": self.query_set,
            "total_execution_time": round(total_elapsed, 2),
            "phase_times": {
                key: round(value, 2) for key, value in self.phase_times.items()
            },
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        
        summary_file = result_dir / "execution_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        self.print_header("全フェーズ完了")
        self.print_success(f"総実行時間: {total_elapsed:.2f} 秒")
        if self.phase_times:
            self.print_info("フェーズ別実行時間:")
            for phase_name, phase_time in self.phase_times.items():
                self.print_info(f"  {phase_name}: {phase_time:.2f} 秒")
        self.print_success(f"サマリーを {summary_file} に保存")
        
        return True


def main():
    parser = argparse.ArgumentParser(description="小規模実験 - 通常モード")
    parser.add_argument(
        '--phase',
        type=str,
        default='all',
        choices=['all', 'post-opt', '0', '1', '2', '3', '4', '5', '6', '6.5', '7', '8', '9'],
        help='実行するフェーズ (all: 全実行, post-opt: 最適化以降(6-9), 0: DB setup, 1: EXPLAIN, 2: Parse, 3: Annotate, 4: Migration plans, 5: Migration costs, 6: Optimize, 6.5: Static Optimize, 7: MV SQL, 8: Rewrite, 9: Benchmark)'
    )
    parser.add_argument(
        '--config',
        type=str,
        default='experiments/small_test_ver2',
        help='実験ディレクトリのパス（設定ファイルは不要）'
    )
    parser.add_argument(
        '--query-set',
        type=str,
        default='job',
        help='実行するクエリセット(job, job_like, explicit_join, etc.)'
    )
    parser.add_argument(
        '--benchmark-mode',
        type=str,
        default='dynamic',
        choices=['dynamic', 'adaptive', 'static', 'baseline'],
        help='ベンチマークモード (dynamic: 動的MV, adaptive: 適応的MV, static: 静的MV, baseline: MVなし)'
    )
    parser.add_argument(
        '--optimization-mode',
        type=str,
        default='dynamic',
        choices=['static', 'dynamic', 'adaptive'],
        help='最適化モード (static: 初期タイムステップのみ, dynamic: 時間依存型最適化, adaptive: 適応的最適化)'
    )
    parser.add_argument(
        '--use-neurocard',
        action='store_true',
        help='NeuroCardを使用してコスト推定を行う'
    )
    parser.add_argument(
        '--use-deepdb',
        action='store_true',
        help='DeepDBを使用してコスト推定を行う（学習済みアンサンブル必須）'
    )
    parser.add_argument(
        '--use-sampling',
        action='store_true',
        help='サンプリングを使用してコスト推定を行う'
    )
    parser.add_argument(
        '--sampling-parallel',
        action='store_true',
        help='サンプリング計算を並列実行する'
    )
    parser.add_argument(
        '--sampling-workers',
        type=int,
        default=None,
        help='サンプリング並列実行時のワーカー数（デフォルト：CPUコア数）'
    )
    parser.add_argument(
        '--compare',
        action='store_true',
        help='コスト推定結果を比較する（DeepDB使用時のみ有効）'
    )
    parser.add_argument(
        '--use-pruning',
        action='store_true',
        help='CF Pruningを使用してMV候補を削減する（大きなタイムステップ数の場合に推奨）'
    )
    parser.add_argument(
        '--pruning-parallel',
        action='store_true',
        help='CF Pruningを並列実行する（多コアサーバーで推奨）'
    )
    parser.add_argument(
        '--pruning-workers',
        type=int,
        default=None,
        help='並列実行時のワーカー数（デフォルト：CPUコア数）'
    )
    parser.add_argument(
        '--static-protection',
        action='store_true',
        help='プルーニング時に静的最適化のMVを聖域として保護する（ハイブリッドアプローチ）'
    )
    parser.add_argument(
        '--exp-suffix',
        type=str,
        default='',
        help='実験識別用サフィックス（例：_16_2, _16_4）。頻度ファイルと最適化結果ファイルに適用'
    )
    parser.add_argument(
        '--static-timestep',
        type=str,
        default='last',
        choices=['first', 'last', 'average', 'addmv'],
        help='静的最適化で使用するタイムステップ (first: 最初, last: 最後, average: 全時刻の平均, addmv: 頻度和+MV作成コスト考慮)'
    )
    parser.add_argument(
        '--static-algorithm',
        type=str,
        default='normal',
        choices=['normal', 'bigsubs', 'both', 'utility'],
        help='静的最適化で使用するアルゴリズム (normal: 通常ILP, bigsubs: BigSubs, both: 両方, utility: UtilityOptimizerV2)'
    )
    parser.add_argument(
        '--ease',
        action='store_true',
        help='簡易ベンチマークモード: 各クエリを1回だけ実行し、実行時間に頻度を掛けて推定時間を算出'
    )
    parser.add_argument(
        '--recalc',
        action='store_true',
        help='再計算されたコスト（simple_migration_costs.json）を使用してマイグレーションと利得を計算する'
    )
    parser.add_argument(
        '--noise-ratio',
        type=float,
        default=0.0,
        help='ノイズ注入率 (0.0〜1.0)。指定した確率で各クエリ実行をノイズクエリに差し替える。ease_modeでは無効。例: 0.2 = 20%%のクエリがノイズに置換'
    )
    parser.add_argument(
        '--noise-query-dir',
        type=str,
        default=None,
        help='ノイズ用クエリが格納されているディレクトリ（デフォルト: experiments/small_test_ver2/01_queries/job）'
    )
    parser.add_argument(
        '--window-size',
        type=int,
        default=4,
        help='適応的最適化で使用する移動平均の幅（デフォルト: 4）'
    )
    parser.add_argument(
        '--b-max',
        type=float,
        default=100.0,
        help='ストレージ予算 B_max（MB単位、デフォルト: 100）。フェーズ6/6b/6cで使用'
    )
    parser.add_argument(
        '--no-wst-parent-constraints',
        action='store_true',
        help='WSTにおける親ノードからの境界制約伝播を無効化する (default: 有効)'
    )

    # Docker/Local switching arguments
    add_docker_args(parser)
    
    args = parser.parse_args()
    
    exp = NormalModeExperiment(
        exp_dir=args.config, 
        query_set=args.query_set, 
        exp_suffix=args.exp_suffix,
        use_docker=args.use_docker,
        recalc_mode=args.recalc,
        window_size=args.window_size
    )
    
    # 接続モードを表示
    print(f"\n[接続モード: {exp.pg_executor.get_mode_description()}]")
    
    if args.phase == 'all':
        success = exp.run_all_phases(
            optimization_mode=args.optimization_mode,
            use_pruning=args.use_pruning,
            pruning_parallel=args.pruning_parallel,
            pruning_workers=args.pruning_workers,
            static_timestep=args.static_timestep,
            use_static_protection=args.static_protection,
            noise_ratio=args.noise_ratio,
            noise_query_dir=args.noise_query_dir,
            b_max=args.b_max,
            inherit_parent_constraints=not args.no_wst_parent_constraints,
        )
    elif args.phase == 'post-opt':
        success = exp.run_post_optimization_phases(
            optimization_mode=args.optimization_mode,
            use_pruning=args.use_pruning,
            pruning_parallel=args.pruning_parallel,
            pruning_workers=args.pruning_workers,
            static_timestep=args.static_timestep,
            use_static_protection=args.static_protection,
            static_algorithm=args.static_algorithm,
            ease_mode=args.ease,
            noise_ratio=args.noise_ratio,
            noise_query_dir=args.noise_query_dir,
            b_max=args.b_max,
            inherit_parent_constraints=not args.no_wst_parent_constraints,
        )
    elif args.phase == '0':
        success = exp.phase0_setup()
    elif args.phase == '1':
        success = exp.phase1_generate_explain_json()
    elif args.phase == '2':
        success = exp.phase2_parse_queries()
    elif args.phase == '3':
        success = exp.phase3_annotate_json()
    elif args.phase == '4':
        success = exp.phase4_enumerate_migration_plans()
    elif args.phase == '5':
        success = exp.phase5_calculate_migration_costs(
            use_neurocard=args.use_neurocard,
            use_deepdb=args.use_deepdb,
            use_sampling=args.use_sampling,
            compare=args.compare
        )
    elif args.phase == '6':
        success = exp.phase6_optimize(
            mode=args.optimization_mode,
            use_pruning=args.use_pruning,
            pruning_parallel=args.pruning_parallel,
            pruning_workers=args.pruning_workers,
            static_timestep=args.static_timestep,
            use_static_protection=args.static_protection,
            b_max=args.b_max,
            inherit_parent_constraints=not args.no_wst_parent_constraints,
        )
    elif args.phase == '6.5':
        success = exp.phase6b_optimize_static(timestep_position=args.static_timestep, static_algorithm=args.static_algorithm, b_max=args.b_max)
    elif args.phase == '7':
        success = exp.phase7_generate_mv_sql(mode=args.optimization_mode)
    elif args.phase == '8':
        success = exp.phase8_rewrite_queries(mode=args.optimization_mode)
    elif args.phase == '9':
        success = exp.phase9_execute_benchmark(
            mode=args.benchmark_mode,
            ease_mode=args.ease,
            noise_ratio=args.noise_ratio,
            noise_query_dir=args.noise_query_dir
        )
    else:
        print(f"不明なフェーズ: {args.phase}")
        success = False
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
