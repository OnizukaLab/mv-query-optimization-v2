# 実験結果の出力ファイル一覧

各フェーズで生成されるファイルとその保存場所をまとめます。

## 📂 ディレクトリ構造（新バージョン）

```
Output/
├── qp_class.pkl                          # [Phase 1] クエリパース結果
│
├── {algorithm}/                          # アルゴリズムごとの結果
│   ├── optimization/                     # [Phase 2] 最適化結果
│   │   ├── result.json                   # 最適化結果（詳細）
│   │   └── mv_list.csv                   # 選択されたMVリスト（旧形式互換）
│   │
│   ├── mv_creation/                      # [Phase 3] MV作成結果
│   │   └── creation_log.json             # MV作成ログと実行時間
│   │
│   ├── query_rewrite/                    # [Phase 4] クエリ書き換え結果
│   │   └── rewrite_log.json              # 書き換えログと実行時間
│   │
│   └── summary.json                      # 全フェーズの統合サマリー
│
└── query_rewrite/                        # クエリ書き換え後のSQLファイル
    └── re_sql/
        ├── normal/
        │   ├── 1a.sql
        │   ├── 1b.sql
        │   └── ...
        ├── bigsubs/
        ├── utility/
        ├── utility_capacity/
        └── frequency/
```

**例: normalアルゴリズムの場合**
```
Output/normal/
├── optimization/
│   ├── result.json
│   └── mv_list.csv
├── mv_creation/
│   └── creation_log.json
├── query_rewrite/
│   └── rewrite_log.json
└── summary.json
```

---

## フェーズ別の出力詳細

### [Phase 1] クエリパース (Query Parsing)

#### 📄 `Output/qp_class.pkl`

**内容**: QueryParserオブジェクトのシリアライズファイル

**形式**: Python pickle形式

**含まれる情報**:
- `qm` (QueryManager): クエリノード管理情報
- `s_num`: サブクエリノード総数
- `m_cost`: 各ノードのメンテナンスコスト
- `node_list`: 全ノードIDリスト
- `b_j`: 各ノードのストレージサイズ
- `u_ij`: 効用行列（クエリ×ノード）
- `X`: 依存関係行列
- `q_s_list`: クエリ-サブクエリ関係行列

**用途**: 
- 2回目以降の実験で再パースを省略
- 他のフェーズの入力データとして使用

**読み込み例**:
```python
import pickle
with open('Output/qp_class.pkl', 'rb') as f:
    qp = pickle.load(f)
    print(f"Total nodes: {qp.s_num}")
    print(f"Query count: {len(qp.u_ij)}")
```

---

### [Phase 2] ILP最適化 (MV Selection)

#### � `Output/{algorithm}/optimization/result.json`

**内容**: 最適化アルゴリズムの実行結果（詳細情報）

**形式**: JSON形式

**ファイル例**: `Output/normal/optimization/result.json`

**JSON構造**:
```json
{
  "algorithm": "normal",
  "total_utility": 12345.67,
  "total_storage": 48000000,
  "total_storage_mb": 45.78,
  "execution_time": 123.45,
  "num_selected_views": 42,
  "selected_views": [
    {
      "view_id": "mv_leaf_15",
      "node_id": "leaf_15",
      "size": 5242880,
      "size_mb": 5.0,
      "maintenance_cost": 12.34,
      "usage_count": 5
    },
    {
      "view_id": "mv_non_leaf_42",
      "node_id": "non_leaf_42",
      "size": 10485760,
      "size_mb": 10.0,
      "maintenance_cost": 23.45,
      "usage_count": 3
    }
  ],
  "metadata": {
    "storage_limit_mb": 50,
    "num_queries": 113
  }
}
```

**含まれる情報**:
- `algorithm`: 使用したアルゴリズム名
- `total_utility`: 総効用（利得 - コスト）
- `total_storage`: 総ストレージ使用量（バイト）
- `total_storage_mb`: 総ストレージ使用量（MB）
- `execution_time`: 最適化の実行時間（秒）
- `num_selected_views`: 選択されたMV数
- `selected_views`: 選択されたMVの詳細リスト
  - `view_id`: ビューID
  - `node_id`: ノードID
  - `size`: サイズ（バイト）
  - `size_mb`: サイズ（MB）
  - `maintenance_cost`: メンテナンスコスト
  - `usage_count`: 使用されるクエリ数
