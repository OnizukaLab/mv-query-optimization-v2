"""Redbench エンドツーエンド実験ランナー.

最適化 → MV 生成 → MV 作成 → クエリ書き換え → ベンチマーク の全フェーズを実行し、
bigsubs と topk-F の結果を比較する。

使い方 (CLI):
    python -m src.runners.redbench_experiment
    python -m src.runners.redbench_experiment --b-max-mb 100 --output-dir Output/my_run
"""
from __future__ import annotations

import argparse
import json
import logging
import pickle
import sys
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import Settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# 共通ユーティリティ
# ──────────────────────────────────────────────────────────────────────────────

def _topological_sort(mvs: list, qm) -> list:
    """MV を依存関係順（子→親）にソート."""
    mv_dict = {mv.node_id: mv for mv in mvs}
    in_degree = {nid: 0 for nid in mv_dict}
    graph = defaultdict(list)

    for nid in mv_dict:
        if nid.startswith("non_leaf_") and nid in qm.non_leaf_nodes_map_r:
            for child in qm.non_leaf_nodes_map_r[nid]:
                if child in mv_dict:
                    graph[child].append(nid)
                    in_degree[nid] += 1

    queue = deque([nid for nid in mv_dict if in_degree[nid] == 0])
    order = []
    while queue:
        nid = queue.popleft()
        order.append(nid)
        for nb in graph[nid]:
            in_degree[nb] -= 1
            if in_degree[nb] == 0:
                queue.append(nb)

    if len(order) != len(mv_dict):
        order += [nid for nid in mv_dict if nid not in order]

    return [mv_dict[nid] for nid in order]


def _drop_all_mvs(settings: Settings):
    """PostgreSQL 上の全 MV と IMMV テーブル (leaf_*/non_leaf_*) を削除."""
    from src.database.connection import DatabaseConnection
    db = DatabaseConnection(settings.database)
    conn = db.get_connection()
    cursor = conn.cursor()

    # 通常のマテリアライズドビューを削除
    cursor.execute("SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'")
    mv_names = [r[0] for r in cursor.fetchall()]
    for name in mv_names:
        try:
            cursor.execute(f"DROP MATERIALIZED VIEW IF EXISTS {name} CASCADE;")
        except Exception:
            conn.rollback()

    # pg_ivm IMMV テーブル (leaf_* / non_leaf_*) を削除
    cursor.execute("""
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public'
          AND (tablename LIKE 'leaf\\_%' ESCAPE '\\' OR tablename LIKE 'non\\_leaf\\_%' ESCAPE '\\')
    """)
    tbl_names = [r[0] for r in cursor.fetchall()]
    for name in tbl_names:
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {name} CASCADE;")
        except Exception:
            conn.rollback()

    conn.commit()
    cursor.close()
    db.close()
    total = len(mv_names) + len(tbl_names)
    if total:
        logger.info(f"  Dropped {len(mv_names)} MVs + {len(tbl_names)} IMMV tables")


# ──────────────────────────────────────────────────────────────────────────────
# フェーズ実装
# ──────────────────────────────────────────────────────────────────────────────

def apply_sampling_costs(qp, sampling_costs_path: Path) -> int:
    """simple_migration_costs.json のサンプリング結果で qp.b_j と qm.subquery_sizes を更新する.

    サンプリング成功ノード（size_source='sampling'）のみ上書きし、
    EXPLAIN フォールバックノードはそのまま保持する。

    Returns:
        更新したノード数
    """
    if not sampling_costs_path.exists():
        logger.warning(f"  sampling costs not found: {sampling_costs_path}")
        return 0

    with open(sampling_costs_path) as f:
        costs = json.load(f)

    updated = 0
    for j, node_id in enumerate(qp.node_list):
        entry = costs.get(node_id, {}).get("[]")
        if not isinstance(entry, dict):
            continue
        if entry.get("size_source") == "sampling" and entry.get("size", 0) > 0:
            size = float(entry["size"])
            qp.b_j[j] = size
            qp.qm.subquery_sizes[node_id] = size
            updated += 1

    logger.info(f"  b_j 更新 (sampling): {updated}/{len(qp.node_list)} nodes")
    total_mb = sum(qp.b_j) / 1024 / 1024
    logger.info(f"  b_j 合計: {total_mb:.1f} MB")
    return updated


