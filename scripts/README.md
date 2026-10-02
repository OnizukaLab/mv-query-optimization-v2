# Scripts Usage Guide

このディレクトリには、実験実行のためのスクリプトが含まれています。

## スクリプト一覧

### 1. `run_experiment.py`
メインの実験実行スクリプト。複数のILPアルゴリズムで最適化を実行します。

#### 基本的な使い方

```bash
# デフォルト設定で実行（normalアルゴリズム）
python scripts/run_experiment.py

# 複数のアルゴリズムを実行
python scripts/run_experiment.py --algorithms normal bigsubs utility

# すべてのアルゴリズムを実行
python scripts/run_experiment.py --algorithms normal bigsubs utility utility_capacity frequency

# MV作成をスキップ（既にMVが作成済みの場合）
python scripts/run_experiment.py --skip-mv-creation

# ベンチマークをスキップ
python scripts/run_experiment.py --skip-benchmark

# 詳細出力
python scripts/run_experiment.py --verbose

# CSV初期化を含む完全実行
python scripts/run_experiment.py --initialize --algorithms normal bigsubs
```

#### オプション

- `--algorithms`: 実行するアルゴリズム（複数可）
  - `none`: MVなし
  - `normal`: Normal ILP
  - `bigsubs`: BigSubs ILP
  - `utility`: Utility-based
  - `utility_capacity`: Utility-Capacity
  - `frequency`: Frequency-based
- `--output`: 出力ディレクトリ（デフォルト: `Output`）
- `--skip-mv-creation`: MV作成をスキップ
- `--skip-rewrite`: クエリ書き換えをスキップ
- `--skip-benchmark`: ベンチマーク実行をスキップ
- `--verbose`: 詳細な出力を表示
- `--initialize`: 実行前にCSV比較を初期化

---

### 2. `rewrite_queries.py`
クエリ書き換え専用スクリプト。既存のMV選択結果を使ってクエリを書き換えます。

#### 基本的な使い方

```bash
# Normal ILPの結果でクエリ書き換え
python scripts/rewrite_queries.py normal

# BigSubs ILPの結果でクエリ書き換え
python scripts/rewrite_queries.py bigsubs

# カスタムMVリストを使用
python scripts/rewrite_queries.py normal --mv-list path/to/mv_y_list.csv

# カスタム出力ディレクトリ
python scripts/rewrite_queries.py normal --output Output/my_rewrite

# QueryManager状態を指定
python scripts/rewrite_queries.py normal --qm-state path/to/qm_state.pkl
```

#### オプション

- `ilp_type`: ILPアルゴリズムタイプ（必須）
- `--mv-list`: MV選択結果CSVファイル
- `--output`: 出力ディレクトリ
- `--qm-state`: QueryManager状態ファイル（pickle）

---

### 3. `compare_algorithms.py`
複数のアルゴリズムの結果を比較するスクリプト。

#### 基本的な使い方

```bash
# デフォルトアルゴリズムで比較
python scripts/compare_algorithms.py --results Output

# 特定のアルゴリズムを比較
python scripts/compare_algorithms.py --results Output --algorithms normal bigsubs utility

# 結果をCSVにエクスポート
python scripts/compare_algorithms.py --results Output --output comparison.csv
```

#### オプション

- `--results`: 結果ディレクトリ（デフォルト: `Output`）
- `--algorithms`: 比較するアルゴリズム（複数可）
- `--output`: 比較結果をCSVで出力

#### 出力例

```
================================================================================
Algorithm Comparison
================================================================================

Algorithm            Total MVs       Queries with MVs    
--------------------------------------------------------------------------------
normal               45              28                  
bigsubs              32              24                  
utility              52              31                  
================================================================================
```

---

### 4. `setup_database.py`
データベースのセットアップスクリプト。

#### 基本的な使い方

```bash
# スキーマのセットアップ
python scripts/setup_database.py --schema data/schema.sql

# データロード
python scripts/setup_database.py --data data/setup.sql

# トリガーのセットアップ
python scripts/setup_database.py --triggers data/triggers.sql

# 既存MVを削除
python scripts/setup_database.py --drop-existing

# 完全なクリーンセットアップ
python scripts/setup_database.py --clean --schema data/schema.sql --data data/setup.sql

# 詳細出力
python scripts/setup_database.py --verbose --schema data/schema.sql
```

#### オプション

- `--schema`: スキーマSQLファイル
- `--data`: データSQLファイル
- `--triggers`: トリガーSQLファイル
- `--drop-existing`: 既存のMVを削除
- `--clean`: クリーンセットアップ（MV削除 + スキーマ再作成）
- `--verbose`: 詳細な出力を表示

---

## 典型的なワークフロー

### 1. 初回セットアップ

```bash
# データベースセットアップ
python scripts/setup_database.py --schema data/schema.sql --data data/setup.sql

# 実験実行
python scripts/run_experiment.py --initialize --algorithms normal bigsubs
```

### 2. 追加のアルゴリズムを実行

```bash
# 既存のMVをクリーンアップして実行
python scripts/setup_database.py --drop-existing
python scripts/run_experiment.py --algorithms utility utility_capacity
```

### 3. 結果の比較

```bash
# コンソールに表示
python scripts/compare_algorithms.py --results Output

# CSVにエクスポート
python scripts/compare_algorithms.py --results Output --output results_comparison.csv
```

### 4. 特定のアルゴリズムのクエリ書き換えのみ

```bash
# MVは既に作成済みで、クエリ書き換えのみ実行
python scripts/rewrite_queries.py normal --mv-list Output/normal/mv_y_list.csv
```

---

## トラブルシューティング

### スクリプトが見つからない

```bash
# プロジェクトルートから実行していることを確認
cd /path/to/mv-query-optimization
python scripts/run_experiment.py
```

### モジュールのインポートエラー

```bash
# PYTHONPATHを設定
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
python scripts/run_experiment.py
```

### データベース接続エラー

- `.env` ファイルでデータベース接続情報が正しく設定されているか確認
- PostgreSQLが起動しているか確認
- データベースが存在するか確認

---

## 注意事項

1. **MVの削除**: 実験間でMVをクリーンアップしないと、古いMVが残り結果に影響します
2. **ディスク容量**: MVは大量のディスク容量を使用します。定期的にクリーンアップしてください
3. **実行時間**: ベンチマークは時間がかかります。`--skip-benchmark` オプションで省略可能
4. **並列実行**: 複数の実験を同時に実行すると、データベースの状態が競合する可能性があります

---

## 既存スクリプトとの互換性

新しいスクリプトは既存の `experiment.py` と互換性がありますが、より柔軟な実行が可能です：

### 旧スクリプト
```bash
python experiment.py
```

### 新スクリプト（同等）
```bash
python scripts/run_experiment.py --initialize --algorithms none normal bigsubs utility_capacity utility frequency
```

### 新スクリプト（カスタマイズ）
```bash
# 特定のアルゴリズムのみ、ベンチマークなし
python scripts/run_experiment.py --algorithms normal bigsubs --skip-benchmark
```
