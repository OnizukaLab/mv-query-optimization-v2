#!/bin/bash

# 実験を順次実行するスクリプト
# 使い方: nohup bash run_experiments.sh > experiments.log 2>&1 &

set -e  # エラーが発生したら停止

SCRIPT_DIR="experiments/small_test_ver2/scripts"
OUTPUT_DIR="experiments/small_test_ver2/time_dependent_output/job"

echo "static_benchmark"

echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --exp-suffix _16_1 \
  --optimization-mode static \
  --static-timestep last \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_static_last_16_1.txt
echo "完了時刻: $(date)"

echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --exp-suffix _16_2 \
  --optimization-mode static \
  --static-timestep last \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_static_last_16_2.txt
echo "完了時刻: $(date)"

echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --exp-suffix _16_3 \
  --optimization-mode static \
  --static-timestep last \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_static_last_16_3.txt
echo "完了時刻: $(date)"

echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --exp-suffix _16_4 \
  --optimization-mode static \
  --static-timestep last \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_static_last_16_4.txt
echo "完了時刻: $(date)"



echo "実験終了: $(date)"