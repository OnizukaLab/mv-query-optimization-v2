"""v10 bigsubs & topkf の IVM m_j 計測 → 更新コスト推定.

1% サンプルIMMVを作成し BEGIN→UPDATE→ROLLBACK で IVM トリガー時間を計測。
full-size にスケールして m_j (秒/更新) を得る。
total_maintenance = Σ_j (m_j × N_updates_for_table_j) で推定。
"""
from __future__ import annotations

import json
import logging
import pickle
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Optional

import psycopg2

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import Settings
from src.maintenance.mv_sql_expander import expand_mv_sql
from src.maintenance.update_workload import _SAFE_UPDATE_TEMPLATES, UpdateWorkload

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── 設定 ──────────────────────────────────────────────────────────
TARGET_TABLES = ["cast_info", "name"]          # 対象ベーステーブル
N_UPDATES = {"cast_info": 220, "name": 60}     # v9_ivm で使った更新回数
N_TRIALS = 5
WARMUP_TRIALS = 2
SAMPLING_RATE = 0.01
SAMPLE_PREFIX = "_mj_s_"

# ── DB 接続 ────────────────────────────────────────────────────────

def connect(settings) -> psycopg2.extensions.connection:
    s = settings.database
    conn = psycopg2.connect(
        host=s.host, port=s.port, dbname=s.database,
        user=s.user, password=s.password,
    )
    conn.autocommit = False
    return conn


# ── サンプルテーブル管理 ───────────────────────────────────────────

def create_sample_tables(conn, tables: list[str]) -> dict[str, str]:
    mapping = {}
    for tbl in tables:
        sample = SAMPLE_PREFIX + tbl
        try:
            with conn.cursor() as cur:
                cur.execute(f"DROP TABLE IF EXISTS {sample} CASCADE")
                cur.execute(
                    f"CREATE UNLOGGED TABLE {sample} AS "
                    f"SELECT * FROM {tbl} TABLESAMPLE BERNOULLI({SAMPLING_RATE * 100})"
                )
            conn.commit()
            mapping[tbl] = sample
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {sample}")
                n = cur.fetchone()[0]
            logger.info(f"  sample {sample}: {n} rows")
        except Exception as e:
            conn.rollback()
            logger.warning(f"  sample {tbl} 失敗: {e}")
    return mapping


def drop_sample_tables(conn, mapping: dict[str, str]):
    for sample in mapping.values():
        try:
            with conn.cursor() as cur:
                cur.execute(f"DROP TABLE IF EXISTS {sample} CASCADE")
            conn.commit()
        except Exception:
            conn.rollback()


# ── IMMV 作成 + 計測 ──────────────────────────────────────────────

def rename_tables(sql: str, mapping: dict[str, str]) -> str:
    """SQL 中のベーステーブル名をサンプルテーブル名に置換（FROM/JOIN文脈のみ）."""
    return UpdateWorkload.rename_sql_tables(sql, mapping)


def get_mv_sql(node_id: str, plans: dict) -> Optional[str]:
    """expand_mv_sql で CTE 展開済み SELECT 本体を取得."""
    return expand_mv_sql(node_id, plans)


def which_tables(sql: str, tables: list[str]) -> list[str]:
    """SQL の FROM/JOIN 句に登場するテーブルのうち、tables の中に含まれるものを返す."""
    found = []
    for t in tables:
        # FROM/JOIN/カンマ直後のテーブル参照のみを対象とする
        pattern = r'(?:FROM|JOIN|,)\s+' + re.escape(t) + r'\b'
        if re.search(pattern, sql, re.IGNORECASE):
            found.append(t)
    return found


def measure_mj(
    conn,
    node_id: str,
    update_table: str,
    mv_sql: str,
    sample_mapping: dict[str, str],
    full_size: int,
) -> Optional[float]:
    """サンプルIMMV 上でトリガー時間を計測し、full-size スケールの m_j (秒) を返す."""
    safe = re.sub(r'[^a-z0-9]', '', node_id.lower())
    immv_name = SAMPLE_PREFIX + safe

    tmpl = _SAFE_UPDATE_TEMPLATES.get(update_table)
    if tmpl is None:
        return None

    sample_sql = rename_tables(mv_sql, sample_mapping)
    sample_tbl = sample_mapping[update_table]

    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {immv_name} CASCADE")
            cur.execute("SELECT pgivm.create_immv(%s, %s)", (immv_name, sample_sql))
            cur.fetchone()
            cur.execute(f"SELECT COUNT(*) FROM {immv_name}")
            sample_mv_size = cur.fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.debug(f"    IMMV作成失敗 {node_id}: {str(e)[:80]}")
        return None

    times = []
    for trial in range(N_TRIALS + WARMUP_TRIALS):
        sql = tmpl.format(table=sample_tbl, offset=trial * 50)
        try:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                t0 = time.perf_counter()
                cur.execute(sql)
                elapsed = time.perf_counter() - t0
                cur.execute("ROLLBACK")
            conn.rollback()
            if trial >= WARMUP_TRIALS:
                times.append(elapsed)
        except Exception:
            conn.rollback()

    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {immv_name} CASCADE")
        conn.commit()
    except Exception:
        conn.rollback()

    if not times:
        return None

    median_t = statistics.median(times)
    # 1%サンプル → full-size スケールアップ
    scale = 1.0 / SAMPLING_RATE
    return median_t * scale


def get_full_size(conn, table_name: str) -> int:
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT reltuples::bigint FROM pg_class WHERE relname = %s",
                (table_name,)
            )
            row = cur.fetchone()
            return max(1, int(row[0])) if row else 1
    except Exception:
        return 1


# ── メイン ────────────────────────────────────────────────────────