def phase_optimize(qp, algorithm: str, b_max: float, settings: Settings):
    """最適化フェーズ: bigsubs または topkf の選択 MV を返す."""
    q_num = len(qp.u_ij)
    freq_weights = [float(qp.query_frequencies.get(i, 1)) for i in range(q_num)]
    weighted_u_ij = [
        [qp.u_ij[i][j] * freq_weights[i] for j in range(len(qp.node_list))]
        for i in range(q_num)
    ]
    b_j = list(qp.b_j)
    m_cost = list(qp.m_cost)
    index_build_costs = list(qp.index_build_costs) if hasattr(qp, "index_build_costs") else None
    s_num = len(qp.node_list)

    nonzero_ibc = sum(1 for v in (index_build_costs or []) if v > 0)
    logger.info(f"  index_build_costs: 非ゼロ={nonzero_ibc}/{s_num}")

    if algorithm == "bigsubs":
        from src.optimization.bigsubs import BigSubsOptimizer
        U_j_max = [sum(weighted_u_ij[i][j] for i in range(q_num)) for j in range(s_num)]
        opt = BigSubsOptimizer(
            qm=qp.qm, s_num=s_num, m_cost=m_cost, node_list=qp.node_list,
            B_max=b_max, b_j=b_j, u_ij=weighted_u_ij, X=qp.X,
            q_s_list=qp.q_s_list, settings=settings,
            U_j_max=U_j_max, U_max=sum(U_j_max),
            y_ij=getattr(qp, "y_ij", [[0]*s_num for _ in range(q_num)]),
            index_build_costs=index_build_costs,
        )
        return opt.optimize(iter_max=200)

    elif algorithm == "topkf":
        from src.optimization.frequency import FrequencyOptimizer
        opt = FrequencyOptimizer(
            qm=qp.qm, s_num=s_num, m_cost=m_cost, node_list=qp.node_list,
            B_max=b_max, b_j=b_j, u_ij=weighted_u_ij, X=qp.X,
            q_s_list=qp.q_s_list, settings=settings,
            position_node_id=qp.position_node_id, deeplist=qp.deeplist,
            query_frequencies=qp.query_frequencies,
            index_build_costs=index_build_costs,
        )
        return opt.optimize()

    elif algorithm == "normal":
        from src.optimization.normal import NormalOptimizer
        opt = NormalOptimizer(
            qm=qp.qm, s_num=s_num, m_cost=m_cost, node_list=qp.node_list,
            B_max=b_max, b_j=b_j, u_ij=weighted_u_ij, X=qp.X,
            q_s_list=qp.q_s_list, settings=settings,
            index_build_costs=index_build_costs,
        )
        return opt.optimize()

    elif algorithm == "topku":
        from src.optimization.utility import UtilityOptimizer
        opt = UtilityOptimizer(
            qm=qp.qm, s_num=s_num, m_cost=m_cost, node_list=qp.node_list,
            B_max=b_max, b_j=b_j, u_ij=weighted_u_ij, X=qp.X,
            q_s_list=qp.q_s_list, settings=settings,
            position_node_id=qp.position_node_id, deeplist=qp.deeplist,
            index_build_costs=index_build_costs,
        )
        return opt.optimize()

    elif algorithm == "topke":
        from src.optimization.utility_capacity import UtilityCapacityOptimizer
        opt = UtilityCapacityOptimizer(
            qm=qp.qm, s_num=s_num, m_cost=m_cost, node_list=qp.node_list,
            B_max=b_max, b_j=b_j, u_ij=weighted_u_ij, X=qp.X,
            q_s_list=qp.q_s_list, settings=settings,
            position_node_id=qp.position_node_id, deeplist=qp.deeplist,
            index_build_costs=index_build_costs,
        )
        return opt.optimize()

    raise ValueError(f"Unknown algorithm: {algorithm}")


def phase_generate_sql(result, qp):
    """SQL 生成フェーズ: 各 MV に create_sql を付与."""
    from src.rewrite.enhanced_mv_generator import EnhancedMVGenerator
    gen = EnhancedMVGenerator(qp.qm, schema_provider=None)
    ok = fail = 0
    for mv in result.selected_views:
        try:
            create_sql, index_sql = gen.generate_mv_and_index_sql(mv.node_id)
            mv.create_sql = create_sql
            mv.index_sql = index_sql
            ok += 1
        except Exception as e:
            mv.create_sql = f"-- Failed: {e}"
            mv.index_sql = None
            fail += 1
    logger.info(f"  SQL generated: {ok} ok, {fail} failed")


def update_base_table_statistics(settings: Settings, target: int = 1000):
    """JOB の主要 join カラムに statistics_target を設定して ANALYZE する.

    デフォルト (target=100) では cardinality の推定精度が低いため、
    target=1000 に上げることで EXPLAIN の推定精度を改善する。
    """
    from src.database.connection import DatabaseConnection

    # JOB ワークロードで結合に使われる大規模テーブルの主要カラム
    columns = [
        ("movie_keyword",  "keyword_id"),
        ("movie_keyword",  "movie_id"),
        ("cast_info",      "movie_id"),
        ("cast_info",      "person_id"),
        ("movie_companies","movie_id"),
        ("movie_companies","company_id"),
        ("movie_info",     "movie_id"),
        ("movie_info",     "info_type_id"),
        ("person_info",    "person_id"),
        ("title",          "id"),
        ("name",           "id"),
    ]

    db = DatabaseConnection(settings.database)
    conn = db.get_connection()
    cur = conn.cursor()

    logger.info(f"  statistics_target={target} を設定中...")
    altered = []
    for tbl, col in columns:
        try:
            cur.execute(
                f"ALTER TABLE {tbl} ALTER COLUMN {col} SET STATISTICS {target};"
            )
            altered.append(f"{tbl}.{col}")
        except Exception as e:
            logger.warning(f"    ALTER failed {tbl}.{col}: {e}")
            conn.rollback()

    conn.commit()
    logger.info(f"  {len(altered)} カラムを更新: {altered}")

    logger.info("  ANALYZE 実行中...")
    t0 = time.time()
    analyzed = []
    seen_tables = []
    for tbl, _ in columns:
        if tbl not in seen_tables:
            seen_tables.append(tbl)
    for tbl in seen_tables:
        try:
            cur.execute(f"ANALYZE {tbl};")
            analyzed.append(tbl)
        except Exception as e:
            logger.warning(f"    ANALYZE failed {tbl}: {e}")
            conn.rollback()
    conn.commit()
    cur.close()
    db.close()
    logger.info(f"  ANALYZE 完了: {analyzed} ({time.time()-t0:.1f}s)")


