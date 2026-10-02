"""v11 全アルゴリズム (normal/bigsubs/topkf/topku/topke) の IVM m_j 計測 → 更新コスト推定.

1% サンプルIMMVを作成し BEGIN→UPDATE→ROLLBACK で IVM トリガー時間を計測。
full-size にスケールして m_j (秒/更新) を得る。
total_maintenance = Σ_j (m_j × N_updates_for_table_j) で推定。
"""
from __future__ import annotations

import json
import logging
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

TARGET_TABLES = ["cast_info", "name"]
N_UPDATES = {"cast_info": 220, "name": 60}
N_TRIALS = 5
WARMUP_TRIALS = 2
SAMPLING_RATE = 0.01
SAMPLE_PREFIX = "_mj_s_"

ALL_TABLES = [
    "cast_info", "name", "movie_info", "title", "movie_keyword",
    "movie_companies", "person_info", "info_type", "company_name",
    "company_type", "keyword", "role_type", "char_name",
]

ALGO_LABEL = {
    "normal": "normal",
    "bigsubs": "bigsubs",
    "topkf": "frequency",
    "topku": "topku",
    "topke": "topke",
}


def connect(settings) -> psycopg2.extensions.connection:
    s = settings.database
    conn = psycopg2.connect(
        host=s.host, port=s.port, dbname=s.database,
        user=s.user, password=s.password,
    )
    conn.autocommit = False
    return conn


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


def which_tables(sql: str, tables: list[str]) -> list[str]:
    found = []
    for t in tables:
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
) -> Optional[float]:
    safe = re.sub(r'[^a-z0-9]', '', node_id.lower())
    immv_name = SAMPLE_PREFIX + safe

    tmpl = _SAFE_UPDATE_TEMPLATES.get(update_table)
    if tmpl is None:
        return None

    sample_sql = UpdateWorkload.rename_sql_tables(mv_sql, sample_mapping)
    sample_tbl = sample_mapping[update_table]

    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {immv_name} CASCADE")
            cur.execute("SELECT pgivm.create_immv(%s, %s)", (immv_name, sample_sql))
            cur.fetchone()
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

    # C=1: IVM delta cost is independent of base table size (other tables are at full size).
    # Scaling by 1/SAMPLING_RATE would overestimate by ~100×.
    # Limitation: actual lock contention may increase real cost; noted as future work.
    return statistics.median(times)


def measure_algo(algo: str, mv_names: list[str], conn, plans: dict) -> dict:
    logger.info(f"=== {algo}: {len(mv_names)} MVs ===")
    logger.info("  サンプルテーブル作成...")
    sample_mapping = create_sample_tables(conn, ALL_TABLES)

    results = {}
    for i, mv_name in enumerate(mv_names, 1):
        mv_sql = expand_mv_sql(mv_name, plans)
        if mv_sql is None:
            continue

        deps = which_tables(mv_sql, TARGET_TABLES)
        if not deps:
            continue

        mv_result = {}
        for tbl in deps:
            if tbl not in sample_mapping:
                continue
            mj = measure_mj(conn, mv_name, tbl, mv_sql, sample_mapping)
            if mj is not None:
                mv_result[tbl] = round(mj, 4)

        if mv_result:
            results[mv_name] = mv_result
            if i % 20 == 0 or i == len(mv_names):
                logger.info(f"  [{i}/{len(mv_names)}] 計測済み: {len(results)} MVs")

    drop_sample_tables(conn, sample_mapping)
    logger.info(f"  計測完了: {len(results)} / {len(mv_names)} MVs")
    return results


def estimate_cost(mj_results: dict, n_updates: dict) -> dict:
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
        d["avg_mj_sec"] = round(d["mj_sum"] / d["n_mvs"], 4) if d["n_mvs"] > 0 else 0.0
        total += cost

    return {"per_table": per_table, "total_maintenance_sec": round(total, 2)}


def main():
    settings = Settings()
    output_dir = PROJECT_ROOT / "Output" / "redbench_edbt_v11_all"

    plans_path = (PROJECT_ROOT /
        "experiments/small_test_ver2/04_migration/job/simple_migration_plans.json")
    with open(plans_path) as f:
        plans = json.load(f)

    conn = connect(settings)

    output = {"n_updates": N_UPDATES, "algorithms": {}}

    for algo, label in ALGO_LABEL.items():
        log_path = output_dir / label / "mv_creation" / "creation_log.json"
        if not log_path.exists():
            logger.warning(f"{algo}: creation_log.json not found, skipping")
            continue

        mv_log = json.load(open(log_path))
        mv_names = sorted(mv_log["regular_names"])

        mj_results = measure_algo(algo, mv_names, conn, plans)
        cost = estimate_cost(mj_results, N_UPDATES)

        # query time from summary.json
        summary_path = output_dir / label / "summary.json"
        query_time = 0.0
        if summary_path.exists():
            s = json.load(open(summary_path))
            query_time = s["benchmark"]["total_time_sec"]

        output["algorithms"][algo] = {
            "label": label,
            "mv_count": len(mv_names),
            "measured_mvs": len(mj_results),
            "mj_per_mv": mj_results,
            "estimated_maintenance": cost,
            "query_time_sec": query_time,
            "combined_sec": round(query_time + cost["total_maintenance_sec"], 2),
        }

        logger.info(
            f"  {algo}: query={query_time:.2f}s + maintenance={cost['total_maintenance_sec']:.2f}s"
            f" = {output['algorithms'][algo]['combined_sec']:.2f}s"
        )

    conn.close()

    out_path = output_dir / "mj_maintenance_estimate.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    logger.info(f"\n結果保存: {out_path}")
    logger.info("=" * 60)
    for algo, d in output["algorithms"].items():
        logger.info(
            f"  {algo:8s}: query={d['query_time_sec']:.2f}s"
            f" + maint={d['estimated_maintenance']['total_maintenance_sec']:.2f}s"
            f" = combined={d['combined_sec']:.2f}s"
        )


if __name__ == "__main__":
    main()
