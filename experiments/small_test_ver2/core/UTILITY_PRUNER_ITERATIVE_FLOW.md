# UtilityPrunerIterative 処理フロー

## 概要

`UtilityPrunerIterative`は、反復的近傍拡大とWST（Workload Summary Tree）階層的絞り込みを組み合わせた、MV候補の効率的な選出アルゴリズムです。

**主な特徴:**
- 事前に全近傍を拡大せず、各WSTノードで段階的に拡大
- 反復的最適化による探索の深化（最大5回のイテレーション）
- 親境界MVの近傍も含めた広範な探索
- 収束判定による効率的な計算打ち切り

---

## 全体の処理フロー

```
入力: per_timestep_seeds (各タイムステップのSeed MV)
  ↓
[1] WST構築
  ↓
[2] ルートノードから再帰的処理開始
  ↓
[3] 各ノードで反復的最適化
  ├─ イテレーション1: (Seed+近傍) ∪ (親境界MV+近傍) で最適化
  ├─ イテレーション2: 選ばれたMVの近傍を追加 → 再最適化
  ├─ イテレーション3-5: 収束するまで繰り返し
  └─ 結果を promising_mvs に蓄積
  ↓
[4] 子ノードへ境界制約を伝播 → 再帰
  ↓
出力: promising_mvs (有望MV候補の集合)
```

---

## 処理の詳細

### Phase 1: 初期化と準備

```python
pruner = UtilityPrunerIterative(
    node_list=node_list,           # MV候補のノードID一覧
    u_ij=u_ij,                     # 利得行列 [クエリ数][MV数]
    X=X,                           # 包含行列 [MV数][MV数]
    b_j=b_j,                       # MVサイズ配列
    B_max=B_max,                   # ストレージ予算
    timesteps=timesteps,           # タイムステップ名リスト
    migration_cost=migration_cost, # マイグレーションコスト
    query_frequency_by_timestep=freq,  # 頻度情報
    per_timestep_seeds=seeds,      # 各タイムステップのSeed
    qm=qm,                         # クエリモデル（近傍拡大用）
    position_node_id=pos_node_id,  # ポジション→ノードIDマッピング
    deeplist=deeplist,             # クエリツリー深さ情報
    max_iterations=5               # 最大イテレーション数
)
```

**保持する情報:**
- `I`: クエリ数
- `T`: タイムステップ数
- `J`: MV候補数
- `per_timestep_seeds`: 各タイムステップで単独最適化で選ばれたMV

---

### Phase 2: WST構築とエントリーポイント

```python
promising_mvs = pruner.prune_candidates()
```

**処理内容:**

1. **統計情報の収集**
   ```python
   all_seed_union = set()
   for seeds in self.per_timestep_seeds.values():
       all_seed_union.update(seeds)
   # 例: 全Seed和集合 = 245 candidates
   ```

2. **WST構築**
   ```python
   tree = WorkloadSummaryTree(self.T)  # T=8タイムステップの場合
   # WST構造:
   #   Root: [0,4,7]
   #   ├─ Left: [0,2,4]
   #   │  ├─ [0,1,2]
   #   │  └─ [2,3,4]
   #   └─ Right: [4,6,7]
   #      ├─ [4,5,6]
   #      └─ [6,7,7]
   ```

3. **再帰処理の開始**
   ```python
   self._recursive_solve(
       tree_node=tree.root,
       parent_min_mvs=set(),      # 初回は空
       parent_max_mvs=set(),      # 初回は空
       promising_mvs=promising_mvs  # 結果蓄積用
   )
   ```

---

### Phase 3: 各ノードでの処理 (`_recursive_solve`)

#### Step 3.1: 固定境界の構築

```python
# 親から受け継いだMVを固定制約として設定
fixed_mvs_by_timestep = {}

if is_left_child:
    # 左子ノード: 親のmin時刻とmax時刻のMVを固定
    fixed_mvs_by_timestep[tree_node.min_idx] = parent_min_mvs
    fixed_mvs_by_timestep[tree_node.max_idx] = parent_max_mvs

if is_right_child:
    # 右子ノード: 親のmedian時刻とmax時刻のMVを固定
    fixed_mvs_by_timestep[tree_node.min_idx] = parent_min_mvs
    fixed_mvs_by_timestep[tree_node.max_idx] = parent_max_mvs

# 親境界MVを集約
parent_boundary_mvs = set()
for mvs in fixed_mvs_by_timestep.values():
    parent_boundary_mvs.update(mvs)
```

