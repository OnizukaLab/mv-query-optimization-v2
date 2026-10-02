## コスト計算方法の違いの分析と評価

### 1. **違いの原因分析**

#### 主な違いの例
- `leaf_1`: 1.62 → 13.14（約8倍）
- `leaf_8`: 6.0 → 18.14（約3倍）
- `non_leaf_3`: 29.48 → 0.91（約1/32）

#### 原因の特定

**以前の方法（EXPLAIN実行）:**
- 実際にMV作成SQLを `EXPLAIN` で実行
- PostgreSQLが実際のテーブル統計、インデックス、JOINアルゴリズムを考慮して計算
- MVを使った場合の実際のコスト削減を反映

**現在の方法（original_subquery_costs）:**
- 元のクエリのEXPLAIN結果から各ノードのコストを取得
- **問題点**: これは「そのクエリ実行時のコスト」であり、「MV作成時のコスト」ではない
- 特に、Limitやフィルタでコストが削減されているノード（`non_leaf_3` など）は、実際のMV作成コストよりはるかに小さい値になる

### 2. **この違いは無視できるか？**

#### **無視できない理由**

❌ **マイグレーションコスト計算の意味が変わる**
- 現在の方法では「クエリ実行コスト」を使っているため、「MV作成コスト」とは異なる
- 例: `non_leaf_3` の `[]` プランが 0.91 というのは、実際のMV作成コストではない

❌ **最適化結果が大きく異なる可能性**
- マイグレーションコストが実際より小さく/大きく計算されると、最適化アルゴリズムが誤った判断をする
- 特に、依存MVのコストが大きすぎる場合、多くのプランでコストが0になり、選択肢が狭まる

❌ **コストが0になる問題**
- `non_leaf_1` の `['leaf_1']`: 依存コスト(13.14) > ターゲットコスト(0.45) → 0.0
- これは「既存MVを使ってもコスト削減がない」という誤った判断

### 3. **改善案（EXPLAIN実行なし）**

#### **案1: クエリプランの構造を利用した推定（推奨）**

EXPLAIN JSONには各ノードの **Plan Rows**（推定行数）が含まれています。これを使ってMV作成コストを推定します。

```python
def estimate_mv_creation_cost(self, node_id: str) -> float:
    """MVの実際の作成コストを推定
    
    Args:
        node_id: ノードID
    
    Returns:
        推定MV作成コスト
    """
    # 元のクエリのEXPLAIN JSONから情報を取得
    plan_info = self._get_plan_info_for_node(node_id)
    
    if not plan_info:
        return self.qp.qm.original_subquery_costs.get(node_id, 0.0)
    
    # Plan Rowsを取得
    plan_rows = plan_info.get("Plan Rows", 1)
    
    # リーフノードの場合
    if node_id.startswith("leaf_"):
        # テーブルスキャンのコスト = 推定行数 × スキャンコスト係数
        base_cost = plan_rows * 0.01  # PostgreSQLのデフォルト: seq_page_cost
        return base_cost
    
    # 非リーフノードの場合
    else:
        # JOINのコスト = 推定行数 × JOIN係数
        # Limitなどのフィルタを無視した「フルスキャン」のコストを推定
        
        # 子ノードのコストを合計
        child_nodes = self._get_child_nodes(node_id)
        child_cost_sum = sum(
            self.estimate_mv_creation_cost(child) 
            for child in child_nodes
        )
        
        # JOIN処理のオーバーヘッド
        join_overhead = plan_rows * 0.005  # cpu_operator_cost
        
        return child_cost_sum + join_overhead

def _get_plan_info_for_node(self, node_id: str) -> Optional[dict]:
    """ノードのEXPLAINプラン情報を取得"""
    # position_node_idからクエリIDを取得
    positions = self.qp.position_node_id.get(node_id, [])
    if not positions:
        return None
    
    query_id = positions[0][0]
    position = positions[0][1]
    
    # 対応するEXPLAIN JSONを読み込み
    json_path = self.json_dir / f"query{query_id}.json"
    with open(json_path, 'r', encoding='utf-8') as f:
        explain_data = json.load(f)[0]
    
    # position に基づいてプランノードを特定
    return self._find_node_at_position(explain_data["Plan"], position)
```

**利点:**
- Plan Rows（推定行数）は、Limitやフィルタの影響を受けない「元のデータサイズ」を反映
- PostgreSQLのコストモデルを簡易的に再現
- EXPLAIN実行不要

**欠点:**
- 完全に正確ではない（実際のEXPLAINより精度が低い）

---

#### **案2: スケーリング補正**

`original_subquery_costs` に対して、既知の問題（Limitなど）を補正します。

```python
def adjust_cost_for_mv_creation(self, node_id: str, original_cost: float) -> float:
    """MV作成用にコストを補正
    
    Args:
        node_id: ノードID
        original_cost: 元のクエリ実行コスト
    
    Returns:
        補正後のMV作成コスト
    """
    # EXPLAIN JSONからプラン情報を取得
    plan_info = self._get_plan_info_for_node(node_id)
    
    if not plan_info:
        return original_cost
    
    # Limitノードが存在するか確認
    has_limit = self._has_limit_in_plan(plan_info)
    
    if has_limit:
        # Limitで削減されたコストを推定して補正
        # 例: Plan RowsとLimit値の比率でスケーリング
        limit_value = self._get_limit_value(plan_info)
        plan_rows = plan_info.get("Plan Rows", 1)
        
        if limit_value and plan_rows:
            scaling_factor = plan_rows / min(limit_value, plan_rows)
            adjusted_cost = original_cost * scaling_factor
            return adjusted_cost
    
    return original_cost
```

