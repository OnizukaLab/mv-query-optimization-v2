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



# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _16_1_10 \
#   --use-docker \
#   --use-pruning \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_16_1.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _16_2_10 \
#   --use-docker \
#   --use-pruning \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_16_1.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _16_3_10 \
#   --use-docker \
#   --use-pruning \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_16_1.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _16_mono \
#   --use-docker \
#   --use-pruning \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_16_1.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _16_peak \
#   --use-docker \
#   --use-pruning \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_16_1.txt
# echo "完了時刻: $(date)"


######8_2_10######
# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _8_2_10 \
#   --optimization-mode adaptive \
#   --window-size 2 \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_8_2.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _8_2_10 \
#   --optimization-mode adaptive \
#   --window-size 4 \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_8_2.txt
# echo "完了時刻: $(date)"


# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _8_2_10 \
#   --optimization-mode static \
#   --static-timestep average \
#   --static-algorithm utility \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_static_average_8_2.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _8_2_10 \
#   --use-docker \
#   --use-pruning \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_8_1.txt
# echo "完了時刻: $(date)"

# ######24_2_10######
# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _24_2_10 \
#   --optimization-mode adaptive \
#   --window-size 2 \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_24_2.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _24_2_10 \
#   --optimization-mode adaptive \
#   --window-size 4 \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_24_2.txt
# echo "完了時刻: $(date)"


# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _24_2_10 \
#   --optimization-mode static \
#   --static-timestep average \
#   --static-algorithm utility \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_static_average_24_2.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _24_2_10 \
#   --use-docker \
#   --use-pruning \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_24_2.txt
# echo "完了時刻: $(date)"


# ######32_2_10######
# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _32_2_10 \
#   --optimization-mode adaptive \
#   --window-size 2 \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_32_2.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _32_2_10 \
#   --optimization-mode adaptive \
#   --window-size 4 \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_32_2.txt
# echo "完了時刻: $(date)"


# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _32_2_10 \
#   --optimization-mode static \
#   --static-timestep average \
#   --static-algorithm utility \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_static_average_32_2.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _32_2_10 \
#   --use-docker \
#   --use-pruning \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_32_2.txt
# echo "完了時刻: $(date)"


# ######8_mono######
# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _8_mono \
#   --optimization-mode adaptive \
#   --window-size 2 \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_8_mono.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _8_mono \
#   --optimization-mode adaptive \
#   --window-size 4 \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_8_mono.txt
# echo "完了時刻: $(date)"


# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _8_mono \
#   --optimization-mode static \
#   --static-timestep average \
#   --static-algorithm utility \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_static_average_8_mono.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _8_mono \
#   --use-docker \
#   --use-pruning \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_8_mono.txt
# echo "完了時刻: $(date)"


# ######24_mono######
# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _24_mono \
#   --optimization-mode adaptive \
#   --window-size 2 \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_24_mono.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _24_mono \
#   --optimization-mode adaptive \
#   --window-size 4 \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_24_mono.txt
# echo "完了時刻: $(date)"


# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _24_mono \
#   --optimization-mode static \
#   --static-timestep average \
#   --static-algorithm utility \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_static_average_24_mono.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _24_mono \
#   --use-docker \
#   --use-pruning \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_24_mono.txt
# echo "完了時刻: $(date)"


# ######32_mono######
# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _32_mono \
#   --optimization-mode adaptive \
#   --window-size 2 \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_32_mono.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _32_mono \
#   --optimization-mode adaptive \
#   --window-size 4 \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_32_mono.txt
# echo "完了時刻: $(date)"


# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _32_mono \
#   --optimization-mode static \
#   --static-timestep average \
#   --static-algorithm utility \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_static_average_32_mono.txt
# echo "完了時刻: $(date)"


######8_peak######
# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _8_peak \
#   --optimization-mode adaptive \
#   --window-size 2 \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_8_peak.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _8_peak \
#   --optimization-mode adaptive \
#   --window-size 4 \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_8_peak.txt
# echo "完了時刻: $(date)"


restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --exp-suffix _8_peak \
  --optimization-mode static \
  --static-timestep average \
  --static-algorithm utility \
  --noise-ratio 0.0 \
  --use-docker \
  --recalc \
  --ease \
  2>&1 | tee ${OUTPUT_DIR}/log_static_average_8_peak.txt
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --optimization-mode dynamic \
  --exp-suffix _8_peak \
  --use-docker \
  --use-pruning \
  --noise-ratio 0.0 \
  --b-max 100 \
  --recalc \
  --ease \
  2>&1 | tee ${OUTPUT_DIR}/log_8_peak.txt
echo "完了時刻: $(date)"


restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --optimization-mode dynamic \
  --exp-suffix _32_mono \
  --use-docker \
  --use-pruning \
  --noise-ratio 0.0 \
  --b-max 100 \
  --recalc \
  2>&1 | tee ${OUTPUT_DIR}/log_32_mono.txt
echo "完了時刻: $(date)"

######24_peak######
# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _24_peak \
#   --optimization-mode adaptive \
#   --window-size 2 \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_24_peak.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _24_peak \
#   --optimization-mode adaptive \
#   --window-size 4 \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_24_peak.txt
# echo "完了時刻: $(date)"


# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _24_peak \
#   --optimization-mode static \
#   --static-timestep average \
#   --static-algorithm utility \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_static_average_24_peak.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _24_peak \
#   --use-docker \
#   --use-pruning \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_24_peak.txt
# echo "完了時刻: $(date)"


# ######32_peak######
# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _32_peak \
#   --optimization-mode adaptive \
#   --window-size 2 \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_32_peak.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _32_peak \
#   --optimization-mode adaptive \
#   --window-size 4 \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_adaptive_32_peak.txt
# echo "完了時刻: $(date)"


# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --exp-suffix _32_peak \
#   --optimization-mode static \
#   --static-timestep average \
#   --static-algorithm utility \
#   --noise-ratio 0.0 \
#   --use-docker \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_static_average_32_peak.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set job \
#   --optimization-mode dynamic \
#   --exp-suffix _32_peak \
#   --use-docker \
#   --use-pruning \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_32_peak.txt
# echo "完了時刻: $(date)"