**例:**
```
Root [0,4,7]: parent_boundary_mvs = {} (空)
Left [0,2,4]: parent_boundary_mvs = {mv_5, mv_12, mv_23} (親の0時刻と4時刻のMV)
```

---

#### Step 3.2: 初期候補の構築 (`_build_initial_candidates`)

```python
def _build_initial_candidates(tree_node, parent_boundary_mvs):
    # 1. ノードが担当する時刻のSeedを収集
    seed_indices = set()
    for t_idx in range(tree_node.min_idx, tree_node.max_idx + 1):
        ts_name = self.timesteps[t_idx]
        seed_indices.update(self.per_timestep_seeds[ts_name])
    
    # 2. Seedを近傍拡大
    expanded_seeds = self.expand_neighbors(seed_indices, silent=True)
    seed_neighbors = expanded_seeds - seed_indices
    
    # 3. 親境界MVも近傍拡大（★重要な変更点）
    expanded_boundary = self.expand_neighbors(parent_boundary_mvs, silent=True)
    boundary_neighbors = expanded_boundary - parent_boundary_mvs
    
    # 4. 統合
    candidate_set = expanded_seeds | expanded_boundary
    
    return candidate_set, stats
```

**近傍拡大の仕組み (`expand_neighbors`):**

```python
def expand_neighbors(seed_indices):
    expanded = set(seed_indices)
    
    for j in seed_indices:
        node_id = self.node_list[j]
        
        # 上方向: クエリツリーの親ノードを追加
        if node_id in qm.subquery_positions:
            parent_pos = _find_parent(query_id, position)
            if parent_pos in position_node_id:
                expanded.add(parent_node_index)
        
        # 下方向: クエリツリーの子ノードを追加
        if node_id.startswith("non_leaf_"):
            for child_node_id in qm.non_leaf_nodes_map_r[node_id]:
                expanded.add(child_node_index)
    
    return expanded
```

**統計情報の例:**
```
Node [1/15] T[0:7]
  Seed: 100個
  Seed近傍: 45個 (+45)
  Boundary: 0個 (ルートなので親境界なし)
  Boundary近傍: 0個
  → Initial: 145個
```

---

#### Step 3.3: 頻度の集約 (`_aggregate_frequencies`)

WSTノードの期間を3分割し、各区間の頻度を代表3時点（min, median, max）に集約します。

```python
# 例: ノード [0,4,7] (期間8タイムステップ)
# 区間: [0,2], [3,5], [6,7]
# 集約先: t=0,  t=4,  t=7

for range_idx, (r_start, r_end) in enumerate(ranges):
    total_freqs = [0.0] * num_queries
    for t in range(r_start, r_end):
        total_freqs[q] += self.freq[timesteps[t]][q]
    
    aggregated_freq[target_timestep] = total_freqs
```

**効果:**
- 8タイムステップの問題を3タイムステップの問題に簡略化
- ILPの変数数を削減

---

#### Step 3.4: 反復的最適化 (`_iterative_node_optimization`)

各ノードで最大5回のイテレーションを実行します。

```python
def _iterative_node_optimization(tree_node, fixed_mvs, parent_boundary_mvs, aggregated_freq):
    # 初期候補を構築
    current_candidates, stats = _build_initial_candidates(tree_node, parent_boundary_mvs)
    
    previous_selected = None
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        
        # === イテレーション開始 ===
        
        # 1. ILP最適化を実行
        optimizer = LocalILPOptimizer(
            candidate_indices=sorted(current_candidates),  # 現在の候補
            fixed_mvs_by_timestep=fixed_mvs,              # 境界制約
            timestep_indices=[min_idx, median_idx, max_idx]
        )
        result = optimizer.optimize()
        
        # 2. 選択されたMVを集計
        current_selected = set()
        for mvs in result["selected_mvs_by_timestep"].values():
            current_selected.update(mvs)
        
        pool_mvs = result.get("pool_mvs", set())
        current_selected_all = current_selected | pool_mvs
        
        # 3. 収束判定
        if previous_selected is not None and current_selected == previous_selected:
            print("→ 収束（選択が変化なし）")
            break
        
        # 4. 近傍拡大
        expanded_candidates = expand_neighbors(current_selected_all)
        expanded_candidates.update(parent_boundary_mvs)  # 親境界も保持
        
        new_candidates = expanded_candidates - current_candidates
        
        if not new_candidates:
            print("→ 収束（新規候補なし）")
            break
        
        print(f"→ 近傍拡大: +{len(new_candidates)} 新規候補")
        
        # 5. 次イテレーションの準備
        current_candidates = expanded_candidates
        previous_selected = current_selected.copy()
    
    return result
```

