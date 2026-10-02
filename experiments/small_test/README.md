# 小規模実験 - 実行手順書

このディレクトリには、MV最適化プロジェクトを小規模データで段階的に試すための全ファイルが含まれています。

## 📁 ディレクトリ構造

```
experiments/small_test/
├── 00_setup.sql                      # データベース・テーブル・データ作成
├── 01_queries/                       # テストクエリ（6個）
│   ├── query1.sql                   # 都市別ユーザー集計
│   ├── query2.sql                   # カテゴリ別売上集計
│   ├── query3.sql                   # 3テーブルJOIN
│   ├── query4.sql                   # 商品価格帯別集計
│   ├── query5.sql                   # 注文統計
│   └── query6.sql                   # ユーザー年齢別分析
│   ├── frequency.json               # 通常モード用頻度設定
│   └── frequency_time_dependent.json # 時刻依存型モード用頻度設定
├── 02_json/                          # EXPLAIN JSON（自動生成）
├── 03_parsed/                        # パース結果（自動生成）
├── 04_optimized/                     # ILP最適化結果（通常モード）
│   ├── normal/                      # Normalアルゴリズム
│   └── bigsubs/                     # BigSubsアルゴリズム
├── time_dependent_output/            # 時刻依存型モード結果
│   ├── qp_<time_id>.pkl            # 各タイムステップのパース結果
│   ├── <algo>_<time_id>_result.json # 各タイムステップの最適化結果
│   ├── <algo>_summary.json         # 全タイムステップのサマリー
│   └── time_metadata.json          # タイムステップのメタデータ
├── 05_mv_sql/                        # MV生成SQL（自動生成）
│   ├── normal/                      # 通常モード: アルゴリズム別
│   │   └── create_mvs.sql
│   └── normal/                      # 時刻依存型: アルゴリズム/タイムステップ別
│       ├── morning/create_mvs.sql
│       └── evening/create_mvs.sql
├── 06_rewritten/                     # リライトクエリ（自動生成）
│   └── normal/                      # 通常モード: アルゴリズム別
│       ├── rewritten_query1.sql
│       └── ...
│   └── normal/                      # 時刻依存型: アルゴリズム/タイムステップ別
│       ├── morning/rewritten_query1.sql
│       └── evening/rewritten_query1.sql
├── logs/                             # ログファイル
├── config.yaml                       # 実験設定
├── run_experiment.py                 # メイン実行スクリプト
├── mv_creator.py                     # MV作成モジュール（新規追加）
├── query_rewriter.py                 # クエリ書き換えクラス
├── mv_generator_wrapper.py           # MV生成ラッパー
├── frequency_weighted_parser.py      # 頻度重み付けパーサー
├── time_dependent_parser.py          # 時刻依存型パーサー
├── migration_planner.py              # マイグレーションプランナー（開発中）
├── README.md                         # この手順書
├── INTEGRATED_USAGE.md               # 統合スクリプトの詳細な使い方
└── FREQUENCY_WEIGHTING.md            # 頻度重み付けの説明
```

## 🚀 実行手順

### 前提条件

1. **PostgreSQL 13+** がインストール済み
2. **Python 3.10+**
3. 必要なパッケージがインストール済み
   ```bash
   pip install -r requirements.txt
   pip install PyYAML  # 必須
   ```
4. **Gurobiライセンス**が設定済み（ILP最適化に必要）

### 実行モード

実験スクリプトは2つのモードに分かれています:

1. **通常モード** (`run_experiment_normal.py`)
   - 単一の頻度設定でMV最適化を実行
   - 全クエリで共通のMVセットを使用
   - 使用アルゴリズム: **normal のみ**
   
2. **時刻依存型モード** (`run_experiment_time_dependent.py`)
   - 複数のタイムステップ（例: 朝、夜）で異なる頻度設定
   - タイムステップごとに異なるMVセットを作成・使用
   - 使用アルゴリズム: **normal のみ**

---

---

## 📋 実行フェーズ一覧

