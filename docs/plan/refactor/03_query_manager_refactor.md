# Phase 3: QueryManager リファクタリング

## 🎯 目的

`query_parse_beta.py` の `QueryManager` クラスを新しい構造に移行し、型ヒントとdocstringを追加します。

## ⏱️ 推定時間: 5-7時間

## 📋 実行手順概要

### Step 1: データモデルの定義

```python
# src/core/models.py

from dataclasses import dataclass
from typing import List, Tuple, Optional

@dataclass
class QueryNode:
    """Base class for query plan nodes."""
    node_id: str
    total_cost: float
    size: int
    width: int

@dataclass  
class LeafNode(QueryNode):
    """Leaf node (table scan)."""
    operator: str
    table_name: str
    alias: str
    filter_condition: str

@dataclass
class NonLeafNode(QueryNode):
    """Non-leaf node (join, etc.)."""
    child_ids: Tuple[str, ...]
    operator: str
```

### Step 2: QueryManager の移行

既存の `query_parse_beta.py` の `QueryManager` クラスを `src/core/query_manager.py` に移動し、以下を追加：

- 型ヒント
- docstring
- メソッドの整理

詳細な実装手順は完全版ドキュメントに記載。

---

**所要時間**: 5-7時間  
**難易度**: ⭐⭐⭐ (Hard)
