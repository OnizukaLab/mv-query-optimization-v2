# Node ID Consistency Fix

## 問題の概要

`Output/parsed/`ディレクトリに生成されるJSONファイルに記載されている`node_id`と、処理の中で扱う`node_id`が一致していない問題がありました。

### 発生していた問題

1. **JSONファイル内のnode_id**: position (0, 1, 2, ...) ベースでマッピングされていた
2. **QueryManagerのnode_id**: カウンター (`leaf_id_counter`, `non_leaf_id_counter`) ベースで生成される実際のID (例: `leaf_63`, `non_leaf_161`)
3. これらが一致していなかったため、LLMの解析やデバッグ時に混乱が発生していた

## 解決方法

### 変更したファイル

#### 1. `src/core/parse_exporter.py`

**変更前の問題点:**
- `position_to_node` マッピングを使用して、positionベースでnode_idを取得していた
- これにより、実際のQueryManagerのnode_idと一致しないnode_idがJSONに記載されていた

**変更後の実装:**
- `_get_node_id_from_plan()` メソッドを追加
- クエリプランツリーを再帰的に走査し、QueryManagerの実際のマッピング（`leaf_nodes_map`, `non_leaf_nodes_map`）から直接node_idを取得
- リーフノードとノンリーフノードの両方を正しく識別し、適切なnode_idをアノテーション

**主な変更点:**

```python
# 変更前: positionベースのマッピング
self.position_to_node: dict[tuple[int, int], str] = {}
for node_id, positions in self.qm.subquery_positions.items():
    for pos in positions:
        query_id, position = pos
        self.position_to_node[(query_id, position)] = node_id

# 変更後: QueryManagerから直接取得
def _get_node_id_from_plan(self, node: dict[str, Any], query_idx: int) -> str | None:
    # リーフノードの場合
    if has_relation and (not has_plans or node_type == 'Bitmap Heap Scan'):
        key = (operator, table, alias, filter_condition)
        node_id = self.qm.leaf_nodes_map.get(key)
        return node_id
    
    # ノンリーフノードの場合
    elif has_plans:
        child_node_ids = [...]  # 子ノードのIDを再帰的に取得
        key = tuple(sorted(child_node_ids))
        node_id = self.qm.non_leaf_nodes_map.get(key)
        return node_id
```

## 動作確認

### テスト方法

```bash
python test_node_id_fix.py
```

### テスト結果

```
================================================================================
Testing node_id consistency fix
================================================================================

1. Parsing queries...
Query selection mode: all_job (using all JOB queries)
q_num_len= 113
Root node ID: non_leaf_990

2. Exporting annotated query files...
Annotated 83 query files
Output directory: .../Output/parsed

3. Verifying node_id consistency...

Found 14 node_ids in 17c.json:
  - non_leaf_467
  - non_leaf_466
  - non_leaf_465
  - non_leaf_464
  - non_leaf_463
  - non_leaf_457
  - non_leaf_30
  - leaf_12
  - leaf_13
  - leaf_37
  ... and 4 more

✓ 14/14 node_ids have valid format
✓ All node_ids found in QueryManager

================================================================================
Test completed successfully!
================================================================================
```

### 実際のJSONファイル例

`Output/parsed/17c.json`:
```json
{
  "Plan": {
    "node_id": "non_leaf_467",
    "Node Type": "Aggregate",
    "Plans": [
      {
        "node_id": "non_leaf_466",
        "Node Type": "Nested Loop",
        "Plans": [
          {
            "node_id": "leaf_12",
            "Node Type": "Seq Scan",
            "Relation Name": "keyword"
          }
        ]
      }
    ]
  }
}
```

## 影響範囲

### 変更による影響

1. **JSONファイルの一貫性向上**: `Output/parsed/`に生成されるJSONファイルのnode_idが、システム内部で使用されるnode_idと完全に一致
2. **デバッグの容易性**: LLMやデバッグツールがJSONファイルを読む際に、正確なnode_idを参照できる
3. **後方互換性**: 既存のコードは変更なしで動作（QueryManagerのマッピングを使用しているため）

### 影響を受けるコンポーネント

- `src/core/parse_exporter.py`: 主要な変更
- `Output/parsed/*.json`: 生成されるファイルのnode_id値が変更
- その他のコンポーネント: 影響なし（内部的にQueryManagerのマッピングを使用しているため）

## 重要な注意点

### リーフノードの識別

リーフノードは以下の条件で識別されます:
- `Relation Name`が存在する
- `Plans`がないか、または`Node Type`が`Bitmap Heap Scan`

### ノンリーフノードの識別

ノンリーフノードは:
- 子ノードのIDをソートした`tuple`をキーとして使用
- これにより、同じ子ノードの組み合わせは同じnode_idにマッピングされる（重複排除）

### フィルタ条件の処理

- `Filter`フィールドのみを使用（`Index Cond`は結合条件なのでリーフMV生成時は除外）
- これは`query_parser.py`の`convert_node()`メソッドと同じロジック

## まとめ

この修正により、`Output/parsed/`のJSONファイルと処理中のnode_idが完全に一致するようになりました。これにより、LLMの解析精度が向上し、デバッグやトラブルシューティングが容易になります。