| フェーズ | 名称 | 通常モード | 時刻依存型モード | 説明 |
|---------|------|-----------|-----------------|------|
| 0 | データベースセットアップ | ✅ | N/A | テーブルとデータを作成 |
| 1 | EXPLAIN JSON生成 | ✅ | N/A | クエリ実行プランを取得 |
| 2 | クエリパース | ✅ | ✅ | 実行プランを内部表現に変換 |
| 3 | ILP最適化 | ✅ | ✅ | MVを選択（normalアルゴリズム） |
| 4 | MV生成SQL作成 | ✅ | ✅ | CREATE文を生成 |
| 5 | MV作成 | ✅ | ✅ | データベースにMVを作成 |
| 6 | クエリ書き換え | ✅ | ✅ | MVを使用するようクエリを変換 |

**注意:** フェーズ0とフェーズ1は通常モードでのみ実行可能です。時刻依存型モードはフェーズ2から開始します。

---

## 🔧 通常モードの実行手順

### ステップ1: データベースセットアップ

テーブルとサンプルデータを作成します。

```bash
python experiments/small_test/run_experiment_normal.py --phase 0
```

**実行内容:**
- データベース `mv_small_test` を作成
- 3つのテーブルを作成: `users`, `products`, `orders`
- サンプルデータを挿入（ユーザー50件、商品30件、注文200件）

**確認:**
```bash
psql -U postgres -d mv_small_test -c "SELECT COUNT(*) FROM users;"
psql -U postgres -d mv_small_test -c "SELECT COUNT(*) FROM orders;"
```

---

### ステップ2: EXPLAIN JSON生成

各クエリの実行プランをJSON形式で取得します。

```bash
python experiments/small_test/run_experiment_normal.py --phase 1
```

**実行内容:**
- `01_queries/*.sql` の全クエリに対して `EXPLAIN (FORMAT JSON)` を実行
- 結果を `02_json/` に保存

**確認:**
```bash
dir experiments\small_test\02_json
# query1.json, query2.json, ... が生成されているはず
```

---

### ステップ3: クエリパース

PostgreSQLの実行プランを内部表現に変換します。

```bash
python experiments/small_test/run_experiment_normal.py --phase 2
```

**実行内容:**
- `FrequencyWeightedParser` でJSONをパース
- リーフノード・非リーフノードを抽出
- コスト・サイズ・依存関係を計算
- 頻度重み付けを適用（`frequency.json` を使用）
- 結果を `qp_class.pkl` と `03_parsed/` に保存

**確認:**
```bash
type experiments\small_test\qp_class.pkl  # パース結果（pickle形式）
type experiments\small_test\03_parsed\parse_summary.json
```

---

### ステップ4: ILP最適化

整数線形計画法でMVを選択します（normalアルゴリズムのみ）。

```bash
python experiments/small_test/run_experiment_normal.py --phase 3
```

**実行内容:**
- normalアルゴリズムでILP実行
- ストレージ制限内で最大効用のMVを選択
- 結果を `04_optimized/normal/` に保存

**確認:**
```bash
type experiments\small_test\04_optimized\normal\result.json
```

---

### ステップ5: MV生成SQL作成

選択されたMVのCREATE文を生成します。

```bash
python experiments/small_test/run_experiment_normal.py --phase 4
```

**実行内容:**
- 最適化結果から選択されたMVを読み込み
- 各MVのCREATE MATERIALIZED VIEW文を生成
- `05_mv_sql/normal/create_mvs.sql` に保存

**確認:**
```bash
type experiments\small_test\05_mv_sql\normal\create_mvs.sql
```

---

### ステップ6: MV作成（データベース）

実際にPostgreSQLにMVを作成します。

```bash
python experiments/small_test/run_experiment_normal.py --phase 5
```

**実行内容:**
- `05_mv_sql/normal/create_mvs.sql` をpsqlで実行
- データベースにMVを作成

**確認:**
```bash
psql -U postgres -d mv_small_test -c "\dm+"
```

**出力例:**
```
              List of relations
 Schema |      Name       | Type    | Size  
--------+-----------------+---------+-------
 public | leaf_1          | matview | 16 kB
 public | leaf_9          | matview | 16 kB
```

