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


######16_2_10######
# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 9 \
#   --query-set job \
#   --exp-suffix _16_1_10 \
#   --benchmark-mode baseline \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_baseline_16_1_10.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 9 \
#   --query-set job \
#   --exp-suffix _16_2_10 \
#   --benchmark-mode baseline \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_baseline_16_2_10.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 9 \
#   --query-set job \
#   --exp-suffix _16_3_10 \
#   --benchmark-mode baseline \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_baseline_16_3_10.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 9 \
#   --query-set job \
#   --exp-suffix _16_mono \
#   --benchmark-mode baseline \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_baseline_16_mono.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase 9 \
#   --query-set job \
#   --exp-suffix _16_peak \
#   --benchmark-mode baseline \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_baseline_16_peak.txt
# echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase 9 \
  --query-set cluster_55_53_combined \
  --exp-suffix  _2h_x2 \
  --benchmark-mode baseline \
  --recalc \
  --ease \
  2>&1 | tee ${OUTPUT_DIR}/log_baseline_cluster_55_53_combined.txt
echo "完了時刻: $(date)"


