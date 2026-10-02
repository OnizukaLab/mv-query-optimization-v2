"""v13 実験: m_cost 削除済み BIGSUBS vs topkf/normal の比較.

変更点:
  - BIGSUBS: src/optimization/bigsubs.py から m_cost を削除済み（純粋に query utility を最大化）
  - topkf/normal: 従来どおり m_cost を目的関数に含む
  - 評価: m_j は C=1（×100 スケールなし）で推定

目的:
  m_cost を無視した BIGSUBS が更新コストの高い MV を選択するかどうかを確認。
  combined time (query + maintenance) で比較して BIGSUBS の劣性を示す。

実行:
    python scripts/run_v13_bigsubs_no_mcost.py

所要時間: 最適化 × 3 + クエリベンチマーク × 3 ≈ 2〜3 時間
"""
from __future__ import annotations

import json
import logging
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PKL_PATH   = PROJECT_ROOT / "Output/redbench_freq_v2/qp_class.pkl"
OUTPUT_DIR = PROJECT_ROOT / "Output/redbench_edbt_v13_bigsubs_no_mcost"
B_MAX_MB   = 50
ALGORITHMS = ["bigsubs", "topkf", "normal"]

# 更新ワークロード設定 (C=1 モデル: シリアル上界)
N_UPDATES  = {"cast_info": 220, "name": 60}


def run_maintenance_measurement(output_dir: Path, algorithms: list[str]) -> dict:
    """v11 measure_v11_mj.py と同等の m_j 計測 (C=1: スケールなし)."""
    import re
    import psycopg2

    from config.settings import Settings
    from src.maintenance.mv_sql_expander import expand_mv_sql
    from src.maintenance.update_workload import _SAFE_UPDATE_TEMPLATES, UpdateWorkload

    SAMPLING_RATE = 0.01
    SAMPLE_PREFIX = "_v13mj_s_"
    N_TRIALS = 5
    WARMUP_TRIALS = 2
    TARGET_TABLES = list(N_UPDATES.keys())
    ALL_TABLES = [
        "cast_info", "name", "movie_info", "title", "movie_keyword",
        "movie_companies", "person_info", "info_type", "company_name",
        "company_type", "keyword", "role_type", "char_name",
    ]
    ALGO_LABEL = {
        "bigsubs": "bigsubs",
        "topkf": "frequency",
        "normal": "normal",
    }

    plans_path = (
        PROJECT_ROOT
        / "experiments/small_test_ver2/04_migration/job/simple_migration_plans.json"
    )
    with open(plans_path) as f:
        plans = json.load(f)

    settings = Settings()
    s = settings.database
    conn = psycopg2.connect(
        host=s.host, port=s.port, dbname=s.database,
        user=s.user, password=s.password,
    )
    conn.autocommit = False

    def which_tables(sql):
        found = []
        for t in TARGET_TABLES:
            if re.search(r'(?:FROM|JOIN|,)\s+' + re.escape(t) + r'\b', sql, re.IGNORECASE):
                found.append(t)
        return found

    def create_samples():
        mapping = {}
        for tbl in ALL_TABLES:
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
            except Exception as e:
                conn.rollback()
                logger.warning(f"  sample {tbl} 失敗: {e}")
        return mapping

    def drop_samples(mapping):
        for sample in mapping.values():
            try:
                with conn.cursor() as cur:
                    cur.execute(f"DROP TABLE IF EXISTS {sample} CASCADE")
                conn.commit()
            except Exception:
                conn.rollback()

    def measure_one(node_id, update_table, mv_sql, sample_mapping):
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
        # C=1: IVM delta cost does not scale with base table size
        return statistics.median(times)

    mj_results_all = {}
    for algo in algorithms:
        label = ALGO_LABEL[algo]
        log_path = output_dir / label / "mv_creation" / "creation_log.json"
        if not log_path.exists():
            logger.warning(f"{algo}: creation_log.json not found, skipping")
            continue

        mv_log = json.load(open(log_path))
        mv_names = sorted(mv_log["regular_names"])
        logger.info(f"=== {algo}: {len(mv_names)} MVs ===")
        sample_mapping = create_samples()

        mv_results = {}
        for i, mv_name in enumerate(mv_names, 1):
            mv_sql = expand_mv_sql(mv_name, plans)
            if mv_sql is None:
                continue
            deps = which_tables(mv_sql)
            if not deps:
                continue
            mv_result = {}
            for tbl in deps:
                if tbl not in sample_mapping:
                    continue
                mj = measure_one(mv_name, tbl, mv_sql, sample_mapping)
                if mj is not None:
                    mv_result[tbl] = round(mj, 6)
            if mv_result:
                mv_results[mv_name] = mv_result
            if i % 20 == 0:
                logger.info(f"  [{i}/{len(mv_names)}] 計測済み: {len(mv_results)} MVs")

        drop_samples(sample_mapping)
        mj_results_all[algo] = mv_results
        logger.info(f"  {algo}: {len(mv_results)} MVs 計測完了")

    conn.close()
    return mj_results_all