---

### ステップ7: クエリ書き換え

選択されたMVを使用するようにクエリを書き換えます。

```bash
python experiments/small_test/run_experiment_normal.py --phase 6
```

**実行内容:**
- 最適化結果から各クエリで使用するMVを読み込み
- テーブル参照をMV参照に置き換え
- 書き換え結果を `06_rewritten/normal/` に保存

**確認:**
```bash
type experiments\small_test\06_rewritten\normal\rewritten_query1.sql
```

**出力例:**
```sql
-- ================================================
-- Query rewritten to use Materialized Views
-- ================================================
-- Selected MVs: 1
-- Replacements:
--   • FROM users → FROM leaf_1
-- ================================================

SELECT 
    u.city,
    COUNT(*) as user_count
FROM leaf_1 u
WHERE u.age >= 25
GROUP BY u.city
ORDER BY user_count DESC;
```

**パフォーマンス比較:**
```bash
# 元のクエリ
psql -U postgres -d mv_small_test -c "\timing on" -f experiments/small_test/01_queries/query1.sql

# 書き換え後のクエリ
psql -U postgres -d mv_small_test -c "\timing on" -f experiments/small_test/06_rewritten/normal/rewritten_query1.sql
```

---

### 全フェーズ一括実行

全フェーズを順番に実行します。

```bash
python experiments/small_test/run_experiment_normal.py --phase all
```

---

## ⏰ 時刻依存型モードの実行手順

時刻依存型モードでは、時間帯ごとに異なる頻度でクエリが実行されることを想定し、タイムステップごとに最適なMVセットを選択します。

**注意:** フェーズ0とフェーズ1は通常モードで事前に実行しておく必要があります。

### 準備: 頻度設定ファイル

`01_queries/frequency_time_dependent.json` を作成:

```json
{
  "timesteps": [
    {
      "id": "morning",
      "label": "朝（9:00-12:00）",
      "duration_hours": 3,
      "frequencies": {
        "query1": 100,
        "query2": 50,
        "query3": 80,
        "query4": 30,
        "query5": 60,
        "query6": 200
      }
    },
    {
      "id": "evening",
      "label": "夕方（17:00-20:00）",
      "duration_hours": 3,
      "frequencies": {
        "query1": 50,
        "query2": 150,
        "query3": 120,
        "query4": 80,
        "query5": 200,
        "query6": 100
      }
    }
  ]
}
```

### ステップ0-1: データベースセットアップ・EXPLAIN JSON生成

**重要:** 時刻依存型モードではフェーズ0とフェーズ1を実行できません。
事前に通常モードでこれらのフェーズを実行してください。

```bash
python experiments/small_test/run_experiment_normal.py --phase 0
python experiments/small_test/run_experiment_normal.py --phase 1
```

---

### ステップ2: 時刻依存型クエリパース

タイムステップごとにクエリを解析し、MV候補を生成します。

```bash
python experiments/small_test/run_experiment_time_dependent.py --phase 2
```

**実行内容:**
- `frequency_time_dependent.json` から各タイムステップの設定を読み込み
- タイムステップごとに頻度重み付けパースを実行
- 結果を `time_dependent_output/qp_<time_id>.pkl` に保存
- メタデータを `time_dependent_output/time_metadata.json` に保存

**確認:**
```bash
dir experiments\small_test\time_dependent_output
# qp_morning.pkl, qp_evening.pkl などが生成される
```

---

### ステップ3: 時刻依存型ILP最適化

各タイムステップで独立にMV選択を実行します（normalアルゴリズムのみ使用）。

```bash
python experiments/small_test/run_experiment_time_dependent.py --phase 3
```

**実行内容:**
- 各タイムステップのパース結果を読み込み
- タイムステップごとに独立してnormalアルゴリズムでILP実行
- 結果を `time_dependent_output/normal_<time_id>_result.json` に保存
- 全タイムステップの比較サマリーを `time_dependent_output/normal_summary.json` に保存

