#!/bin/bash

# 実験を順次実行するスクリプト
# 使い方: nohup bash run_experiments.sh > experiments.log 2>&1 &

set -e  # エラーが発生したら停止

SCRIPT_DIR="experiments/small_test_ver2/scripts"
OUTPUT_DIR="experiments/small_test_ver2/time_dependent_output/job/log"

echo "========================================================================"
echo "実験開始: $(date)"
echo "========================================================================"


restart_container() {
    echo ""
    echo ">>> PostgreSQLコンテナを再起動してキャッシュをクリア..."
    docker restart mv_postgres
    echo ">>> 起動完了を待機中..."
    sleep 15
    # 接続確認
    until docker exec mv_postgres pg_isready -U postgres > /dev/null 2>&1; do
        echo ">>> PostgreSQL起動待ち..."
        sleep 2
    done
    echo ">>> PostgreSQL起動完了"
}


######8time######

echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase 6 \
  --query-set job \
  --exp-suffix _20_mono \
  --optimization-mode adaptive \
  --window-size 2 \
  --noise-ratio 0.0 \
  --b-max 100 \
  --use-docker \
  --recalc \
  --ease \
  2>&1 | tee ${OUTPUT_DIR}/log_adaptive_8_mono.txt
echo "完了時刻: $(date)"


echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase 6 \
  --query-set job \
  --exp-suffix _20_mono \
  --optimization-mode adaptive \
  --window-size 4 \
  --noise-ratio 0.0 \
  --b-max 100 \
  --use-docker \
  --recalc \
  --ease \
  2>&1 | tee ${OUTPUT_DIR}/log_adaptive_8_mono.txt
echo "完了時刻: $(date)"


# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _8_mono \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_dynamic_8_mono.txt
# echo "完了時刻: $(date)"


# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python -u ${SCRIPT_DIR}/run_utility_optimization.py \
#   --query-set job \
#   --freq-suffix _8_mono \
#   --pruning-method iterative \
#   --storage-mb 100 \
#   2>&1 | tee ${OUTPUT_DIR}/log_8_mono_opt.txt
# echo "完了時刻: $(date)"


# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --exp-suffix _12_mono \
#   --optimization-mode adaptive \
#   --window-size 2 \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --use-docker \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_12_mono.txt
# echo "完了時刻: $(date)"

# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --exp-suffix _12_mono \
#   --optimization-mode adaptive \
#   --window-size 4 \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --use-docker \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_12_mono.txt
# echo "完了時刻: $(date)"


# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _12_mono \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_dynamic_12_mono.txt
# echo "完了時刻: $(date)"


# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python -u ${SCRIPT_DIR}/run_utility_optimization.py \
#   --query-set job \
#   --freq-suffix _12_mono \
#   --pruning-method iterative \
#   --storage-mb 100 \
#   2>&1 | tee ${OUTPUT_DIR}/log_12_mono_opt.txt
# echo "完了時刻: $(date)"

# ######24time######
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --exp-suffix _24_mono \
#   --optimization-mode adaptive \
#   --window-size 2 \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --use-docker \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_24_mono.txt
# echo "完了時刻: $(date)"

# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --exp-suffix _24_mono \
#   --optimization-mode adaptive \
#   --window-size 4 \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --use-docker \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_24_mono.txt
# echo "完了時刻: $(date)"


# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _24_mono \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_dynamic_24_mono.txt
# echo "完了時刻: $(date)"


# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python -u ${SCRIPT_DIR}/run_utility_optimization.py \
#   --query-set job \
#   --freq-suffix _24_mono \
#   --pruning-method iterative \
#   --storage-mb 100 \
#   2>&1 | tee ${OUTPUT_DIR}/log_24_mono_opt.txt
# echo "完了時刻: $(date)"

# # ######28time######
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --exp-suffix _28_mono \
#   --optimization-mode adaptive \
#   --window-size 2 \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --use-docker \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_28_mono.txt
# echo "完了時刻: $(date)"

# # restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --exp-suffix _28_mono \
#   --optimization-mode adaptive \
#   --window-size 4 \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --use-docker \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_28_mono.txt
# echo "完了時刻: $(date)"


# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _28_mono \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_dynamic_28_mono.txt
# echo "完了時刻: $(date)"


# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python -u ${SCRIPT_DIR}/run_utility_optimization.py \
#   --query-set job \
#   --freq-suffix _28_mono \
#   --pruning-method iterative \
#   --storage-mb 100 \
#   2>&1 | tee ${OUTPUT_DIR}/log_28_mono_opt.txt
# echo "完了時刻: $(date)"

