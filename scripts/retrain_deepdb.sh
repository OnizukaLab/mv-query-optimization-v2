#!/bin/bash
# DeepDB HDF生成 + アンサンブル再学習スクリプト (Clean Start版)
# 
# 使用方法:
#   nohup bash scripts/retrain_deepdb.sh > retrain.log 2>&1 &
#   tail -f retrain.log  # 進捗確認

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DEEPDB_DIR="$PROJECT_ROOT/deepdb/deepdb-public"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"

echo "=========================================="
echo "DeepDB Retraining Script (Clean Start)"
echo "Started at: $(date)"
echo "=========================================="

cd "$DEEPDB_DIR"

# ---------------------------------------------------------
# Step 1: HDF生成 (Clean)
# ---------------------------------------------------------
echo ""
echo "[Step 1/3] Generating HDF files..."
echo "Cleaning old HDF files..."
echo "Started at: $(date)"

# 【重要】古いHDFを完全に消して、新スキーマで作り直す
rm -rf ./imdb_hdf

$VENV_PYTHON maqp.py \
    --dataset imdb \
    --generate_hdf \
    --csv_path ./imdb_csv \
    --hdf_path ./imdb_hdf \
    --csv_seperator ',' \
    --max_rows_per_hdf_file 100000000

echo "HDF generation completed at: $(date)"

# ---------------------------------------------------------
# Step 2: サンプルHDF生成 (High Sample Size)
# ---------------------------------------------------------
echo ""
echo "[Step 2/3] Generating Sampled HDF files..."
echo "Started at: $(date)"

# RDC計算用に十分なサンプルサイズ（100000行）を使用
$VENV_PYTHON maqp.py \
    --dataset imdb \
    --generate_sampled_hdfs \
    --hdf_path ./imdb_hdf \
    --max_rows_per_hdf_file 100000000 \
    --hdf_sample_size 30000

echo "Sampled HDF generation completed at: $(date)"

# ---------------------------------------------------------
# Step 3: アンサンブル再学習 (rdc_based / High Budget)
# ---------------------------------------------------------
echo ""
echo "[Step 3/3] Training SPN Ensemble (rdc_based)..."
echo "Cleaning old Ensemble models..."
echo "Started at: $(date)"

# 【重要】古いモデルとキャッシュを完全に消す
rm -rf ./imdb_ensemble
mkdir -p ./imdb_ensemble

$VENV_PYTHON maqp.py \
    --dataset imdb \
    --generate_ensemble \
    --ensemble_strategy rdc_based \
    --hdf_path ./imdb_hdf \
    --ensemble_path ./imdb_ensemble \
    --pairwise_rdc_path ./imdb_ensemble/pairwise_rdc.pkl \
    --max_rows_per_hdf_file 100000000 \
    --samples_per_spn 1000000 1000000 1000000 1000000 1000000 \
    --samples_rdc_ensemble_tests 30000 \
    --post_sampling_factor 10 10 5 1 1 \
    --ensemble_budget_factor 5 \
    --ensemble_max_no_joins 3 \
    --rdc_threshold 0.15 \
    > training.log 2>&1 &

echo ""
echo "=========================================="
echo "DeepDB Retraining Complete!"
echo "Finished at: $(date)"
echo "=========================================="
