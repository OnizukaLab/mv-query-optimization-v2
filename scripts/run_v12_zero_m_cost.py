"""v12 実験: insert_query=0 (m_cost=0) での bigsubs vs topk-f 比較.

目的:
  m_cost=0 にしても BIGSUBS が topk-f より速い場合、
  EXPLAIN ベースの utility は実際の実行時間短縮と比例しない
  ことを直接示す（スケール問題とは独立した証拠）。

実行:
    python scripts/run_v12_zero_m_cost.py
"""
from __future__ import annotations

import logging
import pickle
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PKL_PATH   = PROJECT_ROOT / "Output/redbench_freq_v2/qp_class.pkl"
OUTPUT_DIR = PROJECT_ROOT / "Output/redbench_edbt_v12_zero_m_cost"
B_MAX_MB   = 50
ALGORITHMS = ["bigsubs", "topkf"]

def main():
    # pkl をロードして m_cost をゼロに上書き
    logger.info(f"Loading pkl: {PKL_PATH}")
    with open(PKL_PATH, "rb") as f:
        qp = pickle.load(f)

    original_m_cost = list(qp.m_cost)
    num_nodes = len(qp.m_cost)
    qp.m_cost = [0.0] * num_nodes

    logger.info(f"  nodes={qp.s_num}, queries={len(qp.u_ij)}")
    logger.info(f"  m_cost 全 {num_nodes} ノードをゼロに設定 (元の合計: {sum(original_m_cost):.0f})")

    # ゼロ上書きした qp を一時 pkl に保存して実験ランナーに渡す
    tmp_pkl = OUTPUT_DIR
    tmp_pkl.mkdir(parents=True, exist_ok=True)
    patched_pkl = tmp_pkl / "qp_zero_m_cost.pkl"
    with open(patched_pkl, "wb") as f:
        pickle.dump(qp, f)
    logger.info(f"  patched pkl 保存: {patched_pkl}")

    # 実験実行
    from src.runners.redbench_experiment import run_full_experiment
    run_full_experiment(
        pkl_path=patched_pkl,
        output_dir=OUTPUT_DIR,
        b_max_mb=B_MAX_MB,
        algorithms=ALGORITHMS,
        workload_type="redbench",
    )

if __name__ == "__main__":
    main()
