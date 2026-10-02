# MV作成SQL生成とクエリ書き換えロジック - 現状分析

## 1. 全体アーキテクチャ

### データフロー
```
1. QueryParser (EXPLAIN JSON解析)
   ↓ leaf_nodes_map_r, non_leaf_nodes_map_r を構築
2. ILP最適化 (BigSubs/Normalなど)
   ↓ 選択されたMVノードリストを出力
3. MVGenerator (CREATE MV SQL生成)
   ↓ ノードID → CREATE MATERIALIZED VIEW文
4. QueryRewriter (クエリ書き換え)
   ↓ 元のSQL → MVを使うSQL
5. 実行・評価
```

### 主要データ構造

**QueryManager が管理:**
```python
# リーフノード（テーブルスキャン）
leaf_nodes_map: {(operator, table, alias, filter) -> leaf_id}
leaf_nodes_map_r: {leaf_id -> (operator, table, alias, filter)}

# 非リーフノード（JOIN等）
non_leaf_nodes_map: {tuple(sorted([child1, child2, ...])) -> non_leaf_id}
non_leaf_nodes_map_r: {non_leaf_id -> tuple(sorted([child1, child2, ...]))}

# 各ノードの属性
subquery_positions: {node_id -> [[query_id, position], ...]}
subquery_costs: {node_id -> float}
subquery_sizes: {node_id -> int}  # rows * width
subquery_widths: {node_id -> int}  # bytes
```

---

## 2. MV作成SQL生成ロジック (MVGenerator)

### 2.1 リーフノードMV生成 (`_generate_leaf_mv`)

**入力:**
- `leaf_id`: 例 "leaf_4"
- `qm.leaf_nodes_map_r[leaf_id]`: `(operator, table_name, alias, conditions)`

**処理フロー:**
1. `leaf_nodes_map_r` から `(operator, table_name, alias, conditions)` 取得
2. スキーマ定義から該当テーブルのカラムリスト取得 (`get_table_columns`)
3. SELECT句構築: `alias.col1, alias.col2, ...`
4. FROM句構築: `table_name alias`
5. WHERE句: `conditions` をそのまま使用
6. SQL組み立て

**生成例:**
```sql
CREATE MATERIALIZED VIEW leaf_4 AS
SELECT ct.id, ct.kind
FROM company_type ct
WHERE ((kind)::text = 'production companies'::text);
```

**問題点:**
- ✅ 動作する（リーフノードは単純なテーブルスキャン）
- ⚠️ `conditions` の形式に依存（パース元の形式そのまま）
- ⚠️ スキーマ情報が必要（ハードコード: `src/rewrite/schema.py`）

### 2.2 非リーフノードMV生成 (`_generate_non_leaf_mv`)

**入力:**
- `non_leaf_id`: 例 "non_leaf_5"
- `qm.non_leaf_nodes_map_r[non_leaf_id]`: `tuple([child1, child2, ...])`

**処理フロー:**
1. `non_leaf_nodes_map_r` から子ノードIDリスト取得
2. 子ノードが2個未満の場合 → プレースホルダSQL生成
3. 子ノードを使ってFROM句構築
4. **JOIN条件は仮のもの** (`child[0].id = child[i].id`)
5. SELECT句: `*` 固定

**生成例:**
```sql
CREATE MATERIALIZED VIEW non_leaf_5 AS
SELECT *
FROM leaf_4
JOIN leaf_7 ON leaf_4.id = leaf_7.id
JOIN leaf_11 ON leaf_4.id = leaf_11.id;
```

**致命的な問題:**
- ❌ **JOIN条件が不正確** - 常に `.id = .id` を使用（実際のJOIN条件を保持していない）
- ❌ **JOIN種別不明** - INNER/LEFT/RIGHT の区別なし
- ❌ **オペレータ情報喪失** - Hash Join/Merge Join などの情報未使用
- ❌ **フィルタ条件の位置不明** - どのJOINレベルで適用するか不明
- ⚠️ SELECT `*` のため、カラム名が不明瞭

---

## 3. クエリ書き換えロジック (QueryRewriter)

### 3.1 全体フロー (`rewrite_workload`)

```python
for query_id, mv_nodes in mv_selections.items():
    1. 元のSQL取得（original_queries または qm.query_map）
    2. _rewrite_query(query_id, mv_nodes, original_sql)
    3. ファイル保存
```

### 3.2 書き換え処理 (`_rewrite_query`)

**現在の実装:**
1. SQLParser で FROM句抽出
2. FROM句からテーブルリスト抽出 `[(table, alias), ...]`
3. **リーフMVのみ置換:**
   ```python
   for mv_node in mv_nodes:
       if mv_node.startswith("leaf_"):
           if table_name == table:
               replace: "table alias" → "mv_node AS alias"
   ```
4. SELECT/WHERE句はそのまま維持
5. 新しいSQLを再構築

**実行例（Query 0）:**
```
入力MV: ['non_leaf_5']  ← 非リーフノード
↓
リーフMVチェック: non_leaf_5.startswith("leaf_") → False
↓
置換なし
↓
元のFROM句のまま出力
```

**致命的な問題:**
- ❌ **非リーフMV未対応** - 全体の63% (100/158) が非リーフMVだが置換できない
- ❌ **MVが使われない** - BigSubsアルゴリズムは非リーフMVを優先するが、それが使えない
- ⚠️ リーフMVでも完全一致のみ（`table_name == table`）- エイリアス違いなど考慮不足

### 3.3 SQLParser の制約

**FROM句解析 (`extract_tables`):**
```python
# カンマ区切り対応: "table1 t1, table2 t2"
# JOIN対応: "table1 t1 JOIN table2 t2 ON ..."
# AS対応: "table AS alias"
```