**確認:**
```bash
type experiments\small_test\time_dependent_output\normal_summary.json
type experiments\small_test\time_dependent_output\normal_morning_result.json
type experiments\small_test\time_dependent_output\normal_evening_result.json
```

**サマリー例:**
```json
[
  {
    "time_id": "morning",
    "label": "朝（9:00-12:00）",
    "duration_hours": 3,
    "total_utility": 2148.65,
    "num_mvs": 4,
    "storage_mb": 0.0045,
    "selected_mvs": ["leaf_1", "leaf_9", "non_leaf_12", "non_leaf_23"]
  },
  {
    "time_id": "evening",
    "label": "夕方（17:00-20:00）",
    "duration_hours": 3,
    "total_utility": 3821.99,
    "num_mvs": 4,
    "storage_mb": 0.0047,
    "selected_mvs": ["leaf_4", "leaf_9", "non_leaf_5", "non_leaf_12"]
  }
]
```

**ポイント:**
- タイムステップごとに**異なるMVセット**が選択される
- 頻度の違いにより最適なMVが変わる

---

### ステップ4: MV生成SQL作成（時刻依存型）

各タイムステップ用のMV作成SQLを生成します。

```bash
python experiments/small_test/run_experiment_time_dependent.py --phase 4
```

**実行内容:**
- 各タイムステップの最適化結果から選択されたMVを読み込み
- タイムステップID付きのMV名（例: `leaf_1_morning`）でCREATE文を生成
- 結果を `05_mv_sql/normal/<time_id>/create_mvs.sql` に保存

**確認:**
```bash
type experiments\small_test\05_mv_sql\normal\morning\create_mvs.sql
type experiments\small_test\05_mv_sql\normal\evening\create_mvs.sql
```

**出力例:**
```sql
-- =====================================================
-- NORMAL アルゴリズム - morning
-- =====================================================

\c mv_small_test

-- ノード: leaf_1 (morning)
CREATE MATERIALIZED VIEW leaf_1_morning AS
SELECT u.*
FROM users AS u
WHERE (age >= 25);

-- ノード: leaf_9 (morning)
CREATE MATERIALIZED VIEW leaf_9_morning AS
SELECT p.*
FROM products AS p
WHERE (price >= '300'::numeric);
```

**重要:** MV名にタイムステップIDが付加されます（`_morning`, `_evening`など）。

---

### ステップ5: MV作成（時刻依存型）

**🔄 重要な変更: 単一タイムステップのみ実体化**

時刻依存型モードでは、一度に**1つのタイムステップのMVのみ**をデータベースに作成します。
これにより、時間帯に応じてMVを切り替え、ストレージを効率的に使用します。

#### 5-1. morning のMVを作成

```bash
python experiments/small_test/run_experiment_time_dependent.py --phase 5 --time-id morning
```

**実行内容:**
- 既存の全MVを削除（DROP MATERIALIZED VIEW IF EXISTS）
- `05_mv_sql/normal/morning/create_mvs.sql` をpsqlで実行
- データベースにmorning用のMVのみを作成

**確認:**
```bash
psql -U postgres -d mv_small_test -c "\dm+"
```

**出力例:**
```
              List of relations
 Schema |        Name         | Type    | Size  
--------+---------------------+---------+-------
 public | mv_leaf_1_morning   | matview | 16 kB
 public | mv_leaf_9_morning   | matview | 16 kB
 public | mv_non_leaf_12_morning | matview | 24 kB
```

 Schema |        Name         | Type    | Size  
--------+---------------------+---------+-------
 public | leaf_1_morning      | matview | 16 kB
 public | leaf_9_morning      | matview | 16 kB
 public | non_leaf_12_morning | matview | 24 kB
```

#### 5-2. evening のMVに切り替え

```bash
python experiments/small_test/run_experiment_time_dependent.py --phase 5 --time-id evening
```

**実行内容:**
- **morning の全MVを削除**
- `05_mv_sql/normal/evening/create_mvs.sql` をpsqlで実行
- データベースにevening用のMVのみを作成

**確認:**
```bash
psql -U postgres -d mv_small_test -c "\dm+"
```

**出力例:**
```
              List of relations
 Schema |        Name         | Type    | Size  