**利点:**
- 既存のコストを活用
- Limit問題を部分的に解決

**欠点:**
- すべてのケースをカバーできない
- 補正ロジックが複雑化

---

#### **案3: ハイブリッド推定（最もバランスが良い）**

リーフノードは `original_subquery_costs` を使い、非リーフノードは子ノードのコストから推定します。

```python
def estimate_migration_cost_hybrid(self, node_id: str, dependencies: List[str]) -> float:
    """ハイブリッド方式でマイグレーションコストを推定
    
    Args:
        node_id: ターゲットノードID
        dependencies: 利用する既存MVのリスト
    
    Returns:
        推定マイグレーションコスト
    """
    # リーフノードの場合: original_subquery_costs を使用
    if node_id.startswith("leaf_"):
        target_cost = self.qp.qm.original_subquery_costs.get(node_id, 0.0)
    else:
        # 非リーフノードの場合: 子ノードのコストから推定
        target_cost = self._estimate_non_leaf_cost(node_id)
    
    # 依存MVのコスト
    dependency_cost = sum(
        self.qp.qm.original_subquery_costs.get(dep, 0.0) 
        if dep.startswith("leaf_") 
        else self._estimate_non_leaf_cost(dep)
        for dep in dependencies
    )
    
    return max(target_cost - dependency_cost, 0.0)

def _estimate_non_leaf_cost(self, node_id: str) -> float:
    """非リーフノードのMV作成コストを子ノードから推定
    
    Args:
        node_id: 非リーフノードID
    
    Returns:
        推定コスト
    """
    # 子ノードを取得
    child_nodes = self._get_child_nodes(node_id)
    
    if not child_nodes:
        return self.qp.qm.original_subquery_costs.get(node_id, 0.0)
    
    # 子ノードのコストを合計
    child_cost_sum = sum(
        self.qp.qm.original_subquery_costs.get(child, 0.0)
        for child in child_nodes
    )
    
    # JOINオーバーヘッド（簡易推定: 子ノード数に比例）
    join_overhead = len(child_nodes) * 0.5
    
    return child_cost_sum + join_overhead

def _get_child_nodes(self, node_id: str) -> List[str]:
    """ノードの子ノードを取得"""
    if node_id.startswith("leaf_"):
        return []
    
    # non_leaf_nodes_map_r から子ノードを取得
    non_leaf_info = self.qp.qm.non_leaf_nodes_map_r.get(node_id, {})
    return non_leaf_info.get("child_nodes", [])
```

**利点:**
- リーフノードは正確（テーブルスキャンのコスト）
- 非リーフノードは子ノードのコストから合理的に推定
- Limit問題を回避

**欠点:**
- 子ノード情報の取得が必要

---

### 4. **推奨アプローチ**

**案3（ハイブリッド推定）** を推奨します。理由：

1. **リーフノードの正確性**: テーブルスキャンのコストは `original_subquery_costs` で十分正確
2. **非リーフノードの改善**: 子ノードのコストから推定することで、Limit問題を回避
3. **実装の簡潔性**: 複雑な補正ロジックが不要
4. **スケーラビリティ**: EXPLAIN実行不要なので大規模環境でも実行可能

### 5. **実装例（advanced_migration_costs.py）**

```python
def _get_child_nodes(self, node_id: str) -> List[str]:
    """ノードの直接の子ノードリストを取得"""
    if node_id.startswith("leaf_"):
        return []
    
    # non_leaf_nodes_map_r から取得
    non_leaf_map = self.qp.qm.non_leaf_nodes_map_r
    if node_id in non_leaf_map:
        return non_leaf_map[node_id].get("child_nodes", [])
    
    return []

def _estimate_node_cost(self, node_id: str) -> float:
    """ノードのMV作成コストを推定（ハイブリッド方式）"""
    if node_id.startswith("leaf_"):
        # リーフノード: original_subquery_costs を使用
        return self.node_costs.get(node_id, 0.0)
    else:
        # 非リーフノード: 子ノードのコストから推定
        child_nodes = self._get_child_nodes(node_id)
        
        if not child_nodes:
            # 子ノード情報がない場合は元のコストを使用
            return self.node_costs.get(node_id, 0.0)
        
        # 子ノードのコストを再帰的に合計
        child_cost_sum = sum(self._estimate_node_cost(child) for child in child_nodes)
        
        # JOINオーバーヘッド（子ノード数に比例）
        join_overhead = len(child_nodes) * 0.5
        
        return child_cost_sum + join_overhead

def calculate_all_costs(self) -> Dict[str, Dict[str, float]]:
    """すべてのマイグレーションコストを計算（ハイブリッド推定）"""
    print(f"マイグレーションコスト計算中（ハイブリッド推定、クエリセット: {self.query_set}）...")
    
    for node_id, plans in self.plans.items():
        self.costs[node_id] = {}
        
        for plan_key, plan in plans.items():
            if not plan.startswith("CREATE MATERIALIZED VIEW"):
                self.costs[node_id][plan_key] = 0.0
                continue
            
            dependencies = eval(plan_key) if plan_key != "[]" else []
            
            # ハイブリッド推定でコスト計算
            target_cost = self._estimate_node_cost(node_id)
            dependency_cost = sum(self._estimate_node_cost(dep) for dep in dependencies)
            cost = max(target_cost - dependency_cost, 0.0)
            
            self.costs[node_id][plan_key] = cost
    
    self._save_costs()
    print(f"完了: {len(self.costs)} ノード処理済み")
    return self.costs
```

この実装により、Limit問題を回避しつつ、EXPLAIN実行なしで合理的なマイグレーションコストを推定できます。