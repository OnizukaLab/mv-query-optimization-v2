# フェーズ分離: 最適化とSQL生成の分離

## 概要

Phase 2 (optimization) からMV作成SQL生成機能を分離し、新しい Phase 3 (sql_generation) として独立させました。

## 変更内容

### フェーズ構成の変更

**変更前 (5フェーズ)**
1. [1/5] クエリパース
2. [2/5] MV選択（ILP最適化）+ SQL生成 ← ここで両方を実行
3. [3/5] MV作成（データベース）
4. [4/5] クエリ書き換え
5. [5/5] ベンチマーク実行

**変更後 (6フェーズ)**
1. [1/6] クエリパース
2. [2/6] MV選択（ILP最適化）← 最適化のみ
3. [3/6] MV作成SQL生成 ← 新しいフェーズ
4. [4/6] MV作成（データベース）
5. [5/6] クエリ書き換え
6. [6/6] ベンチマーク実行

## フェーズの詳細

### Phase 2: 最適化 (optimization)
- **目的**: ILPアルゴリズムでMVを選択
- **入力**: クエリパース結果 (`qp_class.pkl`)
- **出力**: 
  - `Output/{algorithm}/optimization/result.json` (選択されたMV情報、SQLなし)
  - `Output/{algorithm}/optimization/mv_list.csv`
- **SQL生成**: なし（view_idとnode_idのみ保存）

### Phase 3: SQL生成 (sql_generation)
- **目的**: 選択されたMVの作成SQL生成
- **入力**: Phase 2の最適化結果
- **出力**:
  - `Output/{algorithm}/sql/{view_id}.sql` (各MVのSQL)
  - `Output/{algorithm}/optimization/result.json` (SQLを追加)
- **使用クラス**: `EnhancedMVGenerator`, `SchemaProvider`

### Phase 4: MV作成 (mv_creation)
- **目的**: データベースにMVを作成
- **入力**: Phase 3のSQL
- **出力**: データベース上のMV

## 使用方法

### 個別フェーズの実行

```bash
# Phase 2のみ実行（最適化）
python scripts/run_experiment.py --algorithms bigsubs --phases optimization

# Phase 3のみ実行（SQL生成）
python scripts/run_experiment.py --algorithms bigsubs --phases sql_generation

# Phase 2と3を連続実行
python scripts/run_experiment.py --algorithms bigsubs --phases optimization sql_generation
```

### 範囲指定での実行

```bash
# Phase 2から4まで実行
python scripts/run_experiment.py --algorithms bigsubs --start-from optimization --end-at mv_creation
```

### YAMLでの設定

```yaml
# config/default.yaml
execution:
  phases:
    query_parsing: false
    optimization: true      # Phase 2
    sql_generation: true    # Phase 3 (新規)
    mv_creation: false
    query_rewriting: false
    benchmark: false
```

## メリット

1. **関心の分離**: 最適化とSQL生成を独立して実行可能
2. **デバッグしやすさ**: SQL生成だけを再実行できる
3. **柔軟性**: 最適化結果を保存してSQL生成を後で実行可能
4. **テスト容易性**: 各フェーズを個別にテスト可能

## 注意事項

- Phase 3をスキップすると、Phase 4でSQLが見つからない警告が表示されます
- Phase 2の結果は `create_sql` が空の状態で保存されます
- Phase 3実行後、`result.json` は `create_sql` を含む状態に更新されます

## ファイル構造

```
Output/{algorithm}/
├── optimization/
│   ├── result.json          # Phase 2: SQLなし → Phase 3: SQLあり
│   └── mv_list.csv          # Phase 2で生成
├── sql/                     # Phase 3で生成
│   ├── leaf_1.sql
│   ├── non_leaf_1.sql
│   └── ...
├── mv_creation/
│   └── creation_log.json    # Phase 4で生成
└── ...
```

## 実装の詳細

### 修正ファイル

1. **config/default.yaml**
   - `sql_generation` フェーズを追加

2. **config/settings.py**
   - `ExecutionPhasesConfig.sql_generation` を追加
   - `phases_order` に `sql_generation` を追加

3. **scripts/run_experiment.py**
   - Phase 3 (sql_generation) の処理を追加
   - フェーズ番号を 5 → 6 に更新
   - コマンドライン引数の choices に `sql_generation` を追加

## テスト

```bash
# 全フェーズ実行
python scripts/run_experiment.py --algorithms bigsubs --start-from query_parsing

# SQL生成のみ実行（Phase 2の結果が必要）
python scripts/run_experiment.py --algorithms bigsubs --phases sql_generation

# 最適化からMV作成まで
python scripts/run_experiment.py --algorithms bigsubs --start-from optimization --end-at mv_creation
```