--------+---------------------+---------+-------
 public | leaf_4_evening      | matview | 16 kB
 public | leaf_9_evening      | matview | 16 kB
 public | non_leaf_5_evening  | matview | 24 kB
```

**ポイント:**
- ✅ **一度に1つのタイムステップのMVのみが存在**
- ✅ 時間帯に応じて `--time-id` を変えて実行
- ✅ 既存MVは自動削除されるため、手動削除は不要
- ✅ ストレージを効率的に使用

**利用可能なタイムステップを確認:**
```bash
# --time-id を指定せずに実行すると利用可能なタイムステップが表示される
python experiments/small_test/run_experiment_time_dependent.py --phase 5
```

**⚠️ 注意事項:**
- `--time-id` オプションは**必須**です
- 無効なタイムステップIDを指定するとエラーになります
- MV切り替え時は、対応するタイムステップのクエリ書き換え結果を使用してください

---

### ステップ6: クエリ書き換え（時刻依存型）

各タイムステップ用にクエリを書き換えます。

```bash
python experiments/small_test/run_experiment_time_dependent.py --phase 6
```

**実行内容:**
- 各タイムステップの最適化結果から使用するMVを読み込み
- タイムステップごとに適切なMV名（例: `leaf_1_morning`）で置換
- 書き換え結果を `06_rewritten/normal/<time_id>/` に保存

**確認:**
```bash
dir experiments\small_test\06_rewritten\normal
# morning/, evening/ などのディレクトリが作成される

type experiments\small_test\06_rewritten\normal\morning\rewritten_query1.sql
type experiments\small_test\06_rewritten\normal\evening\rewritten_query1.sql
```

**出力例（morning）:**
```sql
-- ================================================
-- Query rewritten to use Materialized Views
-- ================================================
-- Selected MVs: 1
-- Replacements:
--   • FROM users → FROM leaf_1_morning
-- ================================================

SELECT 
    u.city,
    COUNT(*) as user_count
FROM leaf_1_morning u
WHERE u.age >= 25
GROUP BY u.city
ORDER BY user_count DESC;
```

**出力例（evening - MVが選択されていない場合）:**
```sql
-- No MVs selected for this query
-- Using original tables

SELECT 
    u.city,
    COUNT(*) as user_count
FROM users u
WHERE u.age >= 25
GROUP BY u.city
ORDER BY user_count DESC;
```

**ポイント:**
- タイムステップごとに**異なるMV**が使用される
- あるタイムステップでMVが選択されなかったクエリは元のテーブルを使用

**タイムステップ別パフォーマンス比較:**
```bash
# morning用のMVを使用
psql -U postgres -d mv_small_test -c "\timing on" -f experiments/small_test/06_rewritten/normal/morning/rewritten_query1.sql

# evening用のMVを使用（または元のテーブル）
psql -U postgres -d mv_small_test -c "\timing on" -f experiments/small_test/06_rewritten/normal/evening/rewritten_query1.sql
```

---

### 全フェーズ実行

時刻依存型モードの全フェーズを順番に実行します（タイムステップ指定が必要なフェーズ5は個別実行が必要）。

```bash
# フェーズ2-4と6を一括実行
python experiments/small_test/run_experiment_time_dependent.py --phase all

# その後、必要なタイムステップのMVを作成（個別実行）
python experiments/small_test/run_experiment_time_dependent.py --phase 5 --time-id morning
```

---

## 🎯 一括実行

### 通常モード（全フェーズ）

```bash
python experiments/small_test/run_experiment_normal.py --phase all
```

フェーズ0〜6を順番に実行します。

### 時刻依存型モード（段階的実行）

```bash
# ステップ1: 初期設定（通常モードで実行）
python experiments/small_test/run_experiment_normal.py --phase 0
python experiments/small_test/run_experiment_normal.py --phase 1

# ステップ2-4, 6: 時刻依存型処理
python experiments/small_test/run_experiment_time_dependent.py --phase all