def phase_create_mvs(result, qp, settings: Settings, use_immv: bool = False) -> dict:
    """MV 作成フェーズ: CREATE MATERIALIZED VIEW (or IMMV) + インデックス + ANALYZE を実行.

    Args:
        use_immv: True のとき pgivm.create_immv() で IMMV として作成を試みる。
                  失敗時は通常 MV にフォールバックする。
    Returns:
        dict に immv_names (IMMV として作成した MV 名), regular_names (通常 MV 名) を含む。
    """
    import re
    import psycopg2
    from src.database.connection import DatabaseConnection
    from src.database.mv_manager import MaterializedViewManager

    db = DatabaseConnection(settings.database)
    mv_manager = MaterializedViewManager(db)
    sorted_mvs = _topological_sort(result.selected_views, qp.qm)

    created = failed = idx_created = immv_ok = 0
    immv_names: list[str] = []
    regular_names: list[str] = []
    log = []
    t0 = time.time()

    # IMMV 作成用の raw psycopg2 接続
    raw_conn = None
    if use_immv:
        s = settings.database
        raw_conn = psycopg2.connect(
            host=s.host, port=s.port, dbname=s.database,
            user=s.user, password=s.password,
        )
        raw_conn.autocommit = False

    for idx, mv in enumerate(sorted_mvs, 1):
        ts = time.time()
        logger.info(f"  [{idx}/{len(sorted_mvs)}] Creating {mv.view_id}...")

        # MV 名を抽出
        name_match = re.search(r"CREATE\s+MATERIALIZED\s+VIEW\s+(\w+)", mv.create_sql, re.IGNORECASE)
        vname = name_match.group(1) if name_match else mv.view_id

        created_as_immv = False

        try:
            if use_immv and raw_conn is not None:
                # SELECT ボディを抽出: "CREATE MATERIALIZED VIEW vname AS {body} [WITH [NO] DATA][;]"
                as_match = re.search(r"\bAS\b", mv.create_sql, re.IGNORECASE)
                query_body = None
                if as_match:
                    body = mv.create_sql[as_match.end():].strip()
                    body = re.sub(r'\s+WITH\s+(?:NO\s+)?DATA\s*$', '', body, flags=re.IGNORECASE)
                    query_body = body.rstrip(';').strip()

                if query_body:
                    try:
                        with raw_conn.cursor() as cur:
                            cur.execute(f"DROP TABLE IF EXISTS {vname} CASCADE")
                            cur.execute("SELECT pgivm.create_immv(%s, %s)", (vname, query_body))
                            cur.fetchone()
                        raw_conn.commit()
                        created_as_immv = True
                        immv_ok += 1
                        immv_names.append(vname)
                        logger.info(f"    → IMMV 作成成功")
                    except Exception as ie:
                        raw_conn.rollback()
                        logger.warning(f"    IMMV 失敗 ({str(ie)[:70]}), 通常 MV にフォールバック")

            if not created_as_immv:
                ok = mv_manager.create_view_from_model(mv, replace=True)
                elapsed = time.time() - ts
                if not ok:
                    failed += 1
                    log.append({"view_id": mv.view_id, "status": "failed"})
                    continue
                regular_names.append(vname)

            elapsed = time.time() - ts
            created += 1

            # インデックス作成 (IMMV・通常MV 共通: IMMV も regular table なので CREATE INDEX 可)
            if mv.index_sql:
                try:
                    db.execute(mv.index_sql)
                    idx_created += 1
                except Exception as ie:
                    logger.warning(f"    index failed: {str(ie)[:60]}")

            # ANALYZE
            try:
                db.execute(f"ANALYZE {vname}")
            except Exception:
                pass

            tag = " [IMMV]" if created_as_immv else ""
            logger.info(f"    ✓{tag} {elapsed:.1f}s")
            log.append({
                "view_id": mv.view_id, "status": "ok",
                "time": round(elapsed, 2), "has_index": bool(mv.index_sql),
                "immv": created_as_immv,
            })

        except Exception as e:
            elapsed = time.time() - ts
            failed += 1
            if raw_conn:
                try:
                    raw_conn.rollback()
                except Exception:
                    pass
            logger.warning(f"    ✗ {str(e)[:80]}")
            log.append({"view_id": mv.view_id, "status": "error", "error": str(e)[:120]})

    if raw_conn:
        raw_conn.close()
    total_time = time.time() - t0
    db.close()
    logger.info(
        f"  MV creation: {created}/{len(sorted_mvs)} ok "
        f"(IMMV={immv_ok}, 通常MV={created - immv_ok}), "
        f"{idx_created} indexes, {total_time:.1f}s"
    )
    return {
        "created": created, "failed": failed,
        "immv_created": immv_ok,
        "immv_names": immv_names,
        "regular_names": regular_names,
        "indexes_created": idx_created,
        "total_time": round(total_time, 2),
        "log": log,
    }


