# 時間依存最適化（マイグレーションコスト考慮）の実行手順

このREADMEは、`small_test_ver2` 環境で時間依存最適化（time-dependent optimization with migration costs）を実行するための手順を説明します。

## 目次

- [概要](#概要)
- [クイックスタート](#クイックスタート)
- [コマンドライン引数リファレンス](#コマンドライン引数リファレンス)
- [実行手順（フェーズ別）](#実行手順フェーズ別)
- [入力・出力ファイル](#入力出力ファイル)
- [ディレクトリ構造](#ディレクトリ構造)
- [トラブルシューティング](#トラブルシューティング)

---

## 概要

時間依存最適化は、複数のタイムステップにわたるワークロード変化とマテリアライズドビュー（MV）のマイグレーションコストを考慮して、最適なMV選択を行います。

### 主要な機能
- 時刻ごとに変化するクエリ頻度に対応
- MVの作成・維持・削除のコストを考慮
- 容量制約（ストレージ予算）を満たしながら最適化
- Gurobi を用いた整数線形計画（ILP）による厳密解の導出

### 前提条件
- Python 3.11+
- Gurobi（ライセンス必要）
- PostgreSQL（Docker または ローカル）
- 必要なPythonパッケージ（`requirements.txt`）

---

## クイックスタート

### 1. 最小限の手順

```bash
# 仮想環境をアクティベート
source .venv/bin/activate

# Dockerコンテナを起動
docker start mv_postgres

# 全フェーズを実行（Docker経由）
python experiments/small_test_ver2/scripts/run_experiment_normal.py \
  --phase all \
  --query-set job \
  --use-docker
```

### 2. 典型的な実験コマンド

```bash
# 動的モード + プルーニング + 周期16_2
python experiments/small_test_ver2/scripts/run_experiment_normal.py \
  --phase all \
  --query-set job \
  --optimization-mode dynamic \
  --exp-suffix _16_2 \
  --use-pruning \
  --use-docker
```

---

## コマンドライン引数リファレンス

### 基本引数

| 引数 | 値 | デフォルト | 説明 |
|------|-----|---------|------|
| `--phase` | `all`, `post-opt`, `0`-`9`, `6.5` | 必須 | 実行するフェーズ |
| `--query-set` | 文字列 | `job` | クエリセット名 |
| `--config` | パス | `experiments/small_test_ver2` | 実験ディレクトリ |

### フェーズ一覧

| 値 | 説明 |
|----|------|
| `all` | 全フェーズ（1-9）を順次実行 |
| `post-opt` | Phase 6-9を実行（最適化以降） |
| `0` | データベースセットアップ |
| `1` | EXPLAIN JSON生成 |
| `2` | クエリパース |
| `3` | JSONノードID付加 |
| `4` | マイグレーションプラン列挙 |
| `5` | マイグレーションコスト計算 |
| `6` | ILP最適化（動的/静的） |
| `6.5` | 静的最適化のみ |
| `7` | MV作成SQL生成 |
| `8` | クエリ書き換え |
| `9` | ベンチマーク実行 |

### 最適化・ベンチマーク引数

| 引数 | 値 | デフォルト | 説明 |
|------|-----|---------|------|
| `--optimization-mode` | `dynamic`, `static` | `dynamic` | 最適化モード（Phase 6-8で使用） |
| `--benchmark-mode` | `dynamic`, `static`, `baseline` | `dynamic` | ベンチマークモード（Phase 9で使用） |
| `--use-pruning` | フラグ | - | CF Pruningを使用（大規模データ向け） |
| `--pruning-parallel` | フラグ | - | プルーニングを並列実行 |
| `--pruning-workers` | 整数 | `16` | プルーニング並列実行時のワーカー数 |
| `--static-timestep` | `first`, `last`, `average` | `last` | 静的最適化で使用するタイムステップ |
| `--static-algorithm` | `normal`, `bigsubs`, `both` | `normal` | 静的最適化で使用するアルゴリズム |
| `--exp-suffix` | 文字列 | 空 | 実験識別サフィックス（例: `_16_2`） |

### コスト推定引数

| 引数 | 説明 |
|------|------|
| `--use-neurocard` | NeuroCardを使用してコスト推定 |
| `--use-sampling` | サンプリングを使用してコスト推定 |

### PostgreSQL接続引数

| 引数 | 説明 |
|------|------|
| `--use-docker` | Docker経由でpsqlを実行（デフォルト） |
| `--use-local` | ローカルのpsqlを使用 |

環境変数 `MV_USE_DOCKER=true/false` でデフォルトを変更可能。

### 使用例

```bash
# 基本的な実行（動的モード）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase all --query-set job

# 静的モードで最適化のみ
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 6 --query-set job --optimization-mode static

# ベンチマーク比較（ベースライン）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 9 --query-set job --benchmark-mode baseline

# 大規模データ向け（プルーニング有効）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 6 --query-set job --use-pruning

# 異なる頻度設定の実験
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase all --query-set job --exp-suffix _16_4

# 静的最適化（最初のタイムステップで全実行）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase all --query-set job --optimization-mode static --static-timestep first

# プルーニング並列実行（64ワーカー）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 6 --query-set job --use-pruning --pruning-parallel --pruning-workers 64

# ローカルPostgreSQL使用
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 1 --query-set job --use-local

# BigSubs アルゴリズムで静的最適化
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase post-opt --query-set job --optimization-mode static --static-algorithm bigsubs --static-timestep average --use-docker

# 両アルゴリズム（normal + bigsubs）を実行して比較
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase post-opt --query-set job --optimization-mode static --static-algorithm both --static-timestep average --use-docker
```

---

## 実行手順（フェーズ別）

### Phase 1: EXPLAIN JSON生成

```bash
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 1 --query-set job --use-docker
```

**出力**: `02_json/{query_set}/*.json`

### Phase 2: クエリパース

```bash
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 2 --query-set job
```

**出力**: `03_parsed/{query_set}/qp_class.pkl`, `parse_summary.json`

### Phase 3: JSONノードID付加

```bash
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 3 --query-set job
```

**出力**: `02_json/{query_set}/*.json`（更新）

### Phase 4: マイグレーションプラン列挙

```bash
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 4 --query-set job
```

**出力**: `04_migration/{query_set}/simple_migration_plans.json`

### Phase 5: マイグレーションコスト計算

```bash
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 5 --query-set job
```

**出力**: `04_migration/{query_set}/simple_migration_costs.json`

### Phase 6: ILP最適化

```bash
# 動的モード（デフォルト）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 6 --query-set job --optimization-mode dynamic

# 静的モード（最後のタイムステップ）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 6 --query-set job --optimization-mode static

# 静的モード（最初のタイムステップ）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 6 --query-set job --optimization-mode static --static-timestep first

# プルーニング使用（大規模データ向け）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 6 --query-set job --use-pruning

# プルーニング並列実行（32ワーカー）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 6 --query-set job --use-pruning --pruning-parallel --pruning-workers 32
```

**出力**: `time_dependent_output/{query_set}/td_mv_optimization_result{suffix}.json`

### Phase 6 (静的モード + BigSubs)

```bash
# BigSubs アルゴリズムを使用
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 6 --query-set job --optimization-mode static --static-algorithm bigsubs --static-timestep average

# 通常ILPとBigSubsを両方実行
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 6 --query-set job --optimization-mode static --static-algorithm both --static-timestep average
```

**出力**:
- `normal`: `time_dependent_output/{query_set}/static_mv_optimization_result{suffix}.json`
- `bigsubs`: `time_dependent_output/{query_set}/static_bigsubs_optimization_result{suffix}.json`

### Phase 7: MV作成SQL生成

```bash
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 7 --query-set job --optimization-mode dynamic
```

**出力**: `time_dependent_output/{query_set}/timestep_*_*.sql`

### Phase 8: クエリ書き換え

```bash
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 8 --query-set job --optimization-mode dynamic
```

**出力**: `time_dependent_output/{query_set}/jobs/timestep_*_*/`

### Phase 9: ベンチマーク実行

```bash
# 動的MV
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 9 --query-set job --benchmark-mode dynamic

# 静的MV
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 9 --query-set job --benchmark-mode static

# ベースライン（MVなし）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 9 --query-set job --benchmark-mode baseline
```

**出力**: `time_dependent_output/{query_set}/benchmark_results_{mode}{suffix}.json`

---

## 入力・出力ファイル

### 入力ファイル

| ファイル | 説明 |
|---------|------|
| `01_queries/{query_set}/*.sql` | SQLクエリファイル |
| `01_queries/{query_set}/frequency_time_dependent{suffix}.json` | タイムステップごとの頻度設定 |
| `config.yaml` | 実験環境設定 |

### 出力ファイル

| ファイル | 説明 |
|---------|------|
| `02_json/{query_set}/*.json` | EXPLAIN JSON（ノードID付き） |
| `03_parsed/{query_set}/qp_class.pkl` | パース結果（pickle） |
| `04_migration/{query_set}/simple_migration_*.json` | マイグレーション計画・コスト |
| `time_dependent_output/{query_set}/td_mv_optimization_result{suffix}.json` | 動的最適化結果 |
| `time_dependent_output/{query_set}/static_mv_optimization_result{suffix}.json` | 静的最適化結果（normal） |
| `time_dependent_output/{query_set}/static_bigsubs_optimization_result{suffix}.json` | 静的最適化結果（bigsubs） |
| `time_dependent_output/{query_set}/benchmark_results_*.json` | ベンチマーク結果 |
| `time_dependent_output/{query_set}/benchmark_results_static_bigsubs*.json` | BigSubsベンチマーク結果 |

---

## ディレクトリ構造

```
experiments/small_test_ver2/
├── scripts/                       # 実行スクリプト
│   ├── run_experiment_normal.py   # メインスクリプト
│   └── setup_imdb.py              # DBセットアップ
├── core/                          # コア機能
│   ├── time_dependent_optimizer.py
│   ├── cf_pruner.py               # プルーニング
│   └── io_loaders.py
├── migration/                     # マイグレーション
├── mv_generation/                 # MV生成
├── utils/                         # ユーティリティ
│   └── postgres_executor.py       # Docker/ローカル切り替え
├── 01_queries/                    # クエリ定義
├── 02_json/                       # EXPLAIN出力
├── 03_parsed/                     # パース結果
├── 04_migration/                  # マイグレーション計画
├── time_dependent_output/         # 最適化結果
└── config.yaml
```

---

## トラブルシューティング

### psqlコマンドが見つからない

```
[Errno 2] No such file or directory: 'psql'
```

**解決策**: Dockerモードを使用

```bash
docker start mv_postgres
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 1 --use-docker
```

### Gurobiライセンスエラー

- 学術ライセンスを取得: https://www.gurobi.com/
- `gurobi.lic` をプロジェクトルートに配置
- 環境変数 `GRB_LICENSE_FILE` を設定

### pickleファイルが見つからない

Phase 2（クエリパース）を先に実行してください：

```bash
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 2 --query-set job
```

### PostgreSQL接続エラー

```bash
# Dockerコンテナの状態確認
docker ps | grep mv_postgres

# コンテナを起動
docker start mv_postgres

# ログ確認
docker logs mv_postgres | tail -20
```

---

## 実験設定のカスタマイズ

### ストレージ予算の変更

`core/time_dependent_optimizer.py` または スクリプト内の `B_max` を編集。

### 頻度設定の変更

`01_queries/{query_set}/frequency_time_dependent{suffix}.json` を編集。

### 新しいクエリセットの追加

1. `01_queries/new_set/` を作成
2. SQLファイルを配置
3. `frequency_time_dependent.json` を作成
4. `--query-set new_set` で実行

### プルーニング並列化の推奨設定

- **小規模データ（~100候補）**: `--pruning-workers 16`（デフォルト）
- **中規模データ（~500候補）**: `--pruning-workers 32`
- **大規模データ（1000+候補）**: `--pruning-workers 48-64`

注意: Gurobiは各ILPを1スレッドで解くため、ワーカー数を増やしても線形にスケールしない場合があります。

### 静的最適化のタイムステップ選択

- `--static-timestep first`: 最初のタイムステップ（開始時点）のワークロードで最適化
- `--static-timestep last`: 最後のタイムステップ（終了時点）のワークロードで最適化

全フェーズ実行（`--phase all`）や部分実行（`--phase post-opt`）でも使用可能です。

### 静的最適化アルゴリズムの選択

- `--static-algorithm normal`: 通常のILP最適化（Gurobi）
- `--static-algorithm bigsubs`: BigSubsヒューリスティック最適化
- `--static-algorithm both`: 両方を実行して比較

各アルゴリズムの結果は別ファイルに保存され、ベンチマークも独立して実行可能です。

---

## 参考

- ILP定式化: `small_docs/explain/time_dependent_optimizer.md`
- プロジェクト概要: `docs/`

## 便利なSQLクエリ

### MVサイズ一覧

```sql
SELECT matviewname AS mv_name,
       pg_size_pretty(pg_total_relation_size(pg_class.oid)) AS total_size
FROM pg_matviews
JOIN pg_class ON pg_class.relname = pg_matviews.matviewname
WHERE pg_class.relkind = 'm'
ORDER BY pg_total_relation_size(pg_class.oid) DESC;
```

### MV合計サイズ

```sql
SELECT pg_size_pretty(SUM(pg_total_relation_size(pg_class.oid))) AS total_mv_size
FROM pg_matviews
JOIN pg_class ON pg_class.relname = pg_matviews.matviewname
WHERE pg_class.relkind = 'm';
```

python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase post-opt --query-set job --optimization-mode dynamic --exp-suffix _16_4 --use-pruning --pruning-parallel --use-docker