**具体的な実行例:**

```
Node [1/15] T[0:7] Seed:100+45, Boundary:0+0 -> Initial:145

  反復最適化開始: 初期候補 145 MVs
  
  Iter 1: 候補 145, 選択 38 MVs
  → 近傍拡大: +67 新規候補
  
  Iter 2: 候補 212, 選択 42 MVs
  → 近傍拡大: +23 新規候補
  
  Iter 3: 候補 235, 選択 42 MVs
  → 収束（選択が変化なし、3回で完了）
  
  反復最適化完了: 総イテレーション数 3回
```

---

#### Step 3.5: 結果の収集と子ノードへの伝播

```python
# 選択されたMVを promising_mvs に追加
selected_mvs_optimal = set()
for t_idx, mvs in result["selected_mvs_by_timestep"].items():
    selected_mvs_optimal.update(mvs)

pool_mvs = result.get("pool_mvs", set())
selected_mvs_all = selected_mvs_optimal | pool_mvs

promising_mvs.update(selected_mvs_all)  # in-place更新

# 境界MVを抽出
min_mvs = result["selected_mvs_by_timestep"][tree_node.min_idx]
median_mvs = result["selected_mvs_by_timestep"][tree_node.median_idx]
max_mvs = result["selected_mvs_by_timestep"][tree_node.max_idx]

# 左子ノードへ伝播
if tree_node.left_child:
    _recursive_solve(
        tree_node=tree_node.left_child,
        parent_min_mvs=min_mvs,      # 親のmin時刻のMV
        parent_max_mvs=median_mvs,   # 親のmedian時刻のMV
        promising_mvs=promising_mvs  # 蓄積用（共通の集合）
    )

# 右子ノードへ伝播
if tree_node.right_child:
    _recursive_solve(
        tree_node=tree_node.right_child,
        parent_min_mvs=median_mvs,   # 親のmedian時刻のMV
        parent_max_mvs=max_mvs,      # 親のmax時刻のMV
        promising_mvs=promising_mvs
    )
```

---

## 処理の全体像（具体例: 8タイムステップ）

### WST構造と処理順序

```
                    [1] Root [0,4,7]
                        /           \
            [2] Left [0,2,4]      [3] Right [4,6,7]
               /        \             /          \
        [4] [0,1,2]  [5] [2,3,4]  [6] [4,5,6]  [7] [6,7,7]
        
        [8] [0,0,1]  [9] [1,2,2]  [10] [2,3,3] [11] [3,4,4]
                     [12] [4,5,5] [13] [5,6,6] [14] [6,7,7] [15] [7,7,7]
```

### 各ノードの処理詳細

#### ノード [1] Root [0,4,7]
```
入力:
  parent_min_mvs = {} (空)
  parent_max_mvs = {} (空)
  
処理:
  1. Seed収集: t0,t1,t2,t3,t4,t5,t6,t7 の全Seed → 245個
  2. Seed近傍拡大: 245 → 312個 (+67)
  3. 親境界近傍拡大: 0 → 0個
  4. 初期候補: 312個
  
  反復最適化 (3回で収束):
    Iter 1: 候補312, 選択38
    Iter 2: 候補379 (+67近傍), 選択42
    Iter 3: 候補402 (+23近傍), 選択42 → 収束
  
出力:
  min_mvs (t0): {mv_5, mv_12}
  median_mvs (t4): {mv_8, mv_15, mv_23}
  max_mvs (t7): {mv_10, mv_19}
  promising_mvs: 42個追加
```

#### ノード [2] Left [0,2,4]
```
入力:
  parent_min_mvs = {mv_5, mv_12} (親のt0)
  parent_max_mvs = {mv_8, mv_15, mv_23} (親のt4)
  
固定制約:
  t0時刻: {mv_5, mv_12} を固定
  t4時刻: {mv_8, mv_15, mv_23} を固定
  
処理:
  1. Seed収集: t0,t1,t2,t3,t4 → 150個
  2. Seed近傍拡大: 150 → 198個 (+48)
  3. 親境界近傍拡大: {mv_5,mv_12,mv_8,mv_15,mv_23} → 5+3=8個 (+3)
  4. 初期候補: 198∪8 = 201個
  
  反復最適化 (2回で収束):
    Iter 1: 候補201, 選択28
    Iter 2: 候補248 (+47近傍), 選択28 → 収束
  
出力:
  min_mvs (t0): {mv_5, mv_12} (固定されているので同じ)
  median_mvs (t2): {mv_7, mv_14}
  max_mvs (t4): {mv_8, mv_15, mv_23} (固定)
  promising_mvs: +18個追加 (既存との重複除く)
```

