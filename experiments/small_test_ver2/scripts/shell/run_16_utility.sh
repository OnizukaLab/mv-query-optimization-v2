#!/bin/bash

# 実験を順次実行するスクリプト
# 使い方: nohup bash run_experiments.sh > experiments.log 2>&1 &. --pruning-method iterative

set -e  # エラーが発生したら停止

# 実験設定
STORAGE_MB=100  # ストレージ容量（MB）

SCRIPT_DIR="experiments/small_test_ver2/scripts"
OUTPUT_DIR="experiments/small_test_ver2/time_dependent_output/job/log"

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
python ${SCRIPT_DIR}/run_utility_optimization.py \
  --query-set job \
  --storage-mb ${STORAGE_MB} \
  --freq-suffix _16_4g \
  --pruning-method iterative \
  --use-parallel \

python ${SCRIPT_DIR}/run_utility_benchmark.py \
  --query-set job \
  --freq-suffix _16_4g \
  2>&1 | tee ${OUTPUT_DIR}/log_16_4g.txt
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_utility_optimization.py \
  --query-set job \
  --storage-mb ${STORAGE_MB} \
  --freq-suffix _16_1_10 \
  --pruning-method iterative \
  --use-parallel \

python ${SCRIPT_DIR}/run_utility_benchmark.py \
  --query-set job \
  --freq-suffix _16_1_10 \
  2>&1 | tee ${OUTPUT_DIR}/log_16_1_10.txt
echo "完了時刻: $(date)"


restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_utility_optimization.py \
  --query-set job \
  --storage-mb ${STORAGE_MB} \
  --freq-suffix _16_2_10 \
  --pruning-method iterative \
  --use-parallel \

python ${SCRIPT_DIR}/run_utility_benchmark.py \
  --query-set job \
  --freq-suffix _16_2_10 \
  2>&1 | tee ${OUTPUT_DIR}/log_16_2_10.txt
echo "完了時刻: $(date)"


restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_utility_optimization.py \
  --query-set job \
  --storage-mb ${STORAGE_MB} \
  --freq-suffix _16_3_10 \
  --pruning-method iterative \
  --use-parallel \

python ${SCRIPT_DIR}/run_utility_benchmark.py \
  --query-set job \
  --freq-suffix _16_3_10 \
  2>&1 | tee ${OUTPUT_DIR}/log_16_3_10.txt
echo "完了時刻: $(date)"


restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_utility_optimization.py \
  --query-set job \
  --storage-mb ${STORAGE_MB} \
  --freq-suffix _16_peak \
  --pruning-method iterative \
  --use-parallel \

python ${SCRIPT_DIR}/run_utility_benchmark.py \
  --query-set job \
  --freq-suffix _16_peak \
  2>&1 | tee ${OUTPUT_DIR}/log_16_peak.txt
echo "完了時刻: $(date)"


restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_utility_optimization.py \
  --query-set job \
  --storage-mb ${STORAGE_MB} \
  --freq-suffix _16_mono \
  --pruning-method iterative \
  --use-parallel \

python ${SCRIPT_DIR}/run_utility_benchmark.py \
  --query-set job \
  --freq-suffix _16_mono \
  2>&1 | tee ${OUTPUT_DIR}/log_16_mono.txt
echo "完了時刻: $(date)"


restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_utility_optimization.py \
  --query-set job \
  --storage-mb ${STORAGE_MB} \
  --freq-suffix _16_sin \
  --pruning-method iterative \
  --use-parallel \
  
python ${SCRIPT_DIR}/run_utility_benchmark.py \
  --query-set job \
  --freq-suffix _16_sin \
  2>&1 | tee ${OUTPUT_DIR}/log_16_sin.txt
echo "完了時刻: $(date)"





echo ""
echo "========================================================================"
echo "全実験完了: $(date)"
echo "========================================================================"