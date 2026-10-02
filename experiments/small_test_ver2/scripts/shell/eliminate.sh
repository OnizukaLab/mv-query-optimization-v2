#!/bin/bash

# 実験を順次実行するスクリプト
# 使い方: nohup bash run_experiments.sh > experiments.log 2>&1 &

set -e  # エラーが発生したら停止

python experiments/small_test_ver2/scripts/diagnose_static_mvs.py \
  --sql-file experiments/small_test_ver2/time_dependent_output/cluster_55_25_26_3_ex/static_initial_mvs.sql \
  --host localhost \
  --port 5432 \
  --database imdbload \
  --user postgres \
  --password pass \
  --timeout-sec 300 \
  --out-dir experiments/small_test_ver2/time_dependent_output/cluster_55_25_26_3_ex