# 実験結果の確認ガイド

各フェーズの実行結果と実行時間を確認する方法をまとめます。

## 🎯 クイックスタート

実験を実行すると、以下のディレクトリ構造で結果が保存されます：

```bash
# 実験実行
python scripts/run_experiment.py --algorithms normal bigsubs

# 結果確認
tree Output/normal/
```

## 📂 出力ディレクトリ構造

```
Output/
├── qp_class.pkl                          # [Phase 1] クエリパース結果
│
├── normal/                               # Normalアルゴリズムの結果
│   ├── optimization/
│   │   ├── result.json                   # 最適化結果（詳細）
│   │   └── mv_list.csv                   # MVリスト（旧形式互換）
│   ├── mv_creation/
│   │   └── creation_log.json             # MV作成ログ
│   ├── query_rewrite/
│   │   └── rewrite_log.json              # クエリ書き換えログ
│   └── summary.json                      # 統合サマリー ⭐
│
├── bigsubs/                              # BigSubsアルゴリズムの結果
│   └── ...（同様の構造）
│
└── query_rewrite/re_sql/                 # 書き換えクエリSQL
    ├── normal/
    │   ├── 1a.sql
    │   └── ...
    └── bigsubs/
        └── ...
```

## ⭐ 最重要: 統合サマリーファイル

### `Output/{algorithm}/summary.json`

**全フェーズの実行時間が一目でわかる**最も重要なファイルです。

```bash
# 確認方法
cat Output/normal/summary.json | jq '.'
```

**出力例**:
```json
{
  "algorithm": "normal",
  "total_execution_time": 678.90,
  "phases": {
    "optimization": 123.45,
    "mv_creation": 456.78,
    "query_rewriting": 3.45
  },
  "timestamp": "2025-10-08 14:30:25"
}
```

### 複数アルゴリズムの比較

```bash
# 全アルゴリズムの実行時間を比較
echo "Algorithm Performance Comparison:"
echo "------------------------------------------------------------"
printf "%-20s %15s %15s %15s %15s\n" "Algorithm" "Optimization" "MV Creation" "Rewriting" "Total"
echo "------------------------------------------------------------"

for alg in normal bigsubs utility utility_capacity frequency; do
    if [ -f "Output/$alg/summary.json" ]; then
        python3 -c "
import json
with open('Output/$alg/summary.json') as f:
    s = json.load(f)
    p = s['phases']
    print(f\"{s['algorithm']:<20} {p.get('optimization', 0):>15.2f} {p.get('mv_creation', 0):>15.2f} {p.get('query_rewriting', 0):>15.2f} {s['total_execution_time']:>15.2f}\")
"
    fi
done
```

**出力例**:
```
Algorithm Performance Comparison:
------------------------------------------------------------
Algorithm            Optimization     MV Creation       Rewriting           Total
------------------------------------------------------------
normal                      123.45          456.78            3.45          678.90
bigsubs                     134.56          412.34            3.21          645.23
utility                     145.67          398.76            3.12          632.87
```

## 📊 各フェーズの詳細結果

### Phase 2: 最適化結果

```bash
# 最適化結果の確認
cat Output/normal/optimization/result.json | jq '{
  algorithm,
  num_selected_views,
  total_utility,
  total_storage_mb,
  execution_time
}'
```

**出力例**:
```json
{
  "algorithm": "normal",
  "num_selected_views": 42,
  "total_utility": 12345.67,
  "total_storage_mb": 45.78,
  "execution_time": 123.45
}
```

**選択されたMVの詳細**:
```bash
cat Output/normal/optimization/result.json | jq '.selected_views[] | {view_id, size_mb, maintenance_cost, usage_count}' | head -20
```

### Phase 3: MV作成結果

```bash
# MV作成結果の確認
cat Output/normal/mv_creation/creation_log.json | jq '{
  total_mvs,
  created,
  failed,
  total_time
}'
```

**出力例**:
```json
{
  "total_mvs": 42,
  "created": 40,
  "failed": 2,
  "total_time": 456.78
}
```

**失敗したMVの確認**:
```bash
cat Output/normal/mv_creation/creation_log.json | jq '.mvs[] | select(.status != "SUCCESS") | {view_id, status, error}'
```

**最も時間がかかったMV Top 5**:
```bash
cat Output/normal/mv_creation/creation_log.json | jq '.mvs | sort_by(-.creation_time) | .[0:5] | .[] | {view_id, creation_time, size_mb}'
```

### Phase 4: クエリ書き換え結果

```bash
# クエリ書き換え結果の確認
cat Output/normal/query_rewrite/rewrite_log.json | jq '{
  total_queries,
  total_time,
  average_time: (.total_time / .total_queries)
}'
```

**出力例**:
```json
{
  "total_queries": 113,
  "total_time": 3.45,
  "average_time": 0.0305
}
```

**書き換えたクエリSQLの確認**:
```bash
# 特定のクエリを確認
cat Output/query_rewrite/re_sql/normal/1a.sql

# 最初の5クエリを確認
ls Output/query_rewrite/re_sql/normal/*.sql | head -5 | xargs -I {} sh -c 'echo "=== {} ===" && cat {} && echo'
```

## 🔍 便利なコマンド集

### 全体のサマリー表示

