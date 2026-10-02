#!/usr/bin/env python3
"""
Utility ベースの最適化結果を用いたベンチマーク実行スクリプト

run_time_dependent_utility.py で生成された
td_mv_optimization_result_utility{freq_suffix}.json を入力として、
フェーズ 7〜9（SQL 生成・クエリ書き換え・ベンチマーク実行）を行う。

使い方:
    python experiments/small_test_ver2/scripts/run_utility_benchmark.py --query-set job --freq-suffix _16_1
    
    # 簡易ベンチマーク（各クエリ1回 + 頻度掛け）
    python experiments/small_test_ver2/scripts/run_utility_benchmark.py --query-set job --freq-suffix _16_1 --ease
    
    # フェーズ指定
    python experiments/small_test_ver2/scripts/run_utility_benchmark.py --query-set job --freq-suffix _16_1 --phase 7
"""

import argparse
import json
import logging
import pickle
import re
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Optional

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(name)s - %(message)s'
)

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings

# 実験ディレクトリをパスに追加
experiment_dir = Path(__file__).parent.parent
sys.path.insert(0, str(experiment_dir))
from utils.postgres_executor import PostgresExecutor, add_docker_args


# ============================================================
# ヘルパー関数
# ============================================================
def print_header(title: str, phase: int = 0):
    print(f"\n{'=' * 70}")
    if phase:
        print(f"Phase {phase}: {title}")
    else:
        print(title)
    print(f"{'=' * 70}")


def print_success(msg: str):
    print(f"  [OK] {msg}")


def print_info(msg: str):
    print(f"  → {msg}")


def print_error(msg: str):
    print(f"  [ERROR] {msg}")


def natural_sort_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"([0-9]+)", str(s))]


