#!/bin/bash

# 実験を順次実行するスクリプト
# 使い方: nohup bash run_experiments.sh > experiments.log 2>&1 &

set -e  # エラーが発生したら停止

SCRIPT_DIR="experiments/small_test_ver2/scripts"
OUTPUT_DIR="experiments/small_test_ver2/time_dependent_output/job"

echo "========================================================================"
echo "実験開始: $(date)"
echo "========================================================================"

echo "baseline_benchmark"

echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase 9 \
  --query-set job \
  --exp-suffix _16_1 \
  --benchmark-mode baseline \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_baseline_16_1.txt
echo "完了時刻: $(date)"

echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase 9 \
  --query-set job \
  --exp-suffix _16_2 \
  --benchmark-mode baseline \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_baseline_16_2.txt
echo "完了時刻: $(date)"

echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase 9 \
  --query-set job \
  --exp-suffix _16_3 \
  --benchmark-mode baseline \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_baseline_16_3.txt
echo "完了時刻: $(date)"

echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase 9 \
  --query-set job \
  --exp-suffix _16_4 \
  --benchmark-mode baseline \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_baseline_16_4.txt
echo "完了時刻: $(date)"