def compute_combined(output_dir: Path, mj_results_all: dict, n_updates: dict) -> dict:
    ALGO_LABEL = {"bigsubs": "bigsubs", "topkf": "frequency", "normal": "normal"}
    out = {}
    for algo, mv_results in mj_results_all.items():
        label = ALGO_LABEL[algo]
        summary_path = output_dir / label / "summary.json"
        query_time = 0.0
        mv_count = 0
        if summary_path.exists():
            s = json.load(open(summary_path))
            query_time = s["benchmark"]["total_time_sec"]
            mv_count = s["optimization"]["num_selected_views"]

        # total_maintenance = Σ over table: (Σ m_j for MVs using that table) × N_updates
        per_table: dict[str, float] = {t: 0.0 for t in n_updates}
        for mv_name, tbl_mj in mv_results.items():
            for tbl, mj in tbl_mj.items():
                if tbl in per_table:
                    per_table[tbl] += mj

        total_maint = sum(per_table[t] * n_updates[t] for t in n_updates)
        out[algo] = {
            "mv_count": mv_count,
            "measured_mvs": len(mv_results),
            "query_time_sec": round(query_time, 2),
            "maintenance_sec": round(total_maint, 2),
            "combined_sec": round(query_time + total_maint, 2),
            "per_table_mj_sum": {t: round(per_table[t], 6) for t in n_updates},
        }
    return out


def main():
    from src.runners.redbench_experiment import run_full_experiment

    logger.info("=" * 65)
    logger.info("v13 実験: BIGSUBS(no m_cost) vs topkf/normal")
    logger.info("=" * 65)

    # Phase 1: 最適化 + クエリベンチマーク
    logger.info("\n[Phase 1] 最適化 + クエリベンチマーク")
    run_full_experiment(
        pkl_path=PKL_PATH,
        output_dir=OUTPUT_DIR,
        b_max_mb=B_MAX_MB,
        algorithms=ALGORITHMS,
        workload_type="redbench",
    )

    # Phase 2: m_j 計測 (C=1)
    logger.info("\n[Phase 2] m_j 計測 (C=1, スケールなし)")
    mj_results = run_maintenance_measurement(OUTPUT_DIR, ALGORITHMS)

    # Phase 3: combined time 集計
    logger.info("\n[Phase 3] combined time 集計")
    results = compute_combined(OUTPUT_DIR, mj_results, N_UPDATES)

    # 結果保存
    out_path = OUTPUT_DIR / "v13_combined_summary.json"
    with open(out_path, "w") as f:
        json.dump({"n_updates": N_UPDATES, "c_factor": 1, "algorithms": results}, f, indent=2)

    # 表示
    logger.info("\n" + "=" * 65)
    logger.info(f"{'Algo':<10} {'MVs':>5} {'query(s)':>10} {'maint(s)':>10} {'combined(s)':>12}")
    logger.info("-" * 50)
    for algo, v in results.items():
        logger.info(
            f"{algo:<10} {v['mv_count']:>5} {v['query_time_sec']:>10.1f}"
            f" {v['maintenance_sec']:>10.1f} {v['combined_sec']:>12.1f}"
        )
    logger.info(f"\n結果保存: {out_path}")


if __name__ == "__main__":
    main()