- `metadata`: その他のメタデータ

#### � `Output/{algorithm}/optimization/mv_list.csv`

**内容**: 選択されたMVリスト（旧形式互換）

**形式**: CSV形式

**ファイル例**: `Output/normal/optimization/mv_list.csv`

**CSVフォーマット**:
```csv
leaf_15,non_leaf_42
leaf_3,leaf_7,non_leaf_8
NONE
leaf_15
...
```

**説明**:
- 各行がクエリに対応（0行目 = クエリ0, 1行目 = クエリ1, ...）
- そのクエリで使用するMVのノードIDがカンマ区切りで記載
- MVを使用しない場合は `NONE`

**用途**: 
- 旧実装との互換性維持
- 簡易的なMVマッピング確認

**読み込み例**:
```python
import json

with open('Output/normal/optimization/result.json', 'r') as f:
    result = json.load(f)
    print(f"Algorithm: {result['algorithm']}")
    print(f"Selected MVs: {result['num_selected_views']}")
    print(f"Total Utility: {result['total_utility']:.2f}")
    print(f"Storage Used: {result['total_storage_mb']:.2f} MB")
    print(f"Optimization Time: {result['execution_time']:.2f} seconds")
```

---

### [Phase 3] MV作成 (MV Creation)

#### 🗄️ PostgreSQLデータベース内

選択されたマテリアライズドビューは**PostgreSQLデータベース内**に実際に作成されます。

**作成場所**: `imdbload`データベースの`public`スキーマ

**ビュー名のパターン**:
- リーフノード: `mv_leaf_{id}` (例: `mv_leaf_15`)
- 非リーフノード: `mv_non_leaf_{id}` (例: `mv_non_leaf_42`)

**確認方法**:
```sql
-- データベースに接続
psql -h localhost -p 5432 -U postgres -d imdbload

-- 作成されたMVを一覧表示
SELECT matviewname, 
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||matviewname)) as size
FROM pg_matviews 
WHERE schemaname = 'public'
ORDER BY matviewname;

-- 特定のMVの定義を確認
\d+ mv_leaf_15

-- MVのデータ件数確認
SELECT count(*) FROM mv_leaf_15;
```

#### 📊 `Output/{algorithm}/mv_creation/creation_log.json`

**内容**: MV作成の詳細ログと実行時間

**形式**: JSON形式

**ファイル例**: `Output/normal/mv_creation/creation_log.json`

**JSON構造**:
```json
{
  "total_mvs": 42,
  "created": 40,
  "failed": 2,
  "total_time": 456.78,
  "mvs": [
    {
      "view_id": "mv_leaf_15",
      "node_id": "leaf_15",
      "status": "SUCCESS",
      "creation_time": 2.34,
      "size_mb": 5.0
    },
    {
      "view_id": "mv_non_leaf_42",
      "node_id": "non_leaf_42",
      "status": "SUCCESS",
      "creation_time": 12.56,
      "size_mb": 10.0
    },
    {
      "view_id": "mv_non_leaf_99",
      "node_id": "non_leaf_99",
      "status": "ERROR",
      "creation_time": 0.05,
      "error": "timeout exceeded"
    }
  ]
}
```

**含まれる情報**:
- `total_mvs`: 作成を試みたMV総数
- `created`: 成功したMV数
- `failed`: 失敗したMV数
- `total_time`: 総実行時間（秒）
- `mvs`: 各MVの作成詳細
  - `view_id`: ビューID
  - `node_id`: ノードID
  - `status`: 作成状態（SUCCESS/FAILED/ERROR）
  - `creation_time`: 作成にかかった時間（秒）
  - `size_mb`: MVのサイズ（MB）
  - `error`: エラーメッセージ（失敗時のみ）

**用途**:
- MV作成のボトルネック分析
- 失敗したMVの特定
- データベースパフォーマンス評価