このように、各ノードで反復的最適化を行い、promising_mvsに蓄積していきます。

---

## アルゴリズムの特徴

### 1. 段階的な近傍拡大

**従来 (UtilityPruner):**
```python
# 事前に全タイムステップのSeedを近傍拡大
for ts_name, seeds in per_timestep_seeds.items():
    expanded_seeds[ts_name] = expand_neighbors(seeds)
# → 過剰な候補を含む可能性
```

**本手法 (UtilityPrunerIterative):**
```python
# 各ノードで必要な分だけ近傍拡大
seed_indices = collect_seeds_for_node(tree_node)
expanded = expand_neighbors(seed_indices)
# → 必要最小限の候補
```

### 2. 反復的探索による解の品質向上

- **イテレーション1**: 初期候補で最適化
- **イテレーション2以降**: 選ばれたMVの近傍を追加して再最適化
- **収束判定**: 選択が変わらなくなるまで繰り返し

**効果:**
- 局所最適解に陥るリスクを低減
- より良い候補を段階的に発見

### 3. 親境界MVの近傍拡大

**変更前:**
```python
candidate_set = expanded_seeds | parent_boundary_mvs  # 親境界はそのまま
```

**変更後:**
```python
expanded_boundary = expand_neighbors(parent_boundary_mvs)
candidate_set = expanded_seeds | expanded_boundary  # 親境界も拡大
```

**理由:**
- 親で選ばれたMVの近傍も有望な可能性
- Seed近傍と重複が多いため、候補爆発のリスクは低い
- より広範な探索が可能

---

## 計算量とパフォーマンス

### 時間計算量

```
T: タイムステップ数
N: WST ノード数 ≈ O(T)
K: 各ノードでの平均イテレーション数 (通常2-3回)
C: 各ノードでの平均候補数
```

**総実行時間 = O(N × K × ILP求解時間(C))**

### 実行時間の例 (8タイムステップ、7634 MV候補)

```
Phase 1 (Seed): 各タイムステップで単独最適化
  → 約5-10分

Phase 2 (Pruning): WST階層的絞り込み
  WST: 15ノード
  平均イテレーション数: 2.5回
  → 約15-30分

Phase 3 (Final): 有望候補で最終最適化
  → 約10-20分
```

---

## 出力と統計情報

### 最終出力

```python
promising_mvs: Set[int]  # 有望MV候補のインデックス集合

# 例:
# 全候補数: 7634
# 全Seed和集合: 245
# WST後の有望候補: 312
# 削減率: 95.9%
```

### 統計情報

```python
pruning_info = pruner.get_pruning_info(promising_mvs)

# {
#     "total_candidates": 7634,
#     "seed_union_count": 245,
#     "promising_candidates": 312,
#     "filtered_out": 7322,
#     "retention_rate": 0.041,
#     "reduction_rate": 0.959,
#     "pruning_time_sec": 1823.5,
#     "total_iterations": 38,
#     "avg_iterations_per_node": 2.53
# }
```

---

## UtilityPruner との比較

| 項目 | UtilityPruner | UtilityPrunerIterative |
|------|---------------|------------------------|
| **近傍拡大** | 事前に一括 | 各ノードで段階的 |
| **最適化回数** | 各ノード1回 | 各ノード最大5回（反復） |
| **親境界MV** | そのまま | 近傍拡大 |
| **候補数** | 多い | 少ない（必要分のみ） |
| **計算時間** | 速い | やや遅い（反復分） |
| **解の品質** | 良い | より良い（探索が深い） |
| **収束判定** | なし | あり |
| **並列処理** | 対応 | 対応 |

---

## 並列処理（オプション機能）

### 概要

WSTの同じ深さ（レベル）のノードは独立しているため、並列実行が可能です。この機能により、マルチコアCPUで大幅な高速化が期待できます。

### 使用方法

```python
pruner = UtilityPrunerIterative(
    # ... 他のパラメータ ...
    use_parallel=True,           # 並列処理を有効化
    max_workers=8,               # ワーカー数（Noneの場合はCPU数）
)
```

コマンドラインから実行する場合：

```bash
python3 experiments/small_test_ver2/scripts/run_utility_optimization.py \
    --query-set job-ceb \
    --storage-mb 1024 \
    --pruning-method iterative \
    --use-parallel \
    --max-workers 8
```

