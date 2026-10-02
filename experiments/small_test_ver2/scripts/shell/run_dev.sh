#!/bin/bash

# 実験を順次実行するスクリプト
# 使い方: nohup bash run_experiments.sh > experiments.log 2>&1 &

set -e  # エラーが発生したら停止

SCRIPT_DIR="experiments/small_test_ver2/scripts"
OUTPUT_DIR="experiments/small_test_ver2/time_dependent_output/job/log"

echo "========================================================================"
echo "実験開始: $(date)"
echo "========================================================================"


# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _16_1_4dev \
#   --use-pruning \
#   --pruning-parallel \
#   --use-docker \
#   2>&1 | tee ${OUTPUT_DIR}/log_16_1_4dev.txt
# echo "完了時刻: $(date)"

# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _16_1_4dev \
#   --optimization-mode static \
#   --static-timestep average \
#   --use-docker \
#   2>&1 | tee ${OUTPUT_DIR}/log_static_average_16_1_4dev.txt
# echo "完了時刻: $(date)"

# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _16_2_4dev \
#   --use-pruning \
#   --pruning-parallel \
#   --use-docker \
#   2>&1 | tee ${OUTPUT_DIR}/log_16_2_4dev.txt
# echo "完了時刻: $(date)"

# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _16_2_4dev \
#   --optimization-mode static \
#   --static-timestep average \
#   --use-docker \
#   2>&1 | tee ${OUTPUT_DIR}/log_static_average_16_2_4dev.txt
# echo "完了時刻: $(date)"

echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --optimization-mode dynamic \
  --exp-suffix _16_1 \
  --use-pruning \
  --pruning-parallel \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_16_1.txt
echo "完了時刻: $(date)"

echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --exp-suffix _16_1 \
  --optimization-mode static \
  --static-timestep average \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_static_average_16_1.txt
echo "完了時刻: $(date)"

echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --optimization-mode dynamic \
  --exp-suffix _16_2 \
  --use-pruning \
  --pruning-parallel \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_16_2.txt
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
  --static-timestep average \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_static_average_16_2.txt
echo "完了時刻: $(date)"