**読み込み例**:
```python
import json

with open('Output/normal/mv_creation/creation_log.json', 'r') as f:
    log = json.load(f)
    print(f"Created: {log['created']}/{log['total_mvs']} MVs")
    print(f"Total time: {log['total_time']:.2f} seconds")
    print(f"Average time per MV: {log['total_time']/log['total_mvs']:.2f} seconds")
    
    # 失敗したMVをリストアップ
    failed = [mv for mv in log['mvs'] if mv['status'] != 'SUCCESS']
    for mv in failed:
        print(f"Failed: {mv['view_id']} - {mv.get('error', 'unknown error')}")
```

---

### [Phase 4] クエリ書き換え (Query Rewriting)

#### 📂 `Output/query_rewrite/re_sql/{algorithm}/`

各アルゴリズムごとに書き換えられたクエリSQLファイルが保存されます。

**ディレクトリ構造**:
```
Output/query_rewrite/re_sql/
├── normal/
│   ├── 1a.sql
│   ├── 1b.sql
│   ├── 1c.sql
│   ├── 2a.sql
│   └── ...
├── bigsubs/
│   ├── 1a.sql
│   └── ...
├── utility/
├── utility_capacity/
└── frequency/
```

**ファイル形式**: 標準SQLファイル（`.sql`）

**ファイル名**: 元のクエリIDに対応（例: `1a.sql`, `2b.sql`）

**内容例** (`Output/query_rewrite/re_sql/normal/1a.sql`):

**元のクエリ**:
```sql
SELECT t.title, mi.info
FROM title t
JOIN movie_info mi ON t.id = mi.movie_id
WHERE t.production_year > 2000
  AND mi.info_type_id = 3;
```

**書き換え後**:
```sql
-- Original query rewritten using materialized views
-- MVs used: mv_leaf_15, mv_non_leaf_42

SELECT t.title, mi.info
FROM mv_leaf_15 t  -- title テーブルを mv_leaf_15 に置換
JOIN movie_info mi ON t.id = mi.movie_id
WHERE mi.info_type_id = 3;
```

#### 📊 `Output/{algorithm}/query_rewrite/rewrite_log.json`

**内容**: クエリ書き換えの詳細ログと実行時間

**形式**: JSON形式

**ファイル例**: `Output/normal/query_rewrite/rewrite_log.json`

**JSON構造**:
```json
{
  "total_queries": 113,
  "total_time": 3.45,
  "output_directory": "Output/query_rewrite/re_sql/normal",
  "queries": [
    {
      "query_id": "1a",
      "output_file": "Output/query_rewrite/re_sql/normal/1a.sql",
      "rewrite_time": 0.0234
    },
    {
      "query_id": "1b",
      "output_file": "Output/query_rewrite/re_sql/normal/1b.sql",
      "rewrite_time": 0.0156
    },
    {
      "query_id": "1c",
      "output_file": "Output/query_rewrite/re_sql/normal/1c.sql",
      "rewrite_time": 0.0198
    }
  ]
}
```

**含まれる情報**:
- `total_queries`: 書き換えたクエリ総数
- `total_time`: 総実行時間（秒）
- `output_directory`: 書き換えたSQLファイルの出力先
- `queries`: 各クエリの書き換え詳細
  - `query_id`: クエリID
  - `output_file`: 出力ファイルパス
  - `rewrite_time`: 書き換えにかかった時間（秒）

**用途**:
- 書き換え処理のパフォーマンス分析
- 各クエリの処理時間確認

**読み込み例**:
```python
import json
from pathlib import Path

algorithm = "normal"

# ログファイルを読み込み
with open(f'Output/{algorithm}/query_rewrite/rewrite_log.json', 'r') as f:
    log = json.load(f)
    print(f"Total queries rewritten: {log['total_queries']}")
    print(f"Total time: {log['total_time']:.2f} seconds")
    print(f"Average time per query: {log['total_time']/log['total_queries']:.4f} seconds")

# 特定のクエリを読み込み
query_id = "1a"
sql_path = Path(f"Output/query_rewrite/re_sql/{algorithm}/{query_id}.sql")
with open(sql_path, 'r') as f:
    rewritten_sql = f.read()
    print(f"\nRewritten query {query_id}:")
    print(rewritten_sql)
```

---

---

## 📊 統合サマリーファイル

