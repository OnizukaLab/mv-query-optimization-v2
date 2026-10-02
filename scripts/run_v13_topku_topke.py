"""v13 追加実験: topku / topke を v13 環境で実行.

実行:
    python scripts/run_v13_topku_topke.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PKL_PATH   = PROJECT_ROOT / "Output/redbench_freq_v2/qp_class.pkl"
OUTPUT_DIR = PROJECT_ROOT / "Output/redbench_edbt_v13_bigsubs_no_mcost"
B_MAX_MB   = 50
ALGORITHMS = ["topku", "topke"]


def main():
    from src.runners.redbench_experiment import run_full_experiment

    logger.info("=" * 65)
    logger.info("v13 追加実験: topku / topke")
    logger.info("=" * 65)

    run_full_experiment(
        pkl_path=PKL_PATH,
        output_dir=OUTPUT_DIR,
        b_max_mb=B_MAX_MB,
        algorithms=ALGORITHMS,
        workload_type="redbench",
    )


if __name__ == "__main__":
    main()
