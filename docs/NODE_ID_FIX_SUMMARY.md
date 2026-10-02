# Node ID Consistency Fix - Summary

## 修正概要

`Output/parsed/`ディレクトリに生成されるJSONファイルのnode_idと、処理中のnode_idの不一致を修正しました。

## 問題

- **JSONファイル**: positionベースのnode_id (0, 1, 2, ...)
- **QueryManager**: 実際のnode_id (leaf_63, non_leaf_161, ...)
- これらが一致せず、LLMの解析時に混乱を引き起こしていました

## 解決方法

### 変更ファイル: `src/core/parse_exporter.py`

1. **削除**: position_to_nodeマッピングの構築ロジック
2. **追加**: `_get_node_id_from_plan()` メソッド
   - クエリプランツリーを再帰的に走査
   - QueryManagerの実際のマッピング（`leaf_nodes_map`, `non_leaf_nodes_map`）から直接node_idを取得
   - リーフノード/ノンリーフノードを正しく識別

## 実装の詳細

### リーフノードの識別
```python
# (operator, table, alias, filter_condition) をキーとして使用
key = (operator, table, alias, filter_condition)
node_id = self.qm.leaf_nodes_map.get(key)
```

### ノンリーフノードの識別
```python
# ソート済み子ノードIDのtupleをキーとして使用
key = tuple(sorted(child_node_ids))
node_id = self.qm.non_leaf_nodes_map.get(key)
```

## テスト結果

✅ 83個のクエリファイルで正常動作を確認
✅ すべてのnode_idがQueryManagerと一致
✅ リーフノード、ノンリーフノード両方で正しく動作

例: `17c.json` - 14個のnode_idすべてが正しくアノテーション

## 影響

### ✅ 良い影響
- JSONファイルとシステム内部のnode_idが完全一致
- LLMの解析精度向上
- デバッグが容易に

### ⚠️ 注意点
- 既存の`Output/parsed/`ファイルは再生成が必要
- ただし、システムの動作には影響なし（QueryManagerを使用しているため）

## 使用方法

### テスト実行
```bash
python test_node_id_fix.py
```

### 実験実行時の自動適用
```bash
python scripts/run_experiment.py
```
- query_parsingフェーズで自動的に正しいnode_idが付与されます

## 関連ドキュメント

詳細は `docs/NODE_ID_FIX.md` を参照してください。