### `Output/{algorithm}/summary.json`

**内容**: 全フェーズの統合実行結果

**形式**: JSON形式

**ファイル例**: `Output/normal/summary.json`

**JSON構造**:
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

**含まれる情報**:
- `algorithm`: 使用したアルゴリズム名
- `total_execution_time`: 全フェーズの総実行時間（秒）
- `phases`: 各フェーズの実行時間（秒）
  - `optimization`: Phase 2の実行時間
  - `mv_creation`: Phase 3の実行時間
  - `query_rewriting`: Phase 4の実行時間
- `timestamp`: 実行日時

**用途**:
- 複数アルゴリズムのパフォーマンス比較
- ボトルネック特定
- 実行履歴の記録

**読み込み例**:
```python
import json

algorithms = ['normal', 'bigsubs', 'utility', 'utility_capacity', 'frequency']

print("Algorithm Performance Comparison:")
print("-" * 80)
print(f"{'Algorithm':<20} {'Optimization':>15} {'MV Creation':>15} {'Rewriting':>15} {'Total':>15}")
print("-" * 80)

for alg in algorithms:
    try:
        with open(f'Output/{alg}/summary.json', 'r') as f:
            summary = json.load(f)
            phases = summary['phases']
            print(f"{alg:<20} "
                  f"{phases.get('optimization', 0):>15.2f} "
                  f"{phases.get('mv_creation', 0):>15.2f} "
                  f"{phases.get('query_rewriting', 0):>15.2f} "
                  f"{summary['total_execution_time']:>15.2f}")
    except FileNotFoundError:
        print(f"{alg:<20} {'Not executed':>15}")
```

---

## 🔍 出力ファイルの確認方法

### 全体の出力を確認

```bash
# ディレクトリ構造を表示
tree Output/

# 各アルゴリズムの結果確認
for alg in normal bigsubs utility utility_capacity frequency; do
    echo "=== $alg ==="
    if [ -f "Output/$alg/summary.json" ]; then
        cat "Output/$alg/summary.json" | jq '{algorithm, total_execution_time, phases}'
    else
        echo "Not executed"
    fi
    echo ""
done

# 各アルゴリズムの書き換えクエリ数
for alg in normal bigsubs utility utility_capacity frequency; do
    count=$(find Output/query_rewrite/re_sql/$alg -type f -name "*.sql" 2>/dev/null | wc -l)
    echo "$alg: $count queries"
done
```

### 特定フェーズの結果を確認

```bash
# [Phase 1] パース結果
python -c "
import pickle
with open('Output/qp_class.pkl', 'rb') as f:
    qp = pickle.load(f)
    print(f'Total subquery nodes: {qp.s_num}')
    print(f'Query count: {len(qp.u_ij)}')
"

# [Phase 2] 最適化結果
cat Output/normal/optimization/result.json | jq '{algorithm, num_selected_views, total_utility, total_storage_mb, execution_time}'

# [Phase 3] MV作成結果
cat Output/normal/mv_creation/creation_log.json | jq '{total_mvs, created, failed, total_time}'

# [Phase 4] クエリ書き換え結果
cat Output/normal/query_rewrite/rewrite_log.json | jq '{total_queries, total_time}'

# [統合] サマリー
cat Output/normal/summary.json | jq '.'

# データベース内のMV確認
psql -h localhost -p 5432 -U postgres -d imdbload -c "
    SELECT count(*) as mv_count 
    FROM pg_matviews 
    WHERE schemaname = 'public';
"

# 書き換えクエリのサンプル
cat Output/query_rewrite/re_sql/normal/1a.sql
```

### 複数アルゴリズムの比較

```bash
# 最適化結果の比較
echo "Algorithm,Selected MVs,Total Utility,Storage (MB),Time (sec)"
for alg in normal bigsubs utility utility_capacity frequency; do
    if [ -f "Output/$alg/optimization/result.json" ]; then
        cat "Output/$alg/optimization/result.json" | jq -r '"\(.algorithm),\(.num_selected_views),\(.total_utility),\(.total_storage_mb),\(.execution_time)"'
    fi
done

# MV作成結果の比較
echo -e "\nAlgorithm,Total MVs,Created,Failed,Time (sec)"
for alg in normal bigsubs utility utility_capacity frequency; do
    if [ -f "Output/$alg/mv_creation/creation_log.json" ]; then
        cat "Output/$alg/mv_creation/creation_log.json" | jq -r '"\($alg),\(.total_mvs),\(.created),\(.failed),\(.total_time)"' --arg alg "$alg"
    fi
done
```