# ステップ5: MV作成（タイムステップ指定必須）
# morning のMVを作成
python experiments/small_test/run_experiment_time_dependent.py --phase 5 --time-id morning
```

**時間帯切り替えの例:**
```bash
# 朝の時間帯: morning用MVを作成してクエリ実行
python experiments/small_test/run_experiment_time_dependent.py --phase 5 --time-id morning
psql -U postgres -d mv_small_test -f experiments/small_test/06_rewritten/normal/morning/rewritten_query1.sql

# 夕方の時間帯: evening用MVに切り替えてクエリ実行
python experiments/small_test/run_experiment_time_dependent.py --phase 5 --time-id evening
psql -U postgres -d mv_small_test -f experiments/small_test/06_rewritten/normal/evening/rewritten_query1.sql
```

---

## 📊 結果の確認

### 通常モード

**パース結果:**
```bash
# パース済みオブジェクト（pickle形式）
# Python内で読み込んで確認可能
```

**最適化結果:**
```bash
type experiments\small_test\04_optimized\normal\mv_selections.json
```

**MV一覧:**
```bash
psql -U postgres -d mv_small_test -c "
SELECT matviewname, 
       pg_size_pretty(pg_total_relation_size('public.'||matviewname)) as size
FROM pg_matviews 
WHERE schemaname = 'public'
ORDER BY matviewname;"
```

### 時刻依存型モード

**最適化サマリー:**
```bash
type experiments\small_test\time_dependent_output\normal_summary.json
```

**各タイムステップの詳細結果:**
```bash
type experiments\small_test\time_dependent_output\normal_morning_result.json
type experiments\small_test\time_dependent_output\normal_evening_result.json
```

**タイムステップ別のMV一覧:**
```bash
psql -U postgres -d mv_small_test -c "
SELECT matviewname, 
       pg_size_pretty(pg_total_relation_size('public.'||matviewname)) as size
FROM pg_matviews 
WHERE schemaname = 'public'
ORDER BY matviewname;"
```

---

## ⚠️ 既知の問題と制限事項

### 1. 時刻依存型モードのMV実体化戦略

**現在の仕様:**
- 一度に**1つのタイムステップのMVのみ**をデータベースに実体化
- タイムステップ切り替え時に既存MVを削除して新しいMVを作成
- `--time-id` オプションでタイムステップを指定

**利点:**
- ✅ ストレージを効率的に使用
- ✅ 時間帯に応じたMV切り替えが可能
- ✅ 実運用での動的MV管理に近い動作

**注意点:**
- ⚠️ MVの切り替えには再作成コストが発生
- ⚠️ 同時に複数タイムステップのMVは使用できない

**将来の拡張:**
- マイグレーションプランに基づく効率的なMV切り替え（`migration_planner.py`で開発中）
- 共通MVの保持による切り替えコスト削減

### 2. non_leafノードのMV作成エラー

**問題:**
- non_leafノード（複数テーブルのJOIN）のMVがデータベースに作成されない
- エラー: `列"user_id"が複数指定されました`

**原因:**
- 最適化アルゴリズムが`SELECT o.*, u.*, p.*`のようなSQLを生成
- PostgreSQLでは複数テーブルの`*`で同じ列名があるとエラー

**影響:**
- leafノード（単一テーブル）のMVのみが作成される
- 多くのケースではleafノードだけでも十分な最適化効果がある

**回避策:**
- 現時点ではleafノードのMVを使用した実験を継続
- 根本的な修正には最適化アルゴリズムのSQL生成部分の改修が必要

### 3. 時刻依存型モードのタイムステップID

**現在の仕様:**
- タイムステップIDは`frequency_time_dependent.json`で指定した値（例: `morning`, `evening`）がそのままMV名に使用される
- 例: `mv_leaf_1_morning`, `mv_leaf_9_evening`

**将来の改善案:**
- タイムステップIDを`t1`, `t2`, `t3`のような連番にする
- より一般的で拡張性の高い命名規則

---

## 🔧 設定のカスタマイズ

`config.yaml` を編集して実験条件を変更できます:

```yaml
database:
  host: localhost
  port: 5432
  database: mv_small_test
  user: postgres
  password: null  # null の場合、psql実行時に入力プロンプト

