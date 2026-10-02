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
#   --exp-suffix _8_1_opt \
#   --use-docker \
#   2>&1 | tee ${OUTPUT_DIR}/log_8_1_opt.txt
# echo "完了時刻: $(date)"

# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _8_1_opt \
#   --optimization-mode static \
#   --static-algorithm normal \
#   --static-timestep average \
#   --use-docker \
#   2>&1 | tee ${OUTPUT_DIR}/log_static_average_normal_8_1_opt.txt
# echo "完了時刻: $(date)"

# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _8_1_opt \
#   --optimization-mode static \
#   --static-algorithm bigsubs \
#   --static-timestep average \
#   --use-docker \
#   2>&1 | tee ${OUTPUT_DIR}/log_static_average_bigsubs_8_1_opt.txt
# echo "完了時刻: $(date)"

# # 実験2: プルーニングあり（逐次実行）
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _8_2_opt \
#   --use-docker \
#   2>&1 | tee ${OUTPUT_DIR}/log_8_2_opt.txt
# echo "完了時刻: $(date)"

# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _8_2_opt \
#   --optimization-mode static \
#   --static-timestep average \
#   --use-docker \
#   2>&1 | tee ${OUTPUT_DIR}/log_static_average_8_2_opt.txt
# echo "完了時刻: $(date)"

# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _8_2_opt \
#   --optimization-mode static \
#   --static-algorithm bigsubs \
#   --static-timestep average \
#   --use-docker \
#   2>&1 | tee ${OUTPUT_DIR}/log_static_average_bigsubs_8_2_opt.txt
# echo "完了時刻: $(date)"

# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job_real \
#   --optimization-mode dynamic \
#   --exp-suffix _8_3_opt \
#   --use-docker \
#   2>&1 | tee ${OUTPUT_DIR}/log_8_3_opt.txt
# echo "完了時刻: $(date)"

# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job_real \
#   --exp-suffix _8_3_opt \
#   --optimization-mode static \
#   --static-timestep average \
#   --use-docker \
#   2>&1 | tee ${OUTPUT_DIR}/log_static_average_8_3_opt.txt
# echo "完了時刻: $(date)"

# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _8_3_opt \
#   --optimization-mode static \
#   --static-algorithm bigsubs \
#   --static-timestep average \
#   --use-docker \
#   2>&1 | tee ${OUTPUT_DIR}/log_static_average_bigsubs_8_3_opt.txt
# echo "完了時刻: $(date)"

# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _8_1_opt \
#   --use-pruning \
#   --pruning-parallel \
#   --static-protection \
#   --use-docker \
#   2>&1 | tee ${OUTPUT_DIR}/log_with_pruning_8_1_opt.txt
# echo "完了時刻: $(date)"

# # 実験2: プルーニングあり（逐次実行）
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _8_2_opt \
#   --use-pruning \
#   --pruning-parallel \
#   --static-protection \
#   --use-docker \
#   2>&1 | tee ${OUTPUT_DIR}/log_with_pruning_8_2_opt.txt
# echo "完了時刻: $(date)"

# # 実験3: プルーニングあり（並列実行・16ワーカー）
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _8_3_opt \
#   --use-pruning \
#   --pruning-parallel \
#   --static-protection \
#   --use-docker \
#   2>&1 | tee ${OUTPUT_DIR}/log_with_pruning_8_3_opt.txt
# echo "完了時刻: $(date)"


# echo "実験終了: $(date)"



echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job_real \
  --optimization-mode dynamic \
  --exp-suffix _8_1 \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_8_1.txt
echo "完了時刻: $(date)"

echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job_real \
  --exp-suffix _8_1 \
  --optimization-mode static \
  --static-algorithm normal \
  --static-timestep average \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_static_average_normal_8_1.txt
echo "完了時刻: $(date)"

echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job_real \
  --optimization-mode dynamic \
  --exp-suffix _8_2 \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_8_2.txt
echo "完了時刻: $(date)"

echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job_real \
  --exp-suffix _8_2 \
  --optimization-mode static \
  --static-algorithm normal \
  --static-timestep average \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_static_average_normal_8_2.txt
echo "完了時刻: $(date)"