---

## 📋 出力ファイルのクリーンアップ

実験前に古い結果をクリアする場合：

```bash
# 特定アルゴリズムの結果を削除
rm -rf Output/normal/

# 全アルゴリズムの結果を削除
rm -rf Output/*/

# クエリパース結果を削除（再パース必要）
rm -f Output/qp_class.pkl

# 書き換えクエリを削除
rm -rf Output/query_rewrite/re_sql/*/

# データベース内のMVを削除
psql -h localhost -p 5432 -U postgres -d imdbload -c "
    DO \$\$ 
    DECLARE r RECORD;
    BEGIN
        FOR r IN SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'
        LOOP
            EXECUTE 'DROP MATERIALIZED VIEW IF EXISTS ' || r.matviewname || ' CASCADE';
        END LOOP;
    END \$\$;
"

# または run_experiment.py が自動でクリーンアップ
python scripts/run_experiment.py --algorithms normal
# ↑ 実行前に cleanup_mv_files() が呼ばれる
```

---

## 🎯 まとめ

| フェーズ | 保存場所 | ファイル形式 | 主な内容 |
|---------|---------|------------|---------|
| **[1] クエリパース** | `Output/qp_class.pkl` | pickle | 解析データのキャッシュ |
| **[2] MV選択** | `Output/{algorithm}/optimization/` | JSON, CSV | 選択されたMV、効用、実行時間 |
| **[3] MV作成** | PostgreSQL DB + `Output/{algorithm}/mv_creation/` | DB + JSON | 作成されたMV、作成ログ、実行時間 |
| **[4] クエリ書き換え** | `Output/query_rewrite/re_sql/{algorithm}/` + `Output/{algorithm}/query_rewrite/` | SQL + JSON | 書き換え後クエリ、ログ、実行時間 |
| **[5] ベンチマーク** | 未実装 | - | 性能測定結果（予定） |
| **統合サマリー** | `Output/{algorithm}/summary.json` | JSON | 全フェーズの実行時間 |

**新機能の特徴**:
- ✅ **Phase 2の結果がJSON/CSVで保存される**
- ✅ **Phase 3の実行時間とMVごとの作成時間が記録される**
- ✅ **Phase 4の実行時間とクエリごとの書き換え時間が記録される**
- ✅ **統合サマリーで全体のパフォーマンスが一目で確認できる**

---

**作成日**: 2025年10月8日  
**バージョン**: 2.0  
**更新内容**: 新しい出力構造に対応、各フェーズの実行時間記録機能を追加

#### ⚠️ 現在の実装状況

**注意**: `src/`モジュールでのベンチマーク実行機能は**未実装**です。

```python
# [5/5] 書き換えられたクエリの実行
if settings.execution.should_run_phase('benchmark'):
    logger.info("[5/5] Executing rewritten queries...")
    # TODO: ベンチマーク実行機能を src/ に実装
    logger.warning("Benchmark execution not yet implemented in src/ modules")
```

#### 📊 旧実装での出力ファイル（参考）

旧実装（`execute_rewritten.py`, RedBenchなど）では以下のファイルが生成されていました：

**`Output/redbench/{algorithm}.out`**:
```
Output/redbench/
├── normal.out
├── bigsubs.out
├── utility.out
├── utility_capacity.out
└── frequency.out
```

**ファイル内容例** (`Output/redbench/normal.out`):
```
Query 1a: 234.56 ms
Query 1b: 123.45 ms
Query 1c: 345.67 ms
...
Total execution time: 12345.67 ms
Average query time: 109.34 ms
```

**実行結果ログ** (`Output/query_rewrite/{algorithm}.out`):
```
Executing query 1a... 234.56 ms
Executing query 1b... 123.45 ms
Executing query 1c... 345.67 ms
...
Completed 113 queries in 12.35 seconds
```