optimization:
  storage_limit_mb: 5        # ストレージ制限（MB）
  insert_queries: 50         # 挿入クエリ数（メンテナンスコスト計算用）
  
  algorithms:
    normal: true             # Normalアルゴリズム
    bigsubs: true            # BigSubsアルゴリズム
```

---

## 🧹 クリーンアップ

### MVのみ削除

```bash
psql -U postgres -d mv_small_test -c "
DO $$ 
DECLARE r RECORD;
BEGIN
    FOR r IN SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'
    LOOP
        EXECUTE 'DROP MATERIALIZED VIEW IF EXISTS ' || r.matviewname || ' CASCADE';
    END LOOP;
END $$;"
```

### データベース全体を削除

```bash
psql -U postgres -c "DROP DATABASE IF EXISTS mv_small_test;"
```

### 生成ファイルを削除（Windows）

```bash
rmdir /s /q experiments\small_test\02_json
rmdir /s /q experiments\small_test\03_parsed
rmdir /s /q experiments\small_test\04_optimized
rmdir /s /q experiments\small_test\time_dependent_output
rmdir /s /q experiments\small_test\05_mv_sql
rmdir /s /q experiments\small_test\06_rewritten
rmdir /s /q experiments\small_test\logs
del experiments\small_test\qp_class.pkl
```

---

## 🐛 トラブルシューティング

### エラー: `ModuleNotFoundError: No module named 'yaml'`

**解決策:**
```bash
pip install PyYAML
```

### エラー: psql コマンドが見つからない

**解決策（Windows）:**
```bash
set PATH=%PATH%;C:\Program Files\PostgreSQL\15\bin
```

### エラー: Gurobiライセンスエラー

**解決策:**
```bash
# ライセンスファイルを確認
dir gurobi.lic

# 環境変数を設定
set GRB_LICENSE_FILE=C:\path\to\gurobi.lic
```

### エラー: データベース接続失敗

**解決策:**
```bash
# PostgreSQLが起動しているか確認
psql -U postgres -c "SELECT version();"

# config.yaml のデータベース設定を確認
type experiments\small_test\config.yaml
```

### エラー: 時刻依存型モードで `--algorithm を指定してください`

**解決策:**
```bash
# phase 3 では --algorithm が必須
python experiments/small_test/run_experiment.py \
  --mode time-dependent \
  --phase 3 \
  --algorithm normal
```

### エラー: 時刻依存型モードで `--time-id を指定してください`

**解決策:**
```bash
# phase 5 では --time-id が必須
python experiments/small_test/run_experiment.py \
  --mode time-dependent \
  --phase 5 \
  --time-id morning

# 利用可能なタイムステップを確認
python experiments/small_test/run_experiment.py \
  --mode time-dependent \
  --phase 5
```

### エラー: `frequency_time_dependent.json が見つかりません`

**解決策:**
```bash
# サンプルファイルを参考に作成
# 上記の「時刻依存型モードの実行手順」の「準備」セクションを参照
```

---

## 📖 詳細ドキュメント

- **INTEGRATED_USAGE.md**: 統合された`run_experiment.py`の詳細な使い方
- **FREQUENCY_WEIGHTING.md**: 頻度重み付け機能の説明
- **時刻依存型最適化の論理**: タイムステップごとに異なる頻度でMV選択を最適化

## 🔧 主要モジュールの説明

### `mv_creator.py` - MV作成モジュール（新規追加）

時刻依存型モードで単一タイムステップのMVのみを実体化するためのモジュール。

**主要クラス:**
- `MVCreator`: MV作成処理を管理

**主要メソッド:**
- `create_mvs_for_single_timestep(algorithm, time_id, drop_existing=True)`: 
  - 指定されたタイムステップのMVを作成
  - 既存MVを削除してから新しいMVを作成
  - 戻り値: 成功したかどうか（bool）

- `create_migration_mvs(algorithm, from_time_id, to_time_id, migration_plan_file)`:
  - マイグレーションプランに基づいてMVを作成（開発中）
  - DROP/CREATEを効率的に実行
  
- `get_available_timesteps(algorithm)`:
  - 利用可能なタイムステップのリストを取得
  - 戻り値: タイムステップIDのリスト

**使用例:**
```python
from experiments.small_test.mv_creator import MVCreator
from config.settings import Settings