**問題:**
- ⚠️ 複雑なサブクエリ非対応
- ⚠️ ネストされたJOIN条件で精度低下
- ⚠️ 正規表現ベース - 複雑なSQLで誤動作の可能性

---

## 4. データ構造の問題

### 4.1 非リーフノードの情報不足

**現状保存されている情報:**
```python
non_leaf_nodes_map_r[node_id] = tuple(sorted([child1, child2, ...]))
# 例: ('leaf_4', 'leaf_7', 'leaf_11')
```

**失われている情報:**
- JOIN条件 (`t1.id = t2.movie_id` など)
- JOIN種別 (INNER/LEFT/RIGHT/FULL)
- JOIN順序（ソート済みタプルのため元の順序不明）
- オペレータ種別 (Hash Join/Merge Join/Nested Loop)
- 中間フィルタ条件

### 4.2 必要な情報

**非リーフMVを正しく生成・使用するには:**
```python
non_leaf_nodes_map_r[node_id] = {
    'children': [child1, child2, ...],  # 順序保持
    'join_type': 'Hash Join',
    'join_conditions': ['t.id = ci.movie_id', 'ci.movie_id = mc.movie_id'],
    'filter': 'ci.note LIKE ...',
    'output_columns': ['t.id', 't.title', 'ci.note', ...],
}
```

---

## 5. アルゴリズム別の影響

### BigSubsアルゴリズム
- **選択傾向:** 非リーフMV優先（効率性重視）
- **結果:** 158 MVs中 100個 (63%) が非リーフ
- **現状:** これらが全く使われない → 最適化が無駄

### Normalアルゴリズム
- **選択傾向:** リーフMVとのバランス
- **結果:** リーフMVも多く選択される
- **現状:** リーフMVのみ部分的に動作

---

## 6. 具体例: Query 0の処理

### 元のクエリ
```sql
SELECT MIN(chn.name) AS uncredited_voiced_character,
       MIN(t.title) AS russian_movie
FROM char_name AS chn,
     cast_info AS ci,
     company_name AS cn,
     company_type AS ct,
     movie_companies AS mc,
     role_type AS rt,
     title AS t
WHERE ci.note LIKE '%(voice)%'
  AND ci.note LIKE '%(uncredited)%'
  AND cn.country_code = '[ru]'
  AND rt.role = 'actor'
  AND t.production_year > 2005
  AND t.id = mc.movie_id
  AND t.id = ci.movie_id
  AND ci.movie_id = mc.movie_id
  AND chn.id = ci.person_role_id
  AND rt.id = ci.role_id
  AND cn.id = mc.company_id
  AND ct.id = mc.company_type_id;
```

### ILP最適化結果
```
選択されたMV: non_leaf_5
含まれる子ノード: (leaf_4, leaf_7, leaf_11, ...)
```

### 現在の書き換え結果
```sql
-- 何も変わらない（非リーフMV対応していないため）
FROM char_name chn, cast_info ci, company_name cn, ...
```

### 理想的な書き換え
```sql
-- non_leaf_5がt,ci,mc,ctのJOINを含む場合
FROM non_leaf_5 AS base,
     char_name chn,
     company_name cn,
     role_type rt
WHERE base.person_role_id = chn.id
  AND base.role_id = rt.id
  AND base.company_id = cn.id
  AND cn.country_code = '[ru]'
  AND rt.role = 'actor';
```

---

## 7. 主要な技術的課題

### 課題1: 情報損失
- **原因:** EXPLAIN JSONから抽出時に、JOIN条件などの詳細を保存していない
- **影響:** 非リーフMV SQLが正確に生成できない

### 課題2: 書き換えアルゴリズムの欠如
- **原因:** クエリグラフとMVグラフのマッチングロジック未実装
- **影響:** 非リーフMVが選択されても使用できない

### 課題3: データ構造の設計ミス
- **原因:** `tuple(sorted(children))` で順序・条件情報を喪失
- **影響:** MVの正確な定義が不可能

### 課題4: SQL生成の脆弱性
- **原因:** テンプレートベース・正規表現ベースの単純な実装
- **影響:** 複雑なクエリで破綻する可能性

---

## 8. 統計情報

### テストケース (BigSubs, 113クエリ)
- **選択されたMV総数:** 158
  - リーフMV: 58 (37%)
  - 非リーフMV: 100 (63%)
- **書き換え成功:** 0 (非リーフMVが使えないため)
- **実際に動作する可能性:** リーフMVのみの一部クエリ

### 生成されたSQL
- **リーフMV SQL:** 正常に生成（例: `leaf_4.sql`）
- **非リーフMV SQL:** 生成されない、またはプレースホルダのみ
- **書き換えクエリ:** FROM句が元のまま（MV未使用）

---

## 9. まとめ

### 動作する部分
1. ✅ リーフノードMV SQL生成（単純なテーブルスキャン）
2. ✅ 基本的なSQL解析（FROM/WHERE句抽出）
3. ✅ リーフMVの名前一致時の置換（理論上）

### 重大な欠陥
1. ❌ **非リーフMV SQL生成が不完全** - JOIN条件が不正確
2. ❌ **非リーフMVの書き換え未実装** - 63%のMVが使えない
3. ❌ **データ構造が情報を保持していない** - JOIN条件・順序喪失
4. ⚠️ **SQL解析が脆弱** - 複雑なクエリで精度低下

### 結論
現在の実装は**基本的なリーフMVにのみ対応**しており、最適化で選ばれる大半の非リーフMV（JOIN結果）を活用できない。BigSubsアルゴリズムの効果が全く発揮されず、実質的にMVによる性能改善が機能していない状態。
