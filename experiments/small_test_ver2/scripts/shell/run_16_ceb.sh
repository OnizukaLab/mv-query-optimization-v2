#!/bin/bash

# 実験を順次実行するスクリプト
# 使い方: nohup bash run_experiments.sh > experiments.log 2>&1 &

set -e  # エラーが発生したら停止

SCRIPT_DIR="experiments/small_test_ver2/scripts"
OUTPUT_DIR="experiments/small_test_ver2/time_dependent_output/cluster_55_53_combined/log"

echo "========================================================================"
echo "実験開始: $(date)"
echo "========================================================================"

# コンテナ再起動関数
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




restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set cluster_55_53_combined_ex \
  --exp-suffix _2h_x2 \
  --optimization-mode static \
  --static-timestep average \
  --static-algorithm utility \
  --noise-ratio 0.1 \
  --b-max 100 \
  --use-docker \
  --recalc \
  2>&1 | tee ${OUTPUT_DIR}/log_static_average_cluster_2h_x2.txt
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set cluster_55_53_combined_ex \
  --optimization-mode dynamic \
  --exp-suffix _2h_x2 \
  --use-docker \
  --use-pruning \
  --noise-ratio 0.1 \
  --b-max 100 \
  --recalc \
  2>&1 | tee ${OUTPUT_DIR}/log_2h_2x.txt
echo "完了時刻: $(date)"


restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set cluster_55_53_combined_ex \
  --exp-suffix _2h_x2 \
  --optimization-mode static \
  --static-timestep average \
  --static-algorithm utility \
  --noise-ratio 0.05 \
  --b-max 100 \
  --use-docker \
  --recalc \
  2>&1 | tee ${OUTPUT_DIR}/log_static_average_cluster_2h_x2.txt
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set cluster_55_53_combined_ex \
  --optimization-mode dynamic \
  --exp-suffix _2h_x2 \
  --use-docker \
  --use-pruning \
  --noise-ratio 0.05 \
  --b-max 100 \
  --recalc \
  2>&1 | tee ${OUTPUT_DIR}/log_2h_2x.txt
echo "完了時刻: $(date)"


# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set cluster_55_53_combined_ex \
#   --exp-suffix _2h_x2 \
#   --optimization-mode static \
#   --static-timestep average \
#   --static-algorithm utility \
#   --noise-ratio 0.0 \
#   --b-max 100 \
#   --use-docker \
#   --recalc \
#   --ease \
#   2>&1 | tee ${OUTPUT_DIR}/log_static_average_cluster_2h_x2.txt
# echo "完了時刻: $(date)"

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set cluster_55_53_combined_ex \
#   --optimization-mode dynamic \
#   --exp-suffix _2h_x2 \
#   --use-docker \
#   --use-pruning \
#   --b-max 100 \
#   --recalc \
#   2>&1 | tee ${OUTPUT_DIR}/log_2h_2x.txt
# echo "完了時刻: $(date)"



restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set cluster_55_53_combined_ex \
  --exp-suffix _2h_x2 \
  --optimization-mode adaptive \
  --window-size 2 \
  --noise-ratio 0.0 \
  --b-max 100 \
  --use-docker \
  --recalc \
  --ease \
  2>&1 | tee ${OUTPUT_DIR}/log_adaptive_2h_x2_2.txt
echo "完了時刻: $(date)"


restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set cluster_55_53_combined_ex \
  --exp-suffix _2h_x2 \
  --optimization-mode adaptive \
  --window-size 4 \
  --noise-ratio 0.0 \
  --b-max 100 \
  --use-docker \
  --recalc \
  --ease \
  2>&1 | tee ${OUTPUT_DIR}/log_adaptive_2h_x2_4.txt
echo "完了時刻: $(date)"


restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set cluster_55_53_combined_ex \
  --exp-suffix _2h_x2 \
  --optimization-mode static \
  --static-timestep average \
  --static-algorithm utility \
  --noise-ratio 0.3 \
  --b-max 100 \
  --use-docker \
  --recalc \
  2>&1 | tee ${OUTPUT_DIR}/log_static_average_cluster_2h_x2.txt
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set cluster_55_53_combined_ex \
  --optimization-mode dynamic \
  --exp-suffix _2h_x2 \
  --use-docker \
  --use-pruning \
  --noise-ratio 0.3 \
  --b-max 100 \
  --recalc \
  2>&1 | tee ${OUTPUT_DIR}/log_2h_2x.txt
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set cluster_55_53_combined_ex \
  --exp-suffix _2h_x2 \
  --optimization-mode static \
  --static-timestep average \
  --static-algorithm utility \
  --noise-ratio 0.15 \
  --b-max 100 \
  --use-docker \
  --recalc \
  2>&1 | tee ${OUTPUT_DIR}/log_static_average_cluster_2h_x2.txt
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set cluster_55_53_combined_ex \
  --optimization-mode dynamic \
  --exp-suffix _2h_x2 \
  --use-docker \
  --use-pruning \
  --noise-ratio 0.15 \
  --b-max 100 \
  --recalc \
  2>&1 | tee ${OUTPUT_DIR}/log_2h_2x.txt
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set cluster_55_53_combined_ex \
  --exp-suffix _2h_x2 \
  --optimization-mode static \
  --static-timestep average \
  --static-algorithm utility \
  --noise-ratio 0.2 \
  --b-max 100 \
  --use-docker \
  --recalc \
  2>&1 | tee ${OUTPUT_DIR}/log_static_average_cluster_2h_x2.txt
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set cluster_55_53_combined_ex \
  --optimization-mode dynamic \
  --exp-suffix _2h_x2 \
  --use-docker \
  --use-pruning \
  --noise-ratio 0.2 \
  --b-max 100 \
  --recalc \
  2>&1 | tee ${OUTPUT_DIR}/log_2h_2x.txt
echo "完了時刻: $(date)"


restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set cluster_55_53_combined_ex \
  --exp-suffix _2h_x2 \
  --optimization-mode static \
  --static-timestep average \
  --static-algorithm utility \
  --noise-ratio 0.25 \
  --b-max 100 \
  --use-docker \
  --recalc \
  2>&1 | tee ${OUTPUT_DIR}/log_static_average_cluster_2h_x2.txt
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set cluster_55_53_combined_ex \
  --optimization-mode dynamic \
  --exp-suffix _2h_x2 \
  --use-docker \
  --use-pruning \
  --noise-ratio 0.25 \
  --b-max 100 \
  --recalc \
  2>&1 | tee ${OUTPUT_DIR}/log_2h_2x.txt
echo "完了時刻: $(date)"


restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set cluster_55_53_combined_ex \
  --exp-suffix _2h_x2 \
  --optimization-mode static \
  --static-timestep average \
  --static-algorithm utility \
  --noise-ratio 0.35 \
  --b-max 100 \
  --use-docker \
  --recalc \
  2>&1 | tee ${OUTPUT_DIR}/log_static_average_cluster_2h_x2.txt
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set cluster_55_53_combined_ex \
  --optimization-mode dynamic \
  --exp-suffix _2h_x2 \
  --use-docker \
  --use-pruning \
  --noise-ratio 0.35 \
  --b-max 100 \
  --recalc \
  2>&1 | tee ${OUTPUT_DIR}/log_2h_2x.txt
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set cluster_55_53_combined_ex \
  --exp-suffix _2h_x2 \
  --optimization-mode static \
  --static-timestep average \
  --static-algorithm utility \
  --noise-ratio 0.4 \
  --b-max 100 \
  --use-docker \
  --recalc \
  2>&1 | tee ${OUTPUT_DIR}/log_static_average_cluster_2h_x2.txt
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set cluster_55_53_combined_ex \
  --optimization-mode dynamic \
  --exp-suffix _2h_x2 \
  --use-docker \
  --use-pruning \
  --noise-ratio 0.4 \
  --b-max 100 \
  --recalc \
  2>&1 | tee ${OUTPUT_DIR}/log_2h_2x.txt
echo "完了時刻: $(date)"

echo ""
echo "========================================================================"
echo "全実験完了: $(date)"
echo "========================================================================"