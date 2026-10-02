# MV作成SQL生成ロジック修正案# MV作成SQL生成ロジック修正案



## 問題点の再整理## 問題点



リーフノードのMV生成時に**Index Cond**と**Filter**の役割を整理する必要がある。現状、リーフノードのMV生成時に**Index Cond**と**Filter**を区別せずに処理している。



### 例: leaf_3とnon_leaf_3の関係### 例: leaf_3

```json```json

{{

  "node_id": "non_leaf_3",  "node_id": "leaf_3",

  "Node Type": "Nested Loop",  "Node Type": "Index Scan",

  "Join Type": "Inner",  "Index Cond": "(movie_id = mi_idx.movie_id)",

  "Plans": [  "Filter": "((note !~~ '%(as Metro-Goldwyn-Mayer Pictures)%'::text) AND ...)"

    { "node_id": "non_leaf_2", ... },}

    {```

      "node_id": "leaf_3",

      "Node Type": "Index Scan",**問題**: MVとして実体化する際、`Index Cond`は結合条件であり不要。`Filter`のみをWHERE句に含めるべき。

      "Index Cond": "(movie_id = mi_idx.movie_id)",  // ← 結合条件

      "Filter": "((note !~~ '%(as Metro-Goldwyn-Mayer Pictures)%'::text) AND ...)"  // ← フィルタ条件---

    }

  ]## 修正方針

}

```### 1. QueryParserでの条件分離



**理解すべきポイント**:`src/core/query_parser.py`でリーフノード処理時に:

- **leaf_3単体をMV化**: `Index Cond`は結合条件なので不要。`Filter`のみ必要- **Index Cond**: 結合条件として別フィールドに保存（`index_condition`）

- **non_leaf_3をMV化**: `Index Cond`を結合条件として使う必要がある- **Filter**: フィルタ条件として保存（`filter_condition`）



---#### 修正箇所

`convert_plan_to_dict()`のリーフノード処理部分:

## 現在の実装状況（確認結果）

```python

### ✅ 結合条件の抽出は既に実装済み# リーフノードの処理

if "Plans" not in node or len(node["Plans"]) == 0:

`QueryParser.extract_join_conditions()`で、親ノード（non_leaf_3）から結合条件を抽出:    # Index CondとFilterを分離

    index_cond = node.get("Index Cond", "")

```python    filter_cond = node.get("Filter", "")

def extract_join_conditions(self, node: dict[str, Any]) -> list[JoinCondition]:    

    # ...    # Filter条件のみをMV用に保存

    # Also check for Index Cond (can appear with JOIN operations)    self.qm.add_leaf_node(

    if "Index Cond" in node:        operator=node["Node Type"],

        parsed = self.parse_join_condition(node["Index Cond"], "Index Cond")        table_name=table_name,

        conditions.extend(parsed)        alias=alias,

    return conditions        filter_condition=filter_cond  # Filterのみ

```    )

```

→ **親ノード（Nested Loop）がIndex Condを結合条件として保持**  

→ **NonLeafNodeInfo.join_conditions に保存される**### 2. EnhancedMVGeneratorでの反映



### ✅ リーフノードのフィルタ条件も正しく処理`src/rewrite/enhanced_mv_generator.py`の`generate_leaf_mv_sql()`は既に正しく動作:



現状の`convert_plan_to_dict()`はリーフノード処理時:```python

operator, table, alias, filter_condition = self.qm.leaf_nodes_map_r[node_id]

```python

# リーフノードの場合# filter_conditionにはFilterのみが含まれる

if "Plans" not in node or len(node["Plans"]) == 0:if filter_condition:

    # フィルタ条件を決定（"Filter"キーのみ取得）    sql_parts.append(f"WHERE {filter_condition}")

    filter_condition = node.get("Filter", "")```

    

    self.qm.add_leaf_node(---

        operator=node["Node Type"],

        table_name=table_name,## 実装タスク

        alias=alias,

        filter_condition=filter_condition  # ← Filterのみ（正しい）1. **QueryParser修正** (30分)

    )   - `Index Cond`を除外し、`Filter`のみを`filter_condition`に設定

```   - 既存の`filter_name`分岐ロジックを修正



→ **既に正しく動作している！Index Condは含まれない**2. **テスト追加** (15分)

   - Index ScanノードでFilter/Index Condが正しく分離されることを確認

---   - 生成されるMV SQLにIndex Condが含まれないことを確認



## データフロー図---



```## 期待される動作

【リーフノード: leaf_3】

  Index Scan on movie_companies**修正前**:

  ├─ Index Cond: "(movie_id = mi_idx.movie_id)"  ```sql

  │   → 親ノード（non_leaf_3）で extract_join_conditions() により抽出CREATE MATERIALIZED VIEW leaf_3 AS

  │   → NonLeafNodeInfo.join_conditions に保存SELECT mc.*

  │FROM movie_companies AS mc

  └─ Filter: "((note !~~ '%(as Metro...)%') AND ...)" WHERE (movie_id = mi_idx.movie_id)  -- ✗ 結合条件が含まれる

      → leaf_3の filter_condition として保存  AND ((note !~~ '%(as Metro-Goldwyn-Mayer Pictures)%'::text) AND ...)

      → leaf_nodes_map_r[leaf_3] に格納```



【親ノード: non_leaf_3】**修正後**:

  Nested Loop```sql

  ├─ extract_join_conditions() CREATE MATERIALIZED VIEW leaf_3 AS

  │   → 子ノードのIndex Condを結合条件として抽出SELECT mc.*

  │   → NonLeafNodeInfo.join_conditions に保存FROM movie_companies AS mc

  │WHERE ((note !~~ '%(as Metro-Goldwyn-Mayer Pictures)%'::text) AND ...)  -- ✓ フィルタ条件のみ

  └─ MV生成時```

      → EnhancedMVGenerator._build_join_clause()
      → join_conditions を使って ON句を生成

【MV生成】
✅ leaf_3単体: Filter条件のみ使用
✅ non_leaf_3: Index Condを結合条件として使用
```

---

## 修正方針（明示化のみ）

### 既存実装は正しく動作しているため、コメント追加で意図を明示化

#### 1. query_parser.pyにコメント追加

```python
# リーフノードの処理
if "Plans" not in node or len(node["Plans"]) == 0:
    # 条件の役割分担:
    # - Index Cond: 親ノードで結合条件として抽出される（extract_join_conditions）
    # - Filter: このリーフノード自体のフィルタ条件（MV化時に使用）
    # ここではFilterのみを取得（Index Condは親ノードで処理）
    filter_condition = node.get("Filter", "")
    
    self.qm.add_leaf_node(
        operator=node["Node Type"],
        table_name=table_name,
        alias=alias,
        filter_condition=filter_condition  # Filter条件のみ保存
    )
```

#### 2. enhanced_mv_generator.pyにコメント追加

```python
def generate_leaf_mv_sql(self, node_id: str) -> str:
    """Generate leaf MV creation SQL.
    
    Note: Index Condは結合条件なのでリーフMVには含めない。
    親ノードのMV生成時にjoin_conditionsとして使用される。
    """
    operator, table, alias, filter_condition = self.qm.leaf_nodes_map_r[node_id]
    # ... (既存コード)
```

---

## 実装タスク

### 1. コメント追加（10分）
- `query_parser.py`のリーフノード処理部分
- `enhanced_mv_generator.py`のleaf/non-leaf MV生成部分
- 目的: Index CondとFilterの役割を明記

### 2. テスト追加（20分）
- Index Scanノードの処理確認
  - リーフノード: Filterのみが`filter_condition`に設定
  - 親ノード: Index Condが`join_conditions`に抽出
- MV SQL生成確認
  - leaf_3: Filter条件のみ含む
  - non_leaf_3: Index Condを結合条件として使用

---

## 期待される動作

### ✅ leaf_3単体のMV（既に正しく動作）
```sql
CREATE MATERIALIZED VIEW leaf_3 AS
SELECT mc.*
FROM movie_companies AS mc
WHERE ((note !~~ '%(as Metro-Goldwyn-Mayer Pictures)%'::text) 
       AND ((note ~~ '%(co-production)%'::text) 
            OR (note ~~ '%(presents)%'::text)));
```

### ✅ non_leaf_3のMV（Index Condを結合条件として使用）
```sql
CREATE MATERIALIZED VIEW non_leaf_3 AS
SELECT *
FROM non_leaf_2
INNER JOIN leaf_3 ON non_leaf_2.movie_id = leaf_3.movie_id;  -- ← Index Condを使用
```

---

## まとめ

### 現状分析
- ✅ **既存実装は正しく動作している**
- ✅ **Index Condは親ノードで結合条件として抽出済み**
- ✅ **リーフノードはFilterのみを保持**

### 推奨アクション
- 📝 **コメント追加で意図を明示化**（必須ではないが推奨）
- 🧪 **テスト追加で動作を保証**

### 修正不要な理由
1. `extract_join_conditions()`が親ノードでIndex Condを正しく抽出
2. リーフノードは`Filter`のみを`filter_condition`として保存
3. `EnhancedMVGenerator`が適切に使い分けている
