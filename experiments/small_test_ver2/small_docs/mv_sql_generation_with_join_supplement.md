# MV生成SQLロジック解説（JOIN条件補完を含む）

## 1. このドキュメントの対象

本ドキュメントは、`small_test_ver2` の **MV生成SQL作成ロジック**を、JOIN条件補完の仕組みを含めて整理したものです。対象は以下です。

- Phase4: `simple_migration_plans.json` の生成
- Phase7: タイムステップごとの MV 作成/削除 SQL 生成
- JOIN条件補完: 実行計画から欠落した結合条件の元SQL補完

---

## 2. 全体フロー（Phase4 → Phase7）

### Phase4: 事前に MV SQL 候補を作る

1. `GetSimpleMigrationPlans` が全ノード（leaf/non_leaf）を走査
2. 各ノードで 2 パターンを作成
   - `[target_mv]`: `NON_MIGRATE`
   - `[]`: 依存MVなしで新規作成する `CREATE MATERIALIZED VIEW ... AS ...`
3. 結果を `04_migration/{query_set}/simple_migration_plans.json` に保存

参照:
- [experiments/small_test_ver2/migration/enumerate_simple_migration_plan.py](../migration/enumerate_simple_migration_plan.py)

### Phase7: 時系列差分で SQL を吐く

1. `simple_migration_plans.json` をロード
2. タイムステップ間で `selected_mvs` を比較
   - `mvs_to_create = current - prev`
   - `mvs_to_drop = prev - current`
3. 作成対象MVは `plans["[]"]` をそのまま採用して SQL ファイルを出力

参照:
- [experiments/small_test_ver2/scripts/run_experiment_normal.py](../scripts/run_experiment_normal.py)

---

## 3. MV生成SQLの中核クラス

## 3.1 SimpleMVSQLGenerator

役割:
- MV SQL の入口
- ベースSQL生成 (`EnhancedMVGenerator`) と、必要なら既存MV利用書き換え (`CommaJoinRewriter`) を統合

処理概要:
1. `EnhancedMVGenerator.generate_mv_sql(node_id)` で元SQLを作る
2. `CREATE MATERIALIZED VIEW ... AS` から `SELECT ...` を抽出
3. `existing_mvs` があれば `CommaJoinRewriter.rewrite_with_multiple_mvs(...)`
4. 最後に `CREATE MATERIALIZED VIEW {node_id} AS ...;` に戻す

参照:
- [experiments/small_test_ver2/mv_generation/simple_mv_sql_generator.py](../mv_generation/simple_mv_sql_generator.py)

## 3.2 EnhancedMVGenerator

役割:
- non-leaf ノードの MV SQL を、JOIN条件・フィルタを保って生成

ポイント:
- 子ノードをフラット展開
- FROM句は comma join 形式で並べる
- JOIN条件とフィルタは WHERE句へ集約
- 最後に「欠落JOIN条件補完」をかける

参照:
- [experiments/small_test_ver2/mv_generation/enhanced_mv_generator.py](../mv_generation/enhanced_mv_generator.py)

---

## 4. JOIN条件補完の目的と発動条件

目的:
- PostgreSQLの最適化（定数プッシュダウン等）で実行計画から消えた JOIN 条件を、元SQLから復元する

発動条件（`_supplement_missing_join_conditions`）:
1. `original_query_join_conditions` がロード済み
2. `all_aliases - covered_aliases` が空でない（未結合エイリアスあり）
3. 補完候補の条件で、左右エイリアスがサブツリー内に存在
4. かつ少なくとも片側が `unjoined_aliases` に含まれる

参照:
- [experiments/small_test_ver2/mv_generation/enhanced_mv_generator.py](../mv_generation/enhanced_mv_generator.py)
- [src/core/query_parser.py](../../../src/core/query_parser.py)

---

## 5. 元SQLからのJOIN抽出（今回の実装）

`original_sql_join_extractor.py` で以下を抽出します。

### 5.1 extract_aliases_from_sql

- FROM句を `WHERE/GROUP BY/ORDER BY/LIMIT/HAVING` まで抽出
- `FROM ...`, `, ...`, `JOIN ...` のテーブル定義から alias を抽出
- quoted identifier（`"table" AS "t"`）も対応

### 5.2 extract_equijoin_conditions

抽出対象:
- WHERE句中の `alias.col = alias.col`
- JOIN ... ON 句中の `alias.col = alias.col`

仕様:
- 自己結合（同一alias同士）は除外
- quoted identifier を正規化（クォート除去 + 小文字化）
- 条件は左右入れ替えを同一とみなして重複除去

参照:
- [experiments/small_test_ver2/mv_generation/original_sql_join_extractor.py](../mv_generation/original_sql_join_extractor.py)

---

## 6. 「不足を補えるか / 補いすぎるか」の整理

## 6.1 補える範囲

- 以前取りこぼしていた `JOIN ... ON` の等価結合を補完候補にできる
- quoted identifier の JOIN 条件も候補化できる
- 未結合 alias がある場合に限定して補完される

## 6.2 補いすぎる可能性（現仕様の注意点）

過補完リスクはゼロではありません。主に以下です。

1. `ON (a.id=b.id OR ...)` のような複合論理式
   - 等価条件のみ抽出し、最終的に `AND` 連結へ入るため、意図より強い条件になる可能性
2. 外部結合（LEFT/RIGHT/FULL）の `ON` 条件
   - 補完先が WHERE 連結ベースのため、外部結合の意味に影響する可能性
3. 非等価結合は補完対象外
   - `<`, `<=`, `BETWEEN`, `IS NOT DISTINCT FROM`, `USING` 等は抽出しない

現状は「JOIN欠落を減らす」ことを優先した実装です。

---

## 7. 実運用上のチェックポイント

- 生成されたMV SQLで、FROMに複数 alias があるのに WHERE側に JOIN 条件が不足していないかを確認
- 外部結合が多いワークロードでは、補完追加前後で結果件数の差分チェックを推奨
- 特に OR を含む ON 条件を持つクエリは、個別に生成SQLを spot check する

---

## 8. まとめ

- Phase4で `[]` プランSQLを作成し、Phase7でそのまま採用する設計
- JOIN条件補完は `EnhancedMVGenerator` の WHERE構築時に実行される
- 今回の抽出拡張により、`JOIN ... ON` と quoted identifier の不足補完が可能になった
- 一方で、外部結合や複合論理式に対する過補完リスクは設計上残るため、必要に応じて運用チェックで担保する