def measure_algo(algo_label: str, mv_names: list[str], conn, plans: dict, full_sizes: dict) -> dict:
    """bigsubs or topkf の全選択MVに対して m_j を計測."""
    logger.info(f"=== {algo_label}: {len(mv_names)} MVs ===")

    # サンプルテーブル作成（計測対象テーブルのみ）
    logger.info("  サンプルテーブル作成...")
    # すべてのIMDBテーブルのサンプルが必要（MVがjoinするため）
    all_tables = [
        "cast_info", "name", "movie_info", "title", "movie_keyword",
        "movie_companies", "person_info", "info_type", "company_name",
        "company_type", "keyword", "role_type", "char_name",
    ]
    sample_mapping = create_sample_tables(conn, all_tables)

    results = {}  # {mv_name: {table: m_j_sec}}

    for i, mv_name in enumerate(mv_names, 1):
        node_id = mv_name  # MV名 = ノードID
        mv_sql = get_mv_sql(node_id, plans)
        if mv_sql is None:
            logger.debug(f"  [{i}/{len(mv_names)}] {mv_name}: SQL取得失敗 (スキップ)")
            continue

        # このMVが依存するターゲットテーブルを特定
        deps = which_tables(mv_sql, TARGET_TABLES)
        if not deps:
            continue

        mv_result = {}
        for tbl in deps:
            if tbl not in sample_mapping:
                continue
            full_sz = full_sizes.get(tbl, 1)
            mj = measure_mj(conn, node_id, tbl, mv_sql, sample_mapping, full_sz)
            if mj is not None:
                mv_result[tbl] = round(mj, 4)

        if mv_result:
            results[mv_name] = mv_result
            if i % 10 == 0:
                logger.info(f"  [{i}/{len(mv_names)}] 計測済み: {len(results)} MVs")

    drop_sample_tables(conn, sample_mapping)
    logger.info(f"  計測完了: {len(results)} / {len(mv_names)} MVs")
    return results


def estimate_cost(mj_results: dict, n_updates: dict) -> dict:
    """m_j × N_updates で更新コスト合計を推定."""
    per_table: dict[str, dict] = {t: {"n_updates": n, "mj_sum": 0.0, "n_mvs": 0} for t, n in n_updates.items()}

    for mv_name, table_mj in mj_results.items():
        for tbl, mj in table_mj.items():
            if tbl in per_table:
                per_table[tbl]["mj_sum"] += mj
                per_table[tbl]["n_mvs"] += 1

    total = 0.0
    for tbl, d in per_table.items():
        cost = d["mj_sum"] * d["n_updates"]
        d["total_sec"] = round(cost, 2)
        d["avg_mj_sec"] = round(d["mj_sum"] / d["n_mvs"], 4) if d["n_mvs"] > 0 else 0
        total += cost

    return {"per_table": per_table, "total_maintenance_sec": round(total, 2)}


def main():
    settings = Settings()
    output_dir = PROJECT_ROOT / "Output" / "redbench_edbt_v10_ceb"

    # plans ロード
    plans_path = (PROJECT_ROOT /
        "experiments/small_test_ver2/04_migration/job/simple_migration_plans.json")
    with open(plans_path) as f:
        plans = json.load(f)

    # v10 bigsubs & topkf の選択MV名を取得
    bigsubs_log = json.load(open(output_dir / "bigsubs" / "mv_creation" / "creation_log.json"))
    topkf_log   = json.load(open(output_dir / "frequency" / "mv_creation" / "creation_log.json"))
    bigsubs_mvs = sorted(bigsubs_log["regular_names"])
    topkf_mvs   = sorted(topkf_log["regular_names"])

    conn = connect(settings)
    full_sizes = {t: get_full_size(conn, t) for t in TARGET_TABLES}
    logger.info(f"full_sizes: {full_sizes}")

    # bigsubs 計測
    bigsubs_mj = measure_algo("bigsubs", bigsubs_mvs, conn, plans, full_sizes)
    bigsubs_cost = estimate_cost(bigsubs_mj, N_UPDATES)

    # topkf 計測
    topkf_mj = measure_algo("topkf", topkf_mvs, conn, plans, full_sizes)
    topkf_cost = estimate_cost(topkf_mj, N_UPDATES)

    conn.close()

    # 結果まとめ
    query_bigsubs = 709.09
    query_topkf   = 865.37

    output = {
        "n_updates": N_UPDATES,
        "bigsubs": {
            "mv_count": len(bigsubs_mvs),
            "measured_mvs": len(bigsubs_mj),
            "mj_per_mv": bigsubs_mj,
            "estimated_maintenance": bigsubs_cost,
            "query_time_sec": query_bigsubs,
            "combined_sec": round(query_bigsubs + bigsubs_cost["total_maintenance_sec"], 2),
        },
        "topkf": {
            "mv_count": len(topkf_mvs),
            "measured_mvs": len(topkf_mj),
            "mj_per_mv": topkf_mj,
            "estimated_maintenance": topkf_cost,
            "query_time_sec": query_topkf,
            "combined_sec": round(query_topkf + topkf_cost["total_maintenance_sec"], 2),
        },
    }

    out_path = output_dir / "mj_maintenance_estimate.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    logger.info("=" * 60)
    logger.info(f"bigsubs: query={query_bigsubs}s + maintenance={bigsubs_cost['total_maintenance_sec']}s = {output['bigsubs']['combined_sec']}s")
    logger.info(f"topkf:   query={query_topkf}s + maintenance={topkf_cost['total_maintenance_sec']}s = {output['topkf']['combined_sec']}s")
    logger.info(f"結果保存: {out_path}")


if __name__ == "__main__":
    main()