# #####32time######
# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --exp-suffix _32_mono \
#   --optimization-mode adaptive \
#   --window-size 2 \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --use-docker \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_32_mono.txt
# echo "完了時刻: $(date)"

# # restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --exp-suffix _32_mono \
#   --optimization-mode adaptive \
#   --window-size 4 \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --use-docker \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_32_mono.txt
# echo "完了時刻: $(date)"


# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _32_mono \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_dynamic_32_mono.txt
# echo "完了時刻: $(date)"


# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python -u ${SCRIPT_DIR}/run_utility_optimization.py \
#   --query-set job \
#   --freq-suffix _32_mono \
#   --pruning-method iterative \
#   --storage-mb 100 \
#   2>&1 | tee ${OUTPUT_DIR}/log_32_mono_opt.txt
# echo "完了時刻: $(date)"

# ######36time######
# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --exp-suffix _36_mono \
#   --optimization-mode adaptive \
#   --window-size 2 \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --use-docker \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_36_mono.txt
# echo "完了時刻: $(date)"

# # restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --exp-suffix _36_mono \
#   --optimization-mode adaptive \
#   --window-size 4 \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --use-docker \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_36_mono.txt
# echo "完了時刻: $(date)"


# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _36_mono \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_dynamic_36_mono.txt
# echo "完了時刻: $(date)"


# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python -u ${SCRIPT_DIR}/run_utility_optimization.py \
#   --query-set job \
#   --freq-suffix _36_mono \
#   --pruning-method iterative \
#   --storage-mb 100 \
#   2>&1 | tee ${OUTPUT_DIR}/log_36_mono_opt.txt
# echo "完了時刻: $(date)"

# ######20time######
# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --exp-suffix _20_mono \
#   --optimization-mode adaptive \
#   --window-size 2 \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --use-docker \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_20_mono.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --exp-suffix _20_mono \
#   --optimization-mode adaptive \
#   --window-size 4 \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --use-docker \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_20_mono.txt
# echo "完了時刻: $(date)"


# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _20_mono \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_dynamic_20_mono.txt
# echo "完了時刻: $(date)"


# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python -u ${SCRIPT_DIR}/run_utility_optimization.py \
#   --query-set job \
#   --freq-suffix _20_mono \
#   --pruning-method iterative \
#   --storage-mb 100 \
#   2>&1 | tee ${OUTPUT_DIR}/log_20_mono_opt.txt
# echo "完了時刻: $(date)"


# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --optimization-mode dynamic \
#   --use-pruning \
#   --exp-suffix _8_mono \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_dynamic_8_mono.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --optimization-mode dynamic \
#   --use-pruning \
#   --exp-suffix _12_mono \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_dynamic_12_mono.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --optimization-mode dynamic \
#   --use-pruning \
#   --exp-suffix _16_mono \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_dynamic_16_mono.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --optimization-mode dynamic \
#   --use-pruning \
#   --exp-suffix _20_mono \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_dynamic_20_mono.txt
# echo "完了時刻: $(date)"


# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --optimization-mode dynamic \
#   --use-pruning \
#   --exp-suffix _24_mono \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_dynamic_24_mono.txt
# echo "完了時刻: $(date)"

# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --optimization-mode dynamic \
#   --use-pruning \
#   --exp-suffix _28_mono \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_dynamic_28_mono.txt
# echo "完了時刻: $(date)"

# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --optimization-mode dynamic \
#   --use-pruning \
#   --exp-suffix _32_mono \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_dynamic_32_mono.txt
# echo "完了時刻: $(date)"

# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --optimization-mode dynamic \
#   --use-pruning \
#   --exp-suffix _36_mono \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_dynamic_36_mono.txt
# echo "完了時刻: $(date)"

# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --exp-suffix _8_mono \
#   --optimization-mode static \
#   --static-timestep average \
#   --static-algorithm utility \
#   --b-max 100 \
#   --use-docker 
# echo "完了時刻: $(date)"

# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --exp-suffix _16_mono \
#   --optimization-mode static \
#   --static-timestep average \
#   --static-algorithm utility \
#   --b-max 100 \
#   --use-docker 
# echo "完了時刻: $(date)"

# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --exp-suffix _24_mono \
#   --optimization-mode static \
#   --static-timestep average \
#   --static-algorithm utility \
#   --b-max 100 \
#   --use-docker 
# echo "完了時刻: $(date)"

# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 6 \
#   --query-set job \
#   --exp-suffix _32_mono \
#   --optimization-mode static \
#   --static-timestep average \
#   --static-algorithm utility \
#   --b-max 100 \
#   --use-docker 
# echo "完了時刻: $(date)"