# 初期化
settings = Settings.from_yaml("experiments/small_test/config.yaml")
mv_creator = MVCreator(
    settings=settings,
    mv_sql_dir=Path("experiments/small_test/05_mv_sql"),
    output_dir=Path("experiments/small_test/time_dependent_output")
)

# 利用可能なタイムステップを確認
timesteps = mv_creator.get_available_timesteps("normal")
print(f"利用可能: {timesteps}")  # ['morning', 'evening']

# morning のMVを作成
success = mv_creator.create_mvs_for_single_timestep(
    algorithm="normal",
    time_id="morning",
    drop_existing=True
)

# evening に切り替え
success = mv_creator.create_mvs_for_single_timestep(
    algorithm="normal",
    time_id="evening",
    drop_existing=True
)
```

**特徴:**
- ✅ 既存MVの自動削除
- ✅ 作成されたMVの一覧表示
- ✅ エラーハンドリングとログ出力
- ✅ モジュール化により再利用可能

---

## 📈 各フェーズの所要時間

| フェーズ | 名称 | 所要時間（目安） |
|---------|------|-----------------|
| 0 | DB Setup | 10秒 |
| 1 | EXPLAIN JSON | 5秒 |
| 2 | Parse | 5秒（通常）/ 10秒（時刻依存型） |
| 3 | ILP | 30秒（通常）/ 60秒（時刻依存型） |
| 4 | SQL Gen | 5秒 |
| 5 | MV Create | 10秒 |
| 6 | Rewrite | 5秒 |

**通常モード合計: 約1分10秒**  
**時刻依存型モード合計: 約1分45秒**

---

## ✅ チェックリスト

**通常モード:**
- [ ] PostgreSQLがインストール済み
- [ ] Python環境が準備済み（PyYAML含む）
- [ ] Gurobiライセンスが設定済み
- [ ] フェーズ0: データベースセットアップ完了
- [ ] フェーズ1: EXPLAIN JSON生成完了
- [ ] フェーズ2: クエリパース完了
- [ ] フェーズ3: ILP最適化完了
- [ ] フェーズ4: MV生成SQL作成完了
- [ ] フェーズ5: MV作成完了
- [ ] フェーズ6: クエリ書き換え完了
- [ ] パフォーマンス比較実施

**時刻依存型モード:**
- [ ] `frequency_time_dependent.json` 作成済み
- [ ] フェーズ0-1: 初期設定完了
- [ ] フェーズ2: 時刻依存型パース完了
- [ ] フェーズ3: 時刻依存型最適化完了
- [ ] フェーズ4: タイムステップ別MV SQL作成完了
- [ ] フェーズ5: タイムステップ別MV作成完了
- [ ] フェーズ6: タイムステップ別クエリ書き換え完了
- [ ] タイムステップ別パフォーマンス比較実施

---

## 📝 次のステップ

1. **クエリを追加**: `01_queries/query7.sql` などを作成して実験
2. **ストレージ制限を変更**: `config.yaml`の`storage_limit_mb`を調整
3. **頻度設定を変更**: `frequency.json`や`frequency_time_dependent.json`を編集
4. **別のアルゴリズムを試す**: `--algorithm bigsubs`で実行
5. **大規模データセットで実験**: IMDBデータセットなどを使用
6. **non_leafノード問題の修正**: 最適化アルゴリズムのSQL生成部分を改修

---

## 🙋 質問・サポート

問題が発生した場合:
1. ログファイルを確認: `logs/experiment.log`
2. PostgreSQLのログを確認
3. エラーメッセージをよく読む
4. このREADMEのトラブルシューティングセクションを参照

---

**Happy Experimenting! 🚀**
