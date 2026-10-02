"""v10 bigsubs & topkf のREFRESH時間計測 + 更新コスト推定.

topkf MVは現在DBに存在。bigsubs MVは再作成→計測→削除する。
MV-テーブル依存関係を分析し、更新回数ごとのREFRESHコストを推定する。
"""
from __future__ import annotations

import json
import logging
import pickle
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import Settings
from src.runners.redbench_experiment import (
    phase_generate_sql,
    phase_create_mvs,
    phase_refresh_benchmark,
    _drop_all_mvs,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASE_TABLES = ["cast_info", "name", "movie_info", "title", "movie_keyword",
               "movie_companies", "person_info", "info_type", "company_name",
               "company_type", "keyword", "role_type", "char_name", "aka_name"]

# v9_ivm の更新ベンチマークで使われた更新回数
UPDATE_COUNTS = {
    "cast_info": 220,
    "name": 60,
}


def get_mv_table_deps(mv_names: list[str], settings: Settings) -> dict[str, list[str]]:
    """各MVが依存するベーステーブルを pg_get_viewdef で取得."""
    from src.database.connection import DatabaseConnection

    db = DatabaseConnection(settings.database)
    deps: dict[str, list[str]] = {}

    for mv_name in mv_names:
        try:
            db.cursor.execute(
                "SELECT pg_get_viewdef(%s::regclass, true)", (mv_name,)
            )
            row = db.cursor.fetchone()
            if not row:
                deps[mv_name] = []
                continue
            viewdef = row[0]
            # SQL中に出現するベーステーブル名を抽出
            found = []
            for tbl in BASE_TABLES:
                pattern = r'\b' + re.escape(tbl) + r'\b'
                if re.search(pattern, viewdef, re.IGNORECASE):
                    found.append(tbl)
            deps[mv_name] = found
        except Exception as e:
            logger.warning(f"  {mv_name} viewdef 取得失敗: {e}")
            deps[mv_name] = []

    db.close()
    return deps


def estimate_refresh_cost(
    per_mv_times: dict[str, float],
    mv_table_deps: dict[str, list[str]],
    update_counts: dict[str, int],
) -> dict:
    """更新クエリ × 依存MV のREFRESHコスト推定.

    Returns:
        per_table: テーブルごとの推定REFRESHコスト
        total_refresh_cost: 全テーブル合計
        n_updates_total: 総更新回数
    """
    per_table = {}
    for table, n_updates in update_counts.items():
        affected_mvs = [mv for mv, deps in mv_table_deps.items() if table in deps]
        refresh_per_update = sum(per_mv_times.get(mv, 0.0) for mv in affected_mvs)
        total = refresh_per_update * n_updates
        per_table[table] = {
            "n_updates": n_updates,
            "affected_mvs": len(affected_mvs),
            "refresh_per_update_sec": round(refresh_per_update, 3),
            "total_refresh_sec": round(total, 3),
        }

    total_refresh = sum(v["total_refresh_sec"] for v in per_table.values())
    return {
        "per_table": per_table,
        "total_refresh_cost_sec": round(total_refresh, 2),
        "n_updates_total": sum(update_counts.values()),
    }


def main():
    settings = Settings()
    output_dir = PROJECT_ROOT / "Output" / "redbench_edbt_v10_ceb"
    results_path = output_dir / "refresh_benchmark_v10.json"

    # ──────────────────────────────────────────────────────────
    # 1. topkf: 現在DBにある96MV のREFRESH計測
    # ──────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("Phase 1: topkf REFRESH benchmark (96 MVs in DB)")
    logger.info("=" * 60)

    topkf_log = json.load(
        open(output_dir / "frequency" / "mv_creation" / "creation_log.json")
    )
    topkf_mv_names = sorted(topkf_log["regular_names"])

    topkf_refresh = phase_refresh_benchmark(topkf_mv_names, settings)
    logger.info(f"topkf REFRESH: total={topkf_refresh['total_time']:.2f}s")

    topkf_deps = get_mv_table_deps(topkf_mv_names, settings)
    topkf_cost = estimate_refresh_cost(
        topkf_refresh["per_mv"], topkf_deps, UPDATE_COUNTS
    )
    logger.info(f"topkf estimated refresh cost: {topkf_cost['total_refresh_cost_sec']:.2f}s")

    # ──────────────────────────────────────────────────────────
    # 2. bigsubs: MVを再作成 → REFRESH計測 → 削除
    # ──────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("Phase 2: bigsubs — recreate MVs, measure REFRESH, drop")
    logger.info("=" * 60)

    # topkf MVを削除してbigsubs MVを再作成
    logger.info("  既存MV (topkf) を削除...")
    _drop_all_mvs(settings)

    # qp_class.pkl を読み込み
    pkl_path = PROJECT_ROOT / "Output" / "redbench_freq_v2" / "qp_class.pkl"
    logger.info(f"  pkl読み込み: {pkl_path}")
    with open(pkl_path, "rb") as f:
        qp = pickle.load(f)

    # bigsubs optimization resultを読み込み
    bigsubs_result_path = output_dir / "bigsubs" / "optimization" / "result.json"
    bigsubs_result_data = json.load(open(bigsubs_result_path))

    # result.jsonをMVオブジェクトに変換（qpからノードを取得してSQL生成）
    from src.utils.result_builder import ExperimentResult
    result = ExperimentResult.from_dict(bigsubs_result_data, qp)

    logger.info("  SQL生成中...")
    phase_generate_sql(result, qp)

    logger.info("  MV作成中...")
    mv_info = phase_create_mvs(result, qp, settings, use_immv=False)
    bigsubs_mv_names = sorted(mv_info["regular_names"])
    logger.info(f"  作成完了: {len(bigsubs_mv_names)} MVs")

    bigsubs_refresh = phase_refresh_benchmark(bigsubs_mv_names, settings)
    logger.info(f"bigsubs REFRESH: total={bigsubs_refresh['total_time']:.2f}s")

    bigsubs_deps = get_mv_table_deps(bigsubs_mv_names, settings)
    bigsubs_cost = estimate_refresh_cost(
        bigsubs_refresh["per_mv"], bigsubs_deps, UPDATE_COUNTS
    )
    logger.info(f"bigsubs estimated refresh cost: {bigsubs_cost['total_refresh_cost_sec']:.2f}s")

    # bigsubs MVを削除
    logger.info("  bigsubs MVを削除...")
    _drop_all_mvs(settings)

    # ──────────────────────────────────────────────────────────
    # 3. 結果をまとめて保存
    # ──────────────────────────────────────────────────────────
    query_time_bigsubs = 709.09
    query_time_topkf = 865.37

    output = {
        "update_counts": UPDATE_COUNTS,
        "bigsubs": {
            "mv_count": len(bigsubs_mv_names),
            "refresh_benchmark": bigsubs_refresh,
            "mv_table_deps_summary": {
                tbl: sum(1 for deps in bigsubs_deps.values() if tbl in deps)
                for tbl in UPDATE_COUNTS
            },
            "estimated_refresh_cost": bigsubs_cost,
            "query_time_sec": query_time_bigsubs,
            "combined_time_sec": round(query_time_bigsubs + bigsubs_cost["total_refresh_cost_sec"], 2),
        },
        "topkf": {
            "mv_count": len(topkf_mv_names),
            "refresh_benchmark": topkf_refresh,
            "mv_table_deps_summary": {
                tbl: sum(1 for deps in topkf_deps.values() if tbl in deps)
                for tbl in UPDATE_COUNTS
            },
            "estimated_refresh_cost": topkf_cost,
            "query_time_sec": query_time_topkf,
            "combined_time_sec": round(query_time_topkf + topkf_cost["total_refresh_cost_sec"], 2),
        },
    }

    with open(results_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    logger.info("=" * 60)
    logger.info(f"結果保存: {results_path}")
    logger.info("=" * 60)
    logger.info(f"  bigsubs: query={query_time_bigsubs}s + refresh={bigsubs_cost['total_refresh_cost_sec']}s = combined={output['bigsubs']['combined_time_sec']}s")
    logger.info(f"  topkf:   query={query_time_topkf}s + refresh={topkf_cost['total_refresh_cost_sec']}s = combined={output['topkf']['combined_time_sec']}s")


if __name__ == "__main__":
    main()