#### 🚀 今後の実装予定

ベンチマーク機能は以下の形式で実装予定：

**`Output/benchmark/{algorithm}/results.json`**:
```json
{
  "algorithm": "normal",
  "total_queries": 113,
  "total_time_ms": 12345.67,
  "average_time_ms": 109.34,
  "queries": [
    {
      "query_id": "1a",
      "execution_time_ms": 234.56,
      "rows_returned": 1523,
      "cache_hit": false
    },
    {
      "query_id": "1b",
      "execution_time_ms": 123.45,
      "rows_returned": 872,
      "cache_hit": true
    }
  ]
}
```

**`Output/benchmark/{algorithm}/summary.csv`**:
```csv
query_id,execution_time_ms,rows_returned,cache_hit
1a,234.56,1523,false
1b,123.45,872,true
1c,345.67,2341,false
...
```

---

## 🔍 出力ファイルの確認方法

### 全体の出力を確認

```bash
# ディレクトリ構造を表示
tree Output/

# ファイル一覧とサイズ
find Output/ -type f -exec ls -lh {} \;

# 各アルゴリズムの書き換えクエリ数
for alg in normal bigsubs utility utility_capacity frequency; do
    count=$(find Output/query_rewrite/re_sql/$alg -type f -name "*.sql" 2>/dev/null | wc -l)
    echo "$alg: $count queries"
done
```

### 特定フェーズの結果を確認

```bash
# [Phase 1] パース結果
python -c "
import pickle
with open('Output/qp_class.pkl', 'rb') as f:
    qp = pickle.load(f)
    print(f'Total subquery nodes: {qp.s_num}')
    print(f'Query count: {len(qp.u_ij)}')
"

# [Phase 3] データベース内のMV
psql -h localhost -p 5432 -U postgres -d imdbload -c "
    SELECT count(*) as mv_count 
    FROM pg_matviews 
    WHERE schemaname = 'public';
"

# [Phase 4] 書き換えクエリのサンプル
cat Output/query_rewrite/re_sql/normal/1a.sql
```

---

## 📋 出力ファイルのクリーンアップ

実験前に古い結果をクリアする場合：

```bash
# クエリパース結果を削除（再パース必要）
rm -f Output/qp_class.pkl

# 特定アルゴリズムの書き換え結果を削除
rm -rf Output/query_rewrite/re_sql/normal/

# 全アルゴリズムの結果を削除
rm -rf Output/query_rewrite/re_sql/*/

# データベース内のMVを削除
psql -h localhost -p 5432 -U postgres -d imdbload -c "
    DO \$\$ 
    DECLARE r RECORD;
    BEGIN
        FOR r IN SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'
        LOOP
            EXECUTE 'DROP MATERIALIZED VIEW IF EXISTS ' || r.matviewname || ' CASCADE';
        END LOOP;
    END \$\$;
"

# または run_experiment.py が自動でクリーンアップ
python scripts/run_experiment.py --algorithms normal
# ↑ 実行前に cleanup_mv_files() が呼ばれる
```

---

## 🎯 まとめ

| フェーズ | 保存場所 | ファイル形式 | 用途 |
|---------|---------|------------|------|
| **[1] クエリパース** | `Output/qp_class.pkl` | pickle | 解析データのキャッシュ |
| **[2] MV選択** | メモリ内（`OptimizationResult`） | - | 次フェーズへ渡す |
| **[3] MV作成** | PostgreSQLデータベース | MATERIALIZED VIEW | クエリ実行の高速化 |
| **[4] クエリ書き換え** | `Output/query_rewrite/re_sql/{algorithm}/` | `.sql` | 書き換え後のクエリ |
| **[5] ベンチマーク** | 未実装（`Output/redbench/`予定） | `.out`, `.json` | 性能測定結果 |

**重要な注意点**:
- **Phase 2の結果はファイル保存されない** → メモリ内で保持され、Phase 3/4に渡される
- **Phase 3の結果はデータベース内** → SQLファイルではなくDBに直接作成
- **Phase 5は未実装** → 今後の拡張予定

---

**作成日**: 2025年10月8日  
**バージョン**: 1.0