def phase_rewrite_queries(result, settings: Settings, rewrite_out_dir: Path) -> int:
    """クエリ書き換えフェーズ: 書き換え済み SQL を rewrite_out_dir に保存."""
    from src.rewrite.query_rewriter import QueryRewriter

    rewrite_out_dir.mkdir(parents=True, exist_ok=True)
    rewriter = QueryRewriter(settings)
    rewritten = rewriter.rewrite_queries(result.selected_views)

    for query_id, sql in rewritten.items():
        (rewrite_out_dir / f"{query_id}.sql").write_text(sql)

    logger.info(f"  Rewritten {len(rewritten)} queries → {rewrite_out_dir}")
    return len(rewritten)


def phase_copy_ceb_queries(rewrite_out_dir: Path) -> int:
    """RED_WORKLOADS で参照される CEB クエリ原文を rewrite_out_dir にコピーする。

    書き換えディレクトリに存在しない CEB クエリ（ハッシュ名 .sql）を原文のまま配置することで、
    workload_type="redbench" 実行時に CEB クエリもベンチマーク対象に含める。
    """
    import glob as _glob
    import shutil

    workloads_dir = PROJECT_ROOT / "Output" / "RED_WORKLOADS"
    sql_base_dir = PROJECT_ROOT / "dataset" / "RED_SQL"

    # RED_WORKLOADS CSV から CEB クエリファイル名（ハッシュ）と元パスを収集
    ceb_files: dict[str, Path] = {}  # {filename: original_path}
    for csvf in sorted(workloads_dir.rglob("*.csv")):
        if csvf.name == "stats.csv":
            continue
        with open(csvf) as f:
            for line in f.readlines()[1:]:
                rel = line.split(",")[0].strip()
                fname = rel.split("/")[-1]
                if not fname.endswith(".sql") or fname[0].isdigit():
                    continue  # JOB クエリはスキップ
                if fname in ceb_files:
                    continue
                # 元ファイルを dataset/RED_SQL/ceb/ 以下から探す
                parts = rel.split("/")
                if len(parts) >= 2:
                    template = parts[-2]
                    cand = sql_base_dir / "ceb" / template / fname
                    if cand.exists():
                        ceb_files[fname] = cand

    copied = 0
    for fname, src in ceb_files.items():
        dst = rewrite_out_dir / fname
        if not dst.exists():
            shutil.copy2(src, dst)
            copied += 1

    logger.info(f"  CEB クエリ {len(ceb_files)} 件を配置 (新規コピー {copied} 件) → {rewrite_out_dir}")
    return len(ceb_files)