# ============================================================
# Phase 7: マイグレーション SQL 生成
# ============================================================
def phase7_generate_mv_sql(exp_dir: Path, query_set: str, result_data: dict,
                           settings: Settings) -> bool:
    """最適化結果からタイムステップごとのマイグレーション SQL を生成"""
    print_header("マイグレーション SQL 作成（utility ベース）", 7)

    try:
        # マイグレーションプランを読み込み
        plans_file = exp_dir / "04_migration" / query_set / "simple_migration_plans.json"
        if not plans_file.exists():
            print_error(f"マイグレーションプランが見つかりません: {plans_file}")
            print_info("先にフェーズ 4 を実行してください")
            return False

        with open(plans_file, 'r', encoding='utf-8') as f:
            migration_plans = json.load(f)

        print_info(f"マイグレーションプラン読み込み完了: {len(migration_plans)} 個の MV")

        # 出力ディレクトリ
        output_dir = exp_dir / "time_dependent_output" / query_set
        output_dir.mkdir(parents=True, exist_ok=True)

        # 既存のマイグレーション SQL ファイルを削除
        existing_sql_files = list(output_dir.glob("timestep_*.sql"))
        if existing_sql_files:
            print_info(f"既存のマイグレーション SQL ファイルを削除中: {len(existing_sql_files)} 個")
            for sql_file in existing_sql_files:
                sql_file.unlink()
            print_success("既存ファイルを削除完了")

        migration_analysis = result_data['migration_analysis']
        timesteps = result_data['timesteps']
        print_info(f"タイムステップ数: {len(timesteps)}")

        total_sql_count = 0

        for t_idx, timestep_info in enumerate(migration_analysis):
            timestep_name = timestep_info['timestep']
            current_mvs = set(timestep_info.get('selected_mvs', []))

            prev_mvs = set()
            if t_idx > 0:
                prev_mvs = set(migration_analysis[t_idx - 1].get('selected_mvs', []))

            mvs_to_create = current_mvs - prev_mvs
            mvs_to_drop = prev_mvs - current_mvs

            if not mvs_to_create and not mvs_to_drop:
                print_info(f"  タイムステップ '{timestep_name}': 変更なし（スキップ）")
                continue

            output_file = output_dir / f"timestep_{t_idx}_{timestep_name}.sql"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"-- =====================================================\n")
                f.write(f"-- タイムステップ {t_idx}: {timestep_name}\n")
                f.write(f"-- =====================================================\n\n")
                f.write(f"\\c {settings.database.database}\n\n")

                # 統計情報の詳細度を設定（ファイル全体に適用）
                # if mvs_to_create:
                #     f.write(f"-- 統計情報を拡大（statistics_target = 1000）\n")
                #     f.write(f"SET default_statistics_target = 1000;\n\n")

                if mvs_to_drop:
                    f.write(f"-- 削除する MV: {len(mvs_to_drop)} 個\n")
                    for mv_id in sorted(mvs_to_drop):
                        f.write(f"DROP MATERIALIZED VIEW IF EXISTS {mv_id} CASCADE;\n")
                    f.write("\n")

                if mvs_to_create:
                    f.write(f"-- 新規作成する MV: {len(mvs_to_create)} 個\n\n")
                    created_count = 0
                    for mv_id in sorted(mvs_to_create):
                        if mv_id not in migration_plans:
                            print_info(f"  警告: {mv_id} のマイグレーションプランが見つかりません")
                            continue

                        plans = migration_plans[mv_id]
                        if "[]" in plans:
                            sql = plans["[]"]
                            if sql and sql != "NON_MIGRATE":
                                f.write(f"-- MV: {mv_id}\n")
                                f.write(f"{sql}\n")
                                f.write(f"ANALYZE {mv_id};\n\n")
                                created_count += 1

                    f.write(f"-- {created_count} 個の MV を作成\n\n")
                    # 統計情報の設定を元に戻す
                    # f.write(f"-- 統計情報の設定を元に戻す\n")
                    # f.write(f"RESET default_statistics_target;\n")

            sql_count = len(mvs_to_create) + len(mvs_to_drop)
            total_sql_count += sql_count
            print_success(f"  タイムステップ '{timestep_name}': {output_file.name}")
            print_info(f"    作成: {len(mvs_to_create)} 個, 削除: {len(mvs_to_drop)} 個")

        print_success(f"タイムステップごとのマイグレーション SQL を生成 → {output_dir}")
        print_info(f"  総操作数: {total_sql_count}")
        return True

    except Exception as e:
        print_error(f"SQL 生成に失敗: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================
# Phase 8: クエリ書き換え
# ============================================================
def phase8_rewrite_queries(exp_dir: Path, query_set: str, result_data: dict,
                           settings: Settings, qp) -> bool:
    """最適化結果に基づいてタイムステップごとにクエリを書き換え"""
    print_header("クエリ書き換え（utility ベース）", 8)

    from src.rewrite.query_rewriter import QueryRewriter
    from src.core.models import MaterializedView

    # マイグレーションプラン読み込み
    plans_file = exp_dir / "04_migration" / query_set / "simple_migration_plans.json"
    if not plans_file.exists():
        print_error("マイグレーションプランが見つかりません")
        return False

    with open(plans_file, 'r', encoding='utf-8') as f:
        migration_plans = json.load(f)

    print_info(f"マイグレーションプラン読み込み完了: {len(migration_plans)} 個の MV")

    # クエリファイル一覧
    queries_dir = exp_dir / "01_queries" / query_set
    query_files = sorted(queries_dir.glob("*.sql"), key=lambda x: x.name)
    if not query_files:
        print_error("クエリファイルが見つかりません")
        return False
    print_info(f"クエリ数: {len(query_files)}")

    # 出力ベースディレクトリ
    base_output_dir = exp_dir / "time_dependent_output" / query_set / "jobs"
    base_output_dir.mkdir(parents=True, exist_ok=True)

    migration_analysis = result_data['migration_analysis']
    print_info(f"タイムステップ数: {len(migration_analysis)}")

    total_rewritten = 0

    for t_idx, timestep_info in enumerate(migration_analysis):
        timestep_name = timestep_info['timestep']
        selected_mvs = timestep_info.get('selected_mvs', [])

        print_info(f"\nタイムステップ {t_idx} ({timestep_name}): {len(selected_mvs)} 個の MV")

        # MaterializedView オブジェクト作成
        mv_objects = []
        for node_id in selected_mvs:
            try:
                node_idx = qp.node_list.index(node_id)
            except ValueError:
                print_info(f"  警告: ノード {node_id} が見つかりません")
                continue

            node_size = qp.b_j[node_idx] if node_idx < len(qp.b_j) else 0
            usage_positions = qp.qm.subquery_positions.get(node_id, [])

            create_sql = ""
            if node_id in migration_plans:
                plans = migration_plans[node_id]
                if "[]" in plans:
                    sql = plans["[]"]
                    if sql and sql != "NON_MIGRATE":
                        create_sql = sql

            mv = MaterializedView(
                view_id=f"mv_{node_id}",
                node_id=node_id,
                create_sql=create_sql,
                size=node_size,
                maintenance_cost=0.0,
                usage_positions=usage_positions
            )
            mv_objects.append(mv)

        # タイムステップごとの出力ディレクトリ
        timestep_output_dir = base_output_dir / f"timestep_{t_idx}_{timestep_name}"
        if timestep_output_dir.exists():
            existing_sql_files = list(timestep_output_dir.glob("*.sql"))
            if existing_sql_files:
                print_info(f"  既存SQLをクリーンアップ: {len(existing_sql_files)}個")
                for sql_file in existing_sql_files:
                    sql_file.unlink()
        timestep_output_dir.mkdir(parents=True, exist_ok=True)

        # クエリ書き換え実行
        rewrite_settings = deepcopy(settings)
        rewrite_settings.benchmark.sql_dir = str(queries_dir.parent)

        rewriter = QueryRewriter(
            rewrite_settings,
            containment_matrix=qp.X,
            node_list=qp.node_list,
            query_set=query_set
        )
        rewritten_queries = rewriter.rewrite_queries(mv_objects)

        # 保存
        rewritten_count = 0
        for query_id, rewritten_sql in rewritten_queries.items():
            output_file = timestep_output_dir / f"{query_id}.sql"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(rewritten_sql)
            rewritten_count += 1

        total_rewritten += rewritten_count
        print_success(f"  {rewritten_count} 個のクエリを書き換え → {timestep_output_dir}")

    print_success(f"\n合計 {total_rewritten} 個のクエリを書き換え完了")
    print_info(f"  出力先: {base_output_dir}")
    return True


# ============================================================
# Phase 9: ベンチマーク実行
# ============================================================
def phase9_execute_benchmark(exp_dir: Path, query_set: str, freq_suffix: str,
                             result_data: dict, settings: Settings,
                             pg_executor: PostgresExecutor,
                             ease_mode: bool = False,
                             noise_ratio: float = 0.0,
                             noise_query_dir=None) -> bool:
    """時間依存型ベンチマークを実行"""
    print_header("時間依存型ベンチマーク実行（utility ベース）", 9)

    from experiments.small_test_ver2.benchmark import TimeDependentQueryExecutor
    from experiments.small_test_ver2.core.io_loaders import load_timesteps_and_frequencies
    import psycopg2

    # 既存のMVを全て削除（統一された初期状態を保証）
    # MV削除数が実行ごとに異なるとWAL生成量が変わり、不平等になるため最初に実行
    print_info("既存のMVをクリーンアップ中...")
    try:
        conn = psycopg2.connect(
            database=settings.database.database,
            user=settings.database.user,
            password=settings.database.password,
            host='localhost'
        )
        with conn.cursor() as cursor:
            cursor.execute("SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'")
            mvs = cursor.fetchall()
            dropped_count = 0
            for (mv_name,) in mvs:
                try:
                    cursor.execute(f"DROP MATERIALIZED VIEW IF EXISTS {mv_name} CASCADE;")
                    dropped_count += 1
                except Exception:
                    pass
        conn.commit()
        conn.close()
        print_success(f"{dropped_count}個の既存MVを削除完了")
    except Exception as e:
        print_info(f"MV削除をスキップ: {e}")

    # ベーステーブルの統計情報を更新（フェーズ1と同様に統計ターゲットを拡大）
    # 実行ごとにANALYZEを行うことで、最新の統計情報でベンチマークを実行
    print_info("ベーステーブルの統計情報を更新中...")
    base_tables = [
        # 大きなテーブル（主要な結合テーブル）
        'title', 'cast_info', 'movie_info', 'movie_companies',
        'movie_keyword', 'name', 'person_info', 'movie_info_idx',
        # 中規模テーブル
        'aka_name', 'aka_title', 'char_name', 'complete_cast',
        'movie_link',
        # 小さなテーブル（ディメンションテーブル）
        'keyword', 'company_name', 'company_type', 'info_type',
        'kind_type', 'role_type', 'link_type', 'comp_cast_type'
    ]
    
    try:
        conn = psycopg2.connect(
            database=settings.database.database,
            user=settings.database.user,
            password=settings.database.password,
            host='localhost'
        )
        with conn.cursor() as cursor:
            analyzed_count = 0
            for table in base_tables:
                try:
                    # 統計情報の詳細度を一時的に増やしてANALYZE
                    cursor.execute("SET default_statistics_target = 1000;")
                    cursor.execute(f"ANALYZE {table};")
                    cursor.execute("RESET default_statistics_target;")
                    analyzed_count += 1
                except Exception as e:
                    print_info(f"  警告: {table} のANALYZEに失敗: {e}")
        conn.commit()
        conn.close()
        print_success(f"{analyzed_count}/{len(base_tables)}個のベーステーブルをANALYZE完了")
    except Exception as e:
        print_error(f"ベーステーブルのANALYZEに失敗: {e}")
        return False

    # PostgreSQLキャッシュをクリア（公平なベンチマークのため）
    # print_info("PostgreSQLキャッシュをクリア中...")
    # try:
    #     pg_executor.execute_query("SELECT pg_drop_caches();")
    #     print_success("キャッシュクリア完了")
    # except Exception:
    #     try:
    #         pg_executor.execute_query("DISCARD ALL;")
    #         print_info("セッションキャッシュをクリア（DISCARD ALL）")
    #     except Exception:
    #         print_info("キャッシュクリアをスキップ")

    # Autovacuumを無効化（ベンチマーク中のバックグラウンド処理を抑制）
    # print_info("Autovacuumを無効化中...")
    # try:
    #     conn = psycopg2.connect(
    #         database=settings.database.database,
    #         user=settings.database.user,
    #         password=settings.database.password,
    #         host='localhost'
    #     )
    #     with conn.cursor() as cursor:
    #         cursor.execute("""
    #             SELECT tablename FROM pg_tables WHERE schemaname = 'public'
    #             UNION
    #             SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'
    #         """)
    #         tables = cursor.fetchall()
    #         disabled_count = 0
    #         for (table_name,) in tables:
    #             try:
    #                 cursor.execute(f"ALTER TABLE {table_name} SET (autovacuum_enabled = false);")
    #                 disabled_count += 1
    #             except Exception:
    #                 pass
    #     conn.commit()
    #     conn.close()
    #     print_success(f"Autovacuumを無効化: {disabled_count}個のテーブル/MV")
    # except Exception as e:
    #     print_info(f"Autovacuum無効化をスキップ: {e}")

    # 強制チェックポイントを実行（WALバッファをクリアして同じ初期状態から開始）
    print_info("強制チェックポイントを実行中（WALバッファをクリア）...")
    try:
        conn = psycopg2.connect(
            database=settings.database.database,
            user=settings.database.user,
            password=settings.database.password,
            host='localhost'
        )
        checkpoint_start = time.time()
        with conn.cursor() as cursor:
            cursor.execute("CHECKPOINT;")
        conn.commit()
        conn.close()
        checkpoint_time = time.time() - checkpoint_start
        print_success(f"チェックポイント完了 ({checkpoint_time:.2f}秒)")
    except Exception as e:
        print_info(f"チェックポイント実行をスキップ: {e}")

    # 頻度情報読み込み
    print_info("頻度情報を読み込み中...")
    try:
        timesteps, frequencies_by_timestep = load_timesteps_and_frequencies(
            str(exp_dir), query_set, freq_suffix=freq_suffix
        )
        print_success(f"  タイムステップ数: {len(timesteps)}")
    except Exception as e:
        print_error(f"頻度情報の読み込みに失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

    # クエリファイル
    queries_dir = exp_dir / "01_queries" / query_set
    original_query_files = sorted(queries_dir.glob("*.sql"),
                                  key=lambda x: natural_sort_key(x.name))
    if not original_query_files:
        print_error("クエリファイルが見つかりません")
        return False
    print_info(f"クエリ数: {len(original_query_files)}")

    # パス設定
    migration_sql_dir = exp_dir / "time_dependent_output" / query_set
    rewritten_queries_base_dir = exp_dir / "time_dependent_output" / query_set / "jobs"

    if not migration_sql_dir.exists():
        print_error(f"マイグレーション SQL ディレクトリが見つかりません: {migration_sql_dir}")
        print_info("先にフェーズ 7 を実行してください")
        return False

    # ベンチマーク実行
    executor = TimeDependentQueryExecutor(settings)
    
    # ノイズ注入の設定（ease_modeでは無効）
    if noise_ratio > 0.0 and not ease_mode:
        executor.noise_ratio = noise_ratio
        
        # ノイズ用クエリフォルダの決定（デフォルト: 01_queries/job）
        if noise_query_dir is not None:
            resolved_noise_dir = Path(noise_query_dir)
        else:
            resolved_noise_dir = queries_dir  # 01_queries/{query_set} の元クエリ
        
        print_info(f"ノイズ注入設定: ratio={noise_ratio:.2f}, dir={resolved_noise_dir}")
        loaded_count = executor.load_noise_pool(resolved_noise_dir)
        if loaded_count == 0:
            print_error(f"ノイズ用クエリが見つかりません: {resolved_noise_dir}")
            print_info("ノイズなしで続行します")
            executor.noise_ratio = 0.0
        else:
            print_success(f"  ノイズプール: {loaded_count}個のクエリを事前ロード完了")
    else:
        if noise_ratio > 0.0 and ease_mode:
            print_info("ease_modeではノイズ注入は無効です")
    
    try:
        print_info("ベンチマーク実行を開始します（モード: dynamic / utility）...\n")

        benchmark_results = executor.execute_time_dependent_benchmark(
            optimization_result=result_data,
            migration_sql_dir=migration_sql_dir,
            rewritten_queries_base_dir=rewritten_queries_base_dir,
            frequencies_by_timestep=frequencies_by_timestep,
            timeout_minutes=60,
            verbose=True,
            ease_mode=ease_mode
        )

        # 結果保存
        output_dir = exp_dir / "time_dependent_output" / query_set
        output_dir.mkdir(parents=True, exist_ok=True)
        # noise_ratio > 0 の場合はファイル名に _noise{XX} を付与して衝突を回避
        noise_suffix = f"_noise{int(noise_ratio * 100)}" if noise_ratio > 0.0 else ""
        output_file = output_dir / f"benchmark_results_dynamic_utility{freq_suffix}{noise_suffix}.json"

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(benchmark_results, f, indent=2, ensure_ascii=False)

        print_success(f"\nベンチマーク結果を保存: {output_file}")

        # サマリー表示
        summary = benchmark_results.get('summary', {})
        print_info(f"  総タイムステップ数: {summary.get('total_timesteps', 0)}")
        print_info(f"  総マイグレーション時間: {summary.get('total_migration_time', 0):.2f} 秒")
        print_info(f"  総クエリ実行時間: {summary.get('total_query_time', 0):.2f} 秒")
        print_info(f"  総ベンチマーク時間: {summary.get('total_benchmark_time', 0):.2f} 秒")
        return True

    except Exception as e:
        print_error(f"ベンチマーク実行に失敗: {e}")
        import traceback
        traceback.print_exc()
        return False
    # finally:
    #     # Autovacuumを有効化（元に戻す）
    #     print_info("Autovacuumを有効化中...")
    #     try:
    #         conn = psycopg2.connect(
    #             database=settings.database.database,
    #             user=settings.database.user,
    #             password=settings.database.password,
    #             host='localhost'
    #         )
    #         with conn.cursor() as cursor:
    #             cursor.execute("""
    #                 SELECT tablename FROM pg_tables WHERE schemaname = 'public'
    #                 UNION
    #                 SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'
    #             """)
    #             tables = cursor.fetchall()
    #             enabled_count = 0
    #             for (table_name,) in tables:
    #                 try:
    #                     cursor.execute(f"ALTER TABLE {table_name} RESET (autovacuum_enabled);")
    #                     enabled_count += 1
    #                 except Exception:
    #                     pass
    #         conn.commit()
    #         conn.close()
    #         print_success(f"Autovacuumを有効化: {enabled_count}個のテーブル/MV")
    #     except Exception as e:
    #         print_info(f"Autovacuum有効化エラー: {e}")
    #     
    #     executor.close()


# ============================================================
# メイン
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="Utility ベース最適化結果のベンチマーク実行（Phase 7-9）"
    )
    parser.add_argument(
        '--phase', type=str, default='all',
        choices=['all', '7', '8', '9'],
        help='実行するフェーズ (all: 7-9 全実行, 7: SQL 生成, 8: クエリ書き換え, 9: ベンチマーク)'
    )
    parser.add_argument(
        '--config', type=str, default='experiments/small_test_ver2',
        help='実験ディレクトリのパス'
    )
    parser.add_argument(
        '--query-set', type=str, default='job',
        help='クエリセット名 (job, job_like, etc.)'
    )
    parser.add_argument(
        '--freq-suffix', type=str, default='',
        help='頻度ファイルのサフィックス (例: _16_1, _16_mono)'
    )
    parser.add_argument(
        '--ease', action='store_true',
        help='簡易ベンチマークモード: 各クエリ 1 回実行 + 頻度掛け'
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

    # Docker/Local switching
    add_docker_args(parser)

    args = parser.parse_args()

    exp_dir = Path(args.config)
    query_set = args.query_set
    freq_suffix = args.freq_suffix

    # 結果ファイル読み込み
    result_file = (exp_dir / "time_dependent_output" / query_set
                   / f"td_mv_optimization_result_utility{freq_suffix}.json")
    if not result_file.exists():
        print_error(f"最適化結果が見つかりません: {result_file}")
        print_info("先に run_time_dependent_utility.py を実行してください")
        sys.exit(1)

    with open(result_file, 'r', encoding='utf-8') as f:
        result_data = json.load(f)

    if 'migration_analysis' not in result_data:
        print_error("migration_analysis が結果ファイルに含まれていません")
        sys.exit(1)

    print_info(f"最適化結果を読み込み: {result_file.name}")

    # Settings
    settings = Settings()

    # PostgresExecutor（Phase 9 で必要）
    pg_executor = PostgresExecutor(use_docker=args.use_docker)
    print(f"\n[接続モード: {pg_executor.get_mode_description()}]")

    # QueryParser（Phase 8 で必要）
    pickle_path = exp_dir / "03_parsed" / query_set / "qp_class.pkl"
    qp = None

    # ----- フェーズ実行 -----
    phases_to_run = []
    if args.phase == 'all':
        phases_to_run = ['7', '8', '9']
    else:
        phases_to_run = [args.phase]

    total_start = time.time()
    phase_times = {}

    for phase in phases_to_run:
        phase_start = time.time()

        if phase == '7':
            success = phase7_generate_mv_sql(exp_dir, query_set, result_data, settings)

        elif phase == '8':
            # QueryParser をロード（必要な場合）
            if qp is None:
                if not pickle_path.exists():
                    print_error(f"パース結果が見つかりません: {pickle_path}")
                    sys.exit(1)
                print_info("QueryParser を読み込み中...")
                with open(pickle_path, 'rb') as f:
                    qp = pickle.load(f)
                print_success("QueryParser 読み込み完了")

            success = phase8_rewrite_queries(exp_dir, query_set, result_data, settings, qp)

        elif phase == '9':
            success = phase9_execute_benchmark(
                exp_dir, query_set, freq_suffix, result_data, settings,
                pg_executor, ease_mode=args.ease,
                noise_ratio=args.noise_ratio,
                noise_query_dir=args.noise_query_dir
            )

        else:
            print_error(f"不明なフェーズ: {phase}")
            success = False

        phase_times[f"phase{phase}"] = time.time() - phase_start

        if not success:
            print_error(f"Phase {phase} で失敗しました")
            sys.exit(1)

    total_elapsed = time.time() - total_start

    # サマリー
    print_header("実行完了")
    print_success(f"総実行時間: {total_elapsed:.2f} 秒")
    if len(phase_times) > 1:
        print_info("フェーズ別実行時間:")
        for phase_name, elapsed in phase_times.items():
            print_info(f"  {phase_name}: {elapsed:.2f} 秒")

    sys.exit(0)


if __name__ == "__main__":
    main()