```bash
#!/bin/bash
# show_results.sh

echo "==============================================="
echo "Experiment Results Summary"
echo "==============================================="

for alg in normal bigsubs utility utility_capacity frequency; do
    if [ -f "Output/$alg/summary.json" ]; then
        echo ""
        echo "=== $alg ==="
        
        # 統合サマリー
        python3 -c "
import json
with open('Output/$alg/summary.json') as f:
    s = json.load(f)
    print(f\"Total Time: {s['total_execution_time']:.2f}s\")
    print(f\"  - Optimization: {s['phases'].get('optimization', 0):.2f}s\")
    print(f\"  - MV Creation: {s['phases'].get('mv_creation', 0):.2f}s\")
    print(f\"  - Query Rewriting: {s['phases'].get('query_rewriting', 0):.2f}s\")
"
        
        # 最適化結果
        if [ -f "Output/$alg/optimization/result.json" ]; then
            python3 -c "
import json
with open('Output/$alg/optimization/result.json') as f:
    r = json.load(f)
    print(f\"Selected MVs: {r['num_selected_views']}\")
    print(f\"Total Utility: {r['total_utility']:.2f}\")
    print(f\"Storage Used: {r['total_storage_mb']:.2f} MB\")
"
        fi
        
        # MV作成結果
        if [ -f "Output/$alg/mv_creation/creation_log.json" ]; then
            python3 -c "
import json
with open('Output/$alg/mv_creation/creation_log.json') as f:
    c = json.load(f)
    print(f\"MVs Created: {c['created']}/{c['total_mvs']} (Failed: {c['failed']})\")
"
        fi
    fi
done

echo ""
echo "==============================================="
```

### CSV形式でエクスポート

```bash
# results_export.sh

echo "algorithm,opt_time,mv_creation_time,rewrite_time,total_time,selected_mvs,utility,storage_mb,mvs_created,mvs_failed" > results.csv

for alg in normal bigsubs utility utility_capacity frequency; do
    if [ -f "Output/$alg/summary.json" ]; then
        python3 << EOF >> results.csv
import json

# サマリー読み込み
with open('Output/$alg/summary.json') as f:
    summary = json.load(f)

# 最適化結果
with open('Output/$alg/optimization/result.json') as f:
    opt = json.load(f)

# MV作成結果
with open('Output/$alg/mv_creation/creation_log.json') as f:
    mv = json.load(f)

print(f"{summary['algorithm']},{summary['phases'].get('optimization', 0)},{summary['phases'].get('mv_creation', 0)},{summary['phases'].get('query_rewriting', 0)},{summary['total_execution_time']},{opt['num_selected_views']},{opt['total_utility']:.2f},{opt['total_storage_mb']:.2f},{mv['created']},{mv['failed']}")
EOF
    fi
done

echo "Results exported to results.csv"
cat results.csv
```

### データベース内のMV確認

```bash
# データベースに作成されたMVを確認
psql -h localhost -p 5432 -U postgres -d imdbload << 'EOF'
SELECT 
    matviewname,
    pg_size_pretty(pg_total_relation_size('public.' || matviewname)) as size
FROM pg_matviews 
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size('public.' || matviewname) DESC;
EOF
```

## 📈 グラフ化（Python）

```python
#!/usr/bin/env python3
# visualize_results.py

import json
import matplotlib.pyplot as plt
from pathlib import Path

algorithms = ['normal', 'bigsubs', 'utility', 'utility_capacity', 'frequency']
results = {}

# データ読み込み
for alg in algorithms:
    summary_path = Path(f'Output/{alg}/summary.json')
    if summary_path.exists():
        with open(summary_path) as f:
            results[alg] = json.load(f)

# フェーズごとの実行時間を可視化
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

# 積み上げ棒グラフ
algs = list(results.keys())
opt_times = [results[alg]['phases'].get('optimization', 0) for alg in algs]
mv_times = [results[alg]['phases'].get('mv_creation', 0) for alg in algs]
rw_times = [results[alg]['phases'].get('query_rewriting', 0) for alg in algs]

ax1.bar(algs, opt_times, label='Optimization')
ax1.bar(algs, mv_times, bottom=opt_times, label='MV Creation')
ax1.bar(algs, rw_times, bottom=[o+m for o, m in zip(opt_times, mv_times)], label='Query Rewriting')
ax1.set_ylabel('Time (seconds)')
ax1.set_title('Execution Time by Phase')
ax1.legend()
ax1.grid(axis='y', alpha=0.3)

# 最適化結果の比較
for alg in algs:
    opt_path = Path(f'Output/{alg}/optimization/result.json')
    if opt_path.exists():
        with open(opt_path) as f:
            opt = json.load(f)
            ax2.scatter(opt['total_storage_mb'], opt['total_utility'], s=100, label=alg)

ax2.set_xlabel('Storage (MB)')
ax2.set_ylabel('Total Utility')
ax2.set_title('Optimization Results: Utility vs Storage')
ax2.legend()
ax2.grid(alpha=0.3)

plt.tight_layout()
plt.savefig('Output/comparison.png', dpi=150)
print("Graph saved to Output/comparison.png")
plt.show()
```

## 🎓 まとめ

### 最も重要なファイル

1. **`Output/{algorithm}/summary.json`** - 全フェーズの実行時間
2. **`Output/{algorithm}/optimization/result.json`** - 最適化結果
3. **`Output/{algorithm}/mv_creation/creation_log.json`** - MV作成ログ

### 確認すべきポイント

- ✅ 各フェーズの実行時間（ボトルネック特定）
- ✅ 選択されたMV数とストレージ使用量
- ✅ MV作成の成功/失敗数
- ✅ 複数アルゴリズムのパフォーマンス比較

### トラブルシューティング

**ファイルが存在しない場合**:
```bash
# そのフェーズがスキップされた可能性があります
# 実行時のログを確認
python scripts/run_experiment.py --algorithms normal --verbose
```

**データが不完全な場合**:
```bash
# クリーンアップして再実行
rm -rf Output/normal/
python scripts/run_experiment.py --algorithms normal
```

---

**作成日**: 2025年10月8日  
**バージョン**: 1.0