### 並列処理の仕組み

**BFS（幅優先探索）アプローチ:**

1. WSTをレベルごとに処理
2. 同じレベルのノードを並列実行
3. レベル完了後、結果を親ノードから子ノードに伝播
4. 次のレベルへ進む

```
レベル 0 (深さ 0):  [Root]                    ← 1ノード  (1並列)
                       ↓
レベル 1 (深さ 1):  [Left]  [Right]           ← 2ノード  (2並列)
                       ↓        ↓
レベル 2 (深さ 2):  [L-L] [L-R] [R-L] [R-R]   ← 4ノード  (4並列)
                       ↓    ↓    ↓    ↓
             ...      (さらに分割)             ← 8ノード+ (8+並列)
```

### 実装の詳細

**並列/直列の分岐:**

```python
def prune_candidates(self) -> Set[int]:
    # WST構築
    tree = WorkloadSummaryTree(self.T)
    
    # 並列 or 直列で実行
    if self.use_parallel:
        promising_mvs = self._prune_candidates_parallel(tree)
    else:
        promising_mvs = self._prune_candidates_sequential(tree)
    
    return promising_mvs
```

**並列実装 (_prune_candidates_parallel):**

```python
def _prune_candidates_parallel(self, tree):
    promising_mvs = set()
    current_level = [(tree.root, set(), set(), False, False)]
    
    with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
        while current_level:
            # 同じレベルのノードを並列実行
            futures = {}
            for node, parent_min, parent_max, is_left, is_right in current_level:
                future = executor.submit(
                    _solve_node_iterative_static,  # モジュールレベル関数
                    node=node,
                    parent_min_mvs=parent_min,
                    # ... 他のパラメータ ...
                )
                futures[future] = node
            
            # 結果を収集し、次のレベルを準備
            next_level = []
            for future in as_completed(futures):
                result = future.result()
                promising_mvs.update(result["selected_mvs"])
                
                # 子ノードを次のレベルに追加
                if node.left_child:
                    next_level.append((node.left_child, ...))
                if node.right_child:
                    next_level.append((node.right_child, ...))
            
            # 次のレベルへ
            current_level = next_level
    
    return promising_mvs
```

**モジュールレベル関数:**

並列処理では、ワーカープロセスに関数とデータをpickleして渡す必要があります。そのため、インスタンスメソッドではなくモジュールレベル関数として実装します。

```python
def _solve_node_iterative_static(
    node, parent_min_mvs, parent_max_mvs, ...
):
    """各ノードで反復的最適化を実行（pickle可能）."""
    # 1. 初期候補構築
    current_candidates, stats = build_initial_candidates_static(...)
    
    # 2. 頻度集約
    aggregated_freq = aggregate_frequencies_static(...)
    
    # 3. 反復的最適化ループ
    iteration = 0
    while iteration < max_iterations:
        # ILP最適化
        result = local_optimizer.optimize()
        
        # 収束判定
        if converged:
            break
        
        # 近傍拡大
        current_candidates = expand_neighbors_static(...)
        iteration += 1
    
    return {
        "selected_mvs": ...,
        "min_mvs": ...,
        "median_mvs": ...,
        "max_mvs": ...,
        "iterations_used": iteration,
    }
```

### パフォーマンス

**直列実行の場合:**
```
WST: 15ノード
総イテレーション数: 38回
実行時間: 約30分
```

**並列実行の場合 (8ワーカー):**
```
WST: 15ノード (レベルごとに並列化)
総イテレーション数: 38回 (同じ)
実行時間: 約10-15分 (2-3倍高速化)
```

**高速化の理由:**
- 同じレベルのノードが並列実行される
- 深いレベルほどノード数が多く、並列度が高い
- CPUコア数が多いほど効果的

**注意点:**
- 各ノードで個別にILPを解くため、メモリ使用量は増加
- Gurobiライセンスが複数同時実行をサポートする必要がある
- small_test_ver2のような小規模データセットでは高速化が限定的

---

## まとめ

`UtilityPrunerIterative`は、以下の3つの工夫により、効率的かつ高品質なMV候補選出を実現しています：

1. **段階的近傍拡大**: 必要な候補のみを動的に追加
2. **反復的最適化**: 各ノードで収束するまで繰り返し探索
3. **親境界の活用**: 親で選ばれたMVの近傍も含めた広範な探索
4. **並列処理対応**: WSTレベルごとの並列実行で大幅な高速化

これにより、数千のMV候補から数百の有望候補に効率的に絞り込むことができます。

