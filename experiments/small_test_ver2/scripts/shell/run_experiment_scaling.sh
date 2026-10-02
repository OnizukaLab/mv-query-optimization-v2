#!/bin/bash

# 実験を順次実行するスクリプト
# 使い方: nohup bash run_experiments.sh > experiments.log 2>&1 &

set -e  # エラーが発生したら停止

SCRIPT_DIR="experiments/small_test_ver2/scripts"
OUTPUT_DIR="experiments/small_test_ver2/time_dependent_output/job/log"

echo "========================================================================"
echo "実験開始: $(date)"
echo "========================================================================"

echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase 6 \
  --query-set job \
  --optimization-mode dynamic \
  --exp-suffix _8 \
  --use-pruning \
  --pruning-parallel \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_with_pruning_8.txt
echo "完了時刻: $(date)"

echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase 6 \
  --query-set job \
  --optimization-mode dynamic \
  --exp-suffix _12 \
  --use-pruning \
  --pruning-parallel \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_with_pruning_12.txt
echo "完了時刻: $(date)"

echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase 6 \
  --query-set job \
  --optimization-mode dynamic \
  --exp-suffix _20 \
  --use-pruning \
  --pruning-parallel \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_with_pruning_20.txt
echo "完了時刻: $(date)"

echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase 6 \
  --query-set job \
  --optimization-mode dynamic \
  --exp-suffix _24 \
  --use-pruning \
  --pruning-parallel \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_with_pruning_24.txt
echo "完了時刻: $(date)"

echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase 6 \
  --query-set job \
  --optimization-mode dynamic \
  --exp-suffix _28 \
  --use-pruning \
  --pruning-parallel \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_with_pruning_28.txt
echo "完了時刻: $(date)"

echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase 6 \
  --query-set job \
  --optimization-mode dynamic \
  --exp-suffix _32 \
  --use-pruning \
  --pruning-parallel \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_with_pruning_32.txt
echo "完了時刻: $(date)"


echo "実験終了: $(date)"