def phase_benchmark(algo_label: str, output_base: Path, settings: Settings,
                    query_timeout_minutes: int = 5, workload_type: str = "redbench-job") -> dict:
    """ベンチマークフェーズ: 指定ワークロードを実行."""
    from src.benchmark.workload_runner import run_workload_benchmark

    benchmark_dir = output_base / algo_label / "benchmark"
    benchmark_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"  Running {workload_type} workload (algorithm={algo_label}, timeout={query_timeout_minutes}min)...")
    results = run_workload_benchmark(
        workload_type=workload_type,
        algorithm=algo_label,
        settings=settings,
        output_dir=output_base,
        verbose=False,
        warmup=True,
        timeout_minutes=query_timeout_minutes,
    )
    with open(benchmark_dir / "benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    return results


def phase_update_benchmark(settings: Settings, n_updates: int = 1000) -> dict:
    """更新ベンチマーク: n_updates 件の更新クエリを実行し MV 維持コストを計測する。

    各更新クエリは BEGIN/ROLLBACK で囲むため本番データは変更されない。
    IMMV のトリガーは BEGIN/ROLLBACK 内で自動発火するため、
    トリガー実行時間が総計測時間に含まれる。

    Returns:
        dict: n_updates, total_time, per_table (テーブルごとの集計)
    """
    import psycopg2
    from src.maintenance.update_workload import DEFAULT_UPDATE_FREQUENCY, _SAFE_UPDATE_TEMPLATES

    s = settings.database
    conn = psycopg2.connect(
        host=s.host, port=s.port, dbname=s.database,
        user=s.user, password=s.password,
    )
    conn.autocommit = False

    # DEFAULT_UPDATE_FREQUENCY に従って n_updates 件の更新クエリを生成
    total_freq = sum(DEFAULT_UPDATE_FREQUENCY.values())
    updates: list[tuple[str, str]] = []
    for table, freq in DEFAULT_UPDATE_FREQUENCY.items():
        if table not in _SAFE_UPDATE_TEMPLATES:
            continue
        count = round(n_updates * freq / total_freq)
        tmpl = _SAFE_UPDATE_TEMPLATES[table]
        for i in range(count):
            sql = tmpl.format(table=table, offset=i * 100)
            updates.append((table, sql))

    # 端数補正: n_updates に合わせる
    while len(updates) > n_updates:
        updates.pop()
    fallback_tmpl = _SAFE_UPDATE_TEMPLATES["cast_info"]
    while len(updates) < n_updates:
        sql = fallback_tmpl.format(table="cast_info", offset=len(updates) * 100)
        updates.append(("cast_info", sql))

    logger.info(f"  更新ベンチマーク: {len(updates)} 件の更新クエリを実行中...")
    per_table_times: dict[str, list[float]] = {}
    failures = 0
    total_t0 = time.time()

    with conn.cursor() as cur:
        for i, (table, sql) in enumerate(updates, 1):
            ts = time.perf_counter()
            try:
                cur.execute("BEGIN")
                cur.execute(sql)
                elapsed = time.perf_counter() - ts
                cur.execute("ROLLBACK")
            except Exception as e:
                elapsed = time.perf_counter() - ts
                conn.rollback()
                failures += 1
                logger.warning(f"    更新 [{i}] {table} 失敗: {str(e)[:60]}")
            per_table_times.setdefault(table, []).append(elapsed)
            if i % 200 == 0:
                logger.info(f"    {i}/{len(updates)} 完了 ({time.time() - total_t0:.1f}s)...")

    total_time = time.time() - total_t0
    conn.close()

    per_table_summary = {
        t: {
            "count": len(times),
            "total": round(sum(times), 3),
            "avg": round(sum(times) / len(times), 4),
        }
        for t, times in per_table_times.items()
    }

    logger.info(f"  更新ベンチマーク完了: {total_time:.2f}s / {len(updates)} 件 (失敗={failures})")
    for t, st in sorted(per_table_summary.items(), key=lambda x: -x[1]["total"]):
        logger.info(f"    {t}: {st['count']}件, 合計{st['total']:.2f}s, 平均{st['avg']:.4f}s")

    return {
        "n_updates": len(updates),
        "total_time": round(total_time, 2),
        "failures": failures,
        "per_table": per_table_summary,
    }


def phase_refresh_benchmark(mv_names: list[str], settings: Settings) -> dict:
    """通常 MV のリフレッシュベンチマーク: 全 MV を REFRESH して時間を計測する。

    Args:
        mv_names: REFRESH する MV 名のリスト（依存関係順）
        settings: DB 接続設定

    Returns:
        dict: n_refreshed, total_time, per_mv
    """
    from src.database.connection import DatabaseConnection

    if not mv_names:
        return {"n_refreshed": 0, "total_time": 0.0, "per_mv": {}}

    db = DatabaseConnection(settings.database)
    per_mv: dict[str, float] = {}
    total_t0 = time.time()
    logger.info(f"  REFRESH ベンチマーク: {len(mv_names)} 個の MV をリフレッシュ中...")

    for i, vname in enumerate(mv_names, 1):
        ts = time.time()
        try:
            db.execute(f"REFRESH MATERIALIZED VIEW {vname}")
        except Exception as e:
            logger.warning(f"    REFRESH {vname} 失敗: {str(e)[:60]}")
        per_mv[vname] = round(time.time() - ts, 3)
        if i % 10 == 0:
            logger.info(f"    {i}/{len(mv_names)} 完了 ({time.time() - total_t0:.1f}s)...")

    total_time = time.time() - total_t0
    db.close()
    logger.info(f"  REFRESH ベンチマーク完了: {total_time:.2f}s / {len(mv_names)} MV")
    top5 = sorted(per_mv.items(), key=lambda x: -x[1])[:5]
    for vname, t in top5:
        logger.info(f"    {vname}: {t:.2f}s (最も時間のかかった MV)")
    return {
        "n_refreshed": len(mv_names),
        "total_time": round(total_time, 2),
        "per_mv": per_mv,
    }


# ──────────────────────────────────────────────────────────────────────────────
# フルパイプライン実行
# ──────────────────────────────────────────────────────────────────────────────

def phase_measure_ivm_costs(qp, settings: Settings, top_k: int = 200) -> list[float]:
    """pg_ivm でサンプル IMMV を作成し実測 m_j を取得する。

    既存の qp.m_cost (theoretical) は変更しない。
    返り値を呼び出し元で qp.m_cost に上書きするかどうかは呼び出し元が判断する。

    Returns:
        actual_m_cost: len(qp.node_list) の float リスト。
                       計測失敗ノードは qp.m_cost[j] (理論値) のまま。
    """
    from src.maintenance import IVMCostEstimator
    estimator = IVMCostEstimator(settings, n_trials=10)
    return estimator.estimate_for_qp(qp, top_k=top_k)


def run_full_experiment(
    pkl_path: Path,
    output_dir: Path,
    b_max_mb: int = 50,
    algorithms: list[str] | None = None,
    settings: Optional[Settings] = None,
    sampling_costs_path: Optional[Path] = None,
    use_ivm_mj: bool = False,
    ivm_top_k: int = 200,
    use_immv: bool = False,
    run_update_bench: bool = False,
    update_n: int = 1000,
    skip_mv_creation: bool = False,
    query_timeout_minutes: int = 5,
    workload_type: str = "redbench-job",
):
    """bigsubs と topk-F のフルパイプラインを実行して結果を比較する.

    Args:
        pkl_path: QueryParser pickle のパス
        output_dir: 結果保存ディレクトリ (run_workload_benchmark が参照する基点)
        b_max_mb: ストレージ予算 (MB)
        algorithms: 実行するアルゴリズムのリスト。デフォルト ["bigsubs", "topkf"]
        settings: Settings オブジェクト (None なら自動生成)
        sampling_costs_path: simple_migration_costs.json のパス。
            None の場合はデフォルトパスを自動検索する。
        use_ivm_mj: True のとき pg_ivm でサンプル IMMV を作成して実測 m_j を使う。
            False のとき (デフォルト) は従来の theoretical m_j を使う。
        ivm_top_k: IVM 計測対象ノード数 (u_ij 上位 top_k ノードを計測)。
        use_immv: True のとき選択 MV を pg_ivm IMMV として作成する。
            IMMV は更新クエリ実行時にトリガーで自動更新されるため、
            update_bench の計測値にトリガー時間が含まれる。
        run_update_bench: True のとき update_n 件の更新クエリを実行して
            MV 維持コストを計測する。use_immv=False の場合は追加で全 MV を REFRESH する。
        update_n: 更新ベンチマークのクエリ件数 (default: 1000)。
    """
    if algorithms is None:
        algorithms = ["bigsubs", "topkf"]
    if settings is None:
        settings = Settings()

    b_max = float(b_max_mb * 1024 * 1024)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # run_workload_benchmark が rewritten SQL を探すパス:
    #   output_dir / "query_rewrite" / "re_sql" / {algo_label} / *.sql
    # algo_label = workload_runner が SQL を探すディレクトリ名
    # no_mv は "none" を使うと workload_runner がオリジナルクエリを参照する
    ALGO_LABEL = {
        "bigsubs": "bigsubs",
        "topkf": "frequency",
        "normal": "normal",
        "topku": "topku",
        "topke": "topke",
        "no_mv": "none",
    }

    # ─── pkl ロード ───
    logger.info(f"Loading pkl: {pkl_path}")
    with open(pkl_path, "rb") as f:
        qp = pickle.load(f)
    logger.info(f"  nodes={qp.s_num}, queries={len(qp.u_ij)}")

    # ─── ベーステーブルの統計精度を改善 (一度だけ実行) ───
    logger.info("[pre] ベーステーブル statistics_target=1000 設定 + ANALYZE...")
    update_base_table_statistics(settings, target=1000)

    # ─── sampling で b_j を補正 ───
    if sampling_costs_path is None:
        sampling_costs_path = (
            PROJECT_ROOT
            / "experiments/small_test_ver2/04_migration/job/simple_migration_costs.json"
        )
    logger.info(f"[pre] sampling 結果で b_j を補正: {sampling_costs_path}")
    apply_sampling_costs(qp, sampling_costs_path)

    # ─── (オプション) pg_ivm で実測 m_j を取得して理論値を上書き ───
    if use_ivm_mj:
        logger.info(f"[pre] pg_ivm で実測 m_j を計測 (top_k={ivm_top_k})...")
        t_ivm = time.time()
        actual_m_cost = phase_measure_ivm_costs(qp, settings, top_k=ivm_top_k)
        theoretical_m_cost = list(qp.m_cost)  # 理論値を退避
        qp.m_cost = actual_m_cost
        logger.info(
            f"  IVM 計測完了: {time.time() - t_ivm:.1f}s, "
            f"理論値との比較: "
            f"mean_theo={sum(theoretical_m_cost)/len(theoretical_m_cost):.4f}, "
            f"mean_actual={sum(actual_m_cost)/len(actual_m_cost):.4f}"
        )

    summaries = {}

    for algo in algorithms:
        label = ALGO_LABEL[algo]
        algo_dir = output_dir / label
        algo_dir.mkdir(parents=True, exist_ok=True)

        logger.info("")
        logger.info("=" * 65)
        logger.info(f"  アルゴリズム: {algo}  (B_max={b_max_mb}MB)")
        logger.info("=" * 65)

        phase_times = {}

        if algo == "no_mv":
            # ── no_mv ベースライン: MVなしでそのままワークロードを実行 ──
            logger.info("[0] 既存 MV を削除...")
            _drop_all_mvs(settings)
            logger.info("[1-4] MV なし (ベースライン): 最適化・MV作成・クエリ書き換えをスキップ")
            result = None
            mv_info = {"created": 0, "failed": 0, "immv_created": 0,
                       "regular_names": [], "immv_names": [], "indexes_created": 0, "total_time": 0}
            phase_times["optimization"] = 0.0
            phase_times["sql_generation"] = 0.0
            phase_times["mv_creation"] = 0.0
            # no_mv 用: JOB + CEB クエリを rewrite ディレクトリにコピー（他手法と同条件）
            import shutil as _shutil
            rewrite_out = output_dir / "query_rewrite" / "re_sql" / label
            rewrite_out.mkdir(parents=True, exist_ok=True)
            job_src = PROJECT_ROOT / "dataset" / "RED_SQL" / "job"
            for _f in job_src.glob("*.sql"):
                dst = rewrite_out / _f.name
                if not dst.exists():
                    _shutil.copy2(_f, dst)
            phase_copy_ceb_queries(rewrite_out)
            phase_times["query_rewriting"] = 0.0

        elif skip_mv_creation:
            # MV作成をスキップ: 既存のMV/IMMVとクエリ書き換えを再利用する
            logger.info("[0-4] MV作成・最適化・クエリ書き換えをスキップ (既存MVを使用)")
            # 最適化結果を保存済みJSONから復元
            from src.core.models import OptimizationResult
            opt_path = algo_dir / "optimization" / "result.json"
            result = OptimizationResult.load_from_json(str(opt_path))
            # MV作成ログを復元
            mv_log_path = algo_dir / "mv_creation" / "creation_log.json"
            if mv_log_path.exists():
                with open(mv_log_path) as f:
                    mv_info = json.load(f)
            else:
                mv_info = {"created": 0, "failed": 0, "immv_created": 0,
                           "regular_names": [], "immv_names": [], "indexes_created": 0, "total_time": 0}
        else:
            # ── 既存 MV を削除 ──
            logger.info("[0] 既存 MV を削除...")
            _drop_all_mvs(settings)

            # ── 最適化 ──
            logger.info("[1] 最適化...")
            t0 = time.time()
            result = phase_optimize(qp, algo, b_max, settings)
            phase_times["optimization"] = round(time.time() - t0, 2)
            logger.info(
                f"  選択 MV={len(result.selected_views)}, "
                f"utility={result.total_utility:.2f}, "
                f"storage={result.total_storage/1024/1024:.1f}MB, "
                f"time={phase_times['optimization']}s"
            )

            # 最適化結果を保存
            opt_dir = algo_dir / "optimization"
            opt_dir.mkdir(parents=True, exist_ok=True)
            result.save_to_json(str(opt_dir / "result.json"))

            # ── SQL 生成 ──
            logger.info("[2] MV SQL 生成...")
            t0 = time.time()
            phase_generate_sql(result, qp)
            phase_times["sql_generation"] = round(time.time() - t0, 2)

            # ── MV 作成 ──
            mv_label = "[3] MV 作成 (IMMV)..." if use_immv else "[3] MV 作成 (CREATE MATERIALIZED VIEW)..."
            logger.info(mv_label)
            t0 = time.time()
            mv_info = phase_create_mvs(result, qp, settings, use_immv=use_immv)
            phase_times["mv_creation"] = mv_info["total_time"]
            mv_log_dir = algo_dir / "mv_creation"
            mv_log_dir.mkdir(parents=True, exist_ok=True)
            with open(mv_log_dir / "creation_log.json", "w") as f:
                json.dump(mv_info, f, indent=2)

            # ── クエリ書き換え ──
            logger.info("[4] クエリ書き換え...")
            t0 = time.time()
            rewrite_out = output_dir / "query_rewrite" / "re_sql" / label
            n_rewritten = phase_rewrite_queries(result, settings, rewrite_out)
            if "ceb" in workload_type or workload_type == "redbench":
                phase_copy_ceb_queries(rewrite_out)
            phase_times["query_rewriting"] = round(time.time() - t0, 2)

        # ── ベンチマーク ──
        logger.info(f"[5] ベンチマーク実行 ({workload_type}, timeout={query_timeout_minutes}min)...")
        t0 = time.time()
        bench = phase_benchmark(label, output_dir, settings,
                                query_timeout_minutes=query_timeout_minutes,
                                workload_type=workload_type)
        phase_times["benchmark"] = round(time.time() - t0, 2)

        # ── 更新ベンチマーク (オプション) ──
        update_bench: dict = {}
        refresh_bench: dict = {}
        if run_update_bench:
            logger.info(f"[6] 更新ベンチマーク ({update_n} 件)...")
            t0 = time.time()
            update_bench = phase_update_benchmark(settings, n_updates=update_n)
            phase_times["update_benchmark"] = round(time.time() - t0, 2)

            if not use_immv and mv_info.get("regular_names"):
                logger.info(f"[7] REFRESH ベンチマーク ({len(mv_info['regular_names'])} MV)...")
                t0 = time.time()
                refresh_bench = phase_refresh_benchmark(mv_info["regular_names"], settings)
                phase_times["refresh_benchmark"] = round(time.time() - t0, 2)

        # 維持コスト合計 (read benchmark + update + refresh)
        read_time = bench.get("total_time", 0)
        update_time = update_bench.get("total_time", 0.0)
        refresh_time = refresh_bench.get("total_time", 0.0)
        total_maintenance = round(update_time + refresh_time, 2)
        combined_total = round(read_time + total_maintenance, 2)

        total_time = sum(phase_times.values())
        summary = {
            "algorithm": algo,
            "b_max_mb": b_max_mb,
            "use_immv": use_immv,
            "optimization": {
                "total_utility": result.total_utility if result is not None else 0,
                "num_selected_views": len(result.selected_views) if result is not None else 0,
                "total_storage_mb": round(result.total_storage / 1024 / 1024, 2) if result is not None else 0,
                "iterations": (result.metadata or {}).get("iterations") if result is not None else None,
            },
            "mv_creation": {
                "created": mv_info["created"],
                "failed": mv_info["failed"],
                "immv_created": mv_info.get("immv_created", 0),
                "regular_created": mv_info["created"] - mv_info.get("immv_created", 0),
            },
            "benchmark": {
                "total_queries": bench.get("total_queries", 0),
                "successful": bench.get("successful", 0),
                "total_time_sec": read_time,
                "avg_time_per_query_sec": bench.get("avg_time_per_query", 0),
            },
            "update_benchmark": update_bench,
            "refresh_benchmark": refresh_bench,
            "combined": {
                "read_time_sec": read_time,
                "update_time_sec": update_time,
                "refresh_time_sec": refresh_time,
                "total_maintenance_sec": total_maintenance,
                "combined_total_sec": combined_total,
            },
            "phase_times": phase_times,
            "total_pipeline_time_sec": round(total_time, 2),
        }
        summaries[algo] = summary

        with open(algo_dir / "summary.json", "w") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        logger.info(f"  Summary saved: {algo_dir / 'summary.json'}")

    # ── 比較レポート ──
    _print_comparison(summaries)

    comparison = {"b_max_mb": b_max_mb, "results": summaries}
    with open(output_dir / "comparison.json", "w") as f:
        json.dump(comparison, f, indent=2, ensure_ascii=False)
    logger.info(f"\n比較結果を保存: {output_dir / 'comparison.json'}")

    return summaries


def _print_comparison(summaries: dict):
    algos = list(summaries.keys())
    print("\n" + "=" * 72)
    print("実験結果比較 (Redbench-JOB ワークロード)")
    print("=" * 72)
    print(f"{'指標':<40} " + "".join(f"{a:>16}" for a in algos))
    print("-" * 72)

    def row(label, getter, fmt=".2f"):
        vals = []
        for a in algos:
            try:
                v = getter(summaries[a])
                vals.append(f"{v:{fmt}}" if v is not None else "  N/A")
            except Exception:
                vals.append("  N/A")
        print(f"{label:<40} " + "".join(f"{v:>16}" for v in vals))

    row("最適化利得 (Σ u_ij − Σ m_j)", lambda s: s["optimization"]["total_utility"])
    row("選択 MV 数", lambda s: s["optimization"]["num_selected_views"], "d")
    row("使用ストレージ (MB)", lambda s: s["optimization"]["total_storage_mb"])
    row("IMMV 作成数", lambda s: s["mv_creation"].get("immv_created", 0), "d")
    row("通常 MV 作成数", lambda s: s["mv_creation"].get("regular_created", s["mv_creation"]["created"]), "d")
    print("-" * 72)
    row("【読み取りクエリ】実行時間 (秒)", lambda s: s["benchmark"]["total_time_sec"])
    row("  クエリ平均時間 (秒)", lambda s: s["benchmark"]["avg_time_per_query_sec"])
    row("  総クエリ数", lambda s: s["benchmark"]["total_queries"], "d")
    print("-" * 72)
    row("【更新ベンチ】1000 更新合計 (秒)", lambda s: s["combined"]["update_time_sec"])
    row("  うち REFRESH 合計 (秒)", lambda s: s["combined"]["refresh_time_sec"])
    row("【合算】読み取り+維持コスト (秒)", lambda s: s["combined"]["combined_total_sec"])
    print("-" * 72)
    row("最適化時間 (秒)", lambda s: s["phase_times"]["optimization"])
    row("MV 作成時間 (秒)", lambda s: s["phase_times"]["mv_creation"])
    row("ベンチマーク時間 (秒)", lambda s: s["phase_times"]["benchmark"])
    row("パイプライン合計時間 (秒)", lambda s: s["total_pipeline_time_sec"])
    print("=" * 72)


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Redbench エンドツーエンド実験 (bigsubs vs topk-F)")
    parser.add_argument(
        "--pkl",
        default=str(PROJECT_ROOT / "Output/redbench_freq_v2/qp_class.pkl"),
        help="QueryParser pkl ファイル",
    )
    parser.add_argument("--b-max-mb", type=int, default=50, help="ストレージ予算 MB (default: 50)")
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "Output/redbench_edbt_result"),
        help="結果保存ディレクトリ",
    )
    parser.add_argument(
        "--algorithms", nargs="+",
        choices=["no_mv", "normal", "bigsubs", "topkf", "topku", "topke"],
        default=["bigsubs", "topkf"],
        help="実行するアルゴリズム",
    )
    parser.add_argument(
        "--sampling-costs",
        default=None,
        help="simple_migration_costs.json のパス（省略時はデフォルトパスを使用）",
    )
    parser.add_argument(
        "--use-ivm-mj",
        action="store_true",
        help="pg_ivm でサンプル IMMV を作成して実測 m_j を使う (デフォルト: 理論値)",
    )
    parser.add_argument(
        "--ivm-top-k",
        type=int,
        default=200,
        help="IVM 計測対象ノード数 (u_ij 上位 top_k, default: 200)",
    )
    parser.add_argument(
        "--use-immv",
        action="store_true",
        help="選択した MV を pg_ivm IMMV として作成する（更新時にトリガーで自動更新）",
    )
    parser.add_argument(
        "--run-update-bench",
        action="store_true",
        help="更新ベンチマークを実行する（--update-n 件の更新クエリ + REFRESH 計測）",
    )
    parser.add_argument(
        "--update-n",
        type=int,
        default=1000,
        help="更新ベンチマークのクエリ件数 (default: 1000)",
    )
    parser.add_argument(
        "--skip-mv-creation",
        action="store_true",
        help="MV作成・最適化・クエリ書き換えをスキップして既存MVを再利用する",
    )
    parser.add_argument(
        "--query-timeout-minutes",
        type=int,
        default=5,
        help="各クエリのタイムアウト時間（分）(default: 5)",
    )
    parser.add_argument(
        "--workload-type",
        default="redbench",
        choices=["redbench", "redbench-job", "redbench-ceb"],
        help="実行するワークロード種別 (default: redbench = JOB+CEB両方)",
    )
    args = parser.parse_args()

    run_full_experiment(
        pkl_path=Path(args.pkl),
        output_dir=Path(args.output_dir),
        b_max_mb=args.b_max_mb,
        algorithms=args.algorithms,
        sampling_costs_path=Path(args.sampling_costs) if args.sampling_costs else None,
        use_ivm_mj=args.use_ivm_mj,
        ivm_top_k=args.ivm_top_k,
        use_immv=args.use_immv,
        run_update_bench=args.run_update_bench,
        update_n=args.update_n,
        skip_mv_creation=args.skip_mv_creation,
        query_timeout_minutes=args.query_timeout_minutes,
        workload_type=args.workload_type,
    )


if __name__ == "__main__":
